"""A single durable worker. Every file outcome is committed independently."""

import logging
import os
import threading
from pathlib import Path

from .errors import StudioError
from .indexing import Indexer, JobCancelled
from .paths import path_key, within
from .repository import require_row
from .settings import file_kind
from .storage import utc_now


LOG = logging.getLogger(__name__)
ACTIVE = ("queued", "running", "stopping")
SKIP_DIRECTORIES = {".git", ".venv", "venv", "env", "node_modules", "__pycache__", "$RECYCLE.BIN", "System Volume Information", ".build"}


class JobManager:
    def __init__(self, repository, settings, engines):
        self.repository, self.db = repository, repository.db
        self.settings, self.engines = settings, engines
        self.indexer = Indexer(repository, settings, engines)
        self.wake = threading.Event()
        self.shutdown = threading.Event()
        self.thread = None

    def start(self):
        with self.db.connect(write=True) as connection:
            connection.execute("UPDATE jobs SET status='interrupted',stage='interrupted',current_path='',updated_at=? WHERE status IN ('running','stopping')", (utc_now(),))
            connection.execute("UPDATE job_items SET status='pending' WHERE status='running'")
        if self.settings.worker_enabled:
            self.thread = threading.Thread(target=self._loop, name="studio-indexer", daemon=True)
            self.thread.start()

    def close(self):
        self.shutdown.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=5)

    def get(self, identifier: int, detail=False) -> dict:
        with self.db.connect() as connection:
            job = require_row(connection, "jobs", identifier)
            root = require_row(connection, "roots", job["root_id"])
            if detail:
                job["failures"] = [dict(row) for row in connection.execute("SELECT path,code,message FROM job_items WHERE job_id=? AND status='failed' ORDER BY id DESC LIMIT 100", (identifier,))]
        job["root_name"] = root["name"]
        job["progress"] = None if job["stage"] == "discovering" else (round(job["done"] / job["total"] * 100, 1) if job["total"] else (100 if job["status"] == "completed" else 0))
        return job

    def list(self, limit=20, active_only=False):
        with self.db.connect() as connection:
            condition = "WHERE status IN ('queued','running','stopping')" if active_only else ""
            ids = [row[0] for row in connection.execute(f"SELECT id FROM jobs {condition} ORDER BY id DESC LIMIT ?", (limit,))]
            total = connection.execute(f"SELECT COUNT(*) FROM jobs {condition}").fetchone()[0]
        return {"items": [self.get(identifier) for identifier in ids], "total": total}

    def create(self, payload: dict):
        root = self.repository.root(payload["root_id"])
        if not root["available"]:
            raise StudioError("素材目录暂时不可用，请连接磁盘后重试", "folder_unavailable", 409)
        operation = payload["operation"]
        if operation == "visual" and not self.engines.vision.status()["installed"]:
            raise StudioError(self.engines.vision.status()["message"], "dependency_missing", 503)
        if operation == "transcripts" and not self.engines.speech.status()["installed"]:
            raise StudioError(self.engines.speech.status()["message"], "dependency_missing", 503)
        now = utc_now()
        with self.db.connect(write=True) as connection:
            duplicate = connection.execute("SELECT 1 FROM jobs WHERE root_id=? AND operation=? AND status IN ('queued','running','stopping')", (root["id"], operation)).fetchone()
            if duplicate:
                raise StudioError("同一目录已有相同任务等待或运行中", "job_active", 409)
            cursor = connection.execute("INSERT INTO jobs(root_id,operation,retry_failed,created_at,updated_at) VALUES(?,?,?,?,?)", (root["id"], operation, payload.get("retry_failed", False), now, now))
            identifier = cursor.lastrowid
        self.wake.set()
        return self.get(identifier)

    def stop(self, identifier):
        with self.db.connect(write=True) as connection:
            job = require_row(connection, "jobs", identifier)
            if job["status"] == "queued":
                connection.execute("UPDATE jobs SET status='stopped',stage='stopped',updated_at=? WHERE id=?", (utc_now(), identifier))
            elif job["status"] == "running":
                connection.execute("UPDATE jobs SET status='stopping',updated_at=? WHERE id=?", (utc_now(), identifier))
        return self.get(identifier)

    def resume(self, identifier):
        with self.db.connect(write=True) as connection:
            job = require_row(connection, "jobs", identifier)
            if job["status"] not in {"stopped", "interrupted", "failed", "completed"}:
                raise StudioError("此任务暂时不能继续", "job_active", 409)
            if job["status"] == "completed" and not job["failed"]:
                raise StudioError("任务已完成，请新建增量索引任务", "job_completed", 409)
            require_row(connection, "roots", job["root_id"])
            duplicate = connection.execute("SELECT 1 FROM jobs WHERE root_id=? AND operation=? AND status IN ('queued','running','stopping')", (job["root_id"], job["operation"])).fetchone()
            if duplicate:
                raise StudioError("同一目录已有相同任务运行中", "job_active", 409)
            connection.execute("UPDATE job_items SET status='pending',code='',message='' WHERE job_id=? AND status IN ('failed','running')", (identifier,))
            connection.execute("UPDATE jobs SET status='queued',stage='queued',error='',finished_at=NULL,updated_at=? WHERE id=?", (utc_now(), identifier))
            self._recount(connection, identifier)
        self.wake.set()
        return self.get(identifier)

    def _update(self, identifier, **values):
        values["updated_at"] = utc_now()
        columns = ",".join(f"{key}=?" for key in values)
        with self.db.connect(write=True) as connection:
            connection.execute(f"UPDATE jobs SET {columns} WHERE id=?", [*values.values(), identifier])

    def _cancelled(self, identifier):
        if self.shutdown.is_set():
            return True
        with self.db.connect() as connection:
            row = connection.execute("SELECT status FROM jobs WHERE id=?", (identifier,)).fetchone()
            return row is None or row[0] == "stopping"

    def _loop(self):
        while not self.shutdown.is_set():
            with self.db.connect(write=True) as connection:
                row = connection.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
                if row:
                    connection.execute("UPDATE jobs SET status='running',stage='discovering',updated_at=? WHERE id=?", (utc_now(), row[0]))
            if row is None:
                self.wake.wait(0.5)
                self.wake.clear()
                continue
            try:
                self._execute(row[0])
            except JobCancelled:
                state = "interrupted" if self.shutdown.is_set() else "stopped"
                self._update(row[0], status=state, stage=state, current_path="")
            except Exception as exc:
                LOG.exception("Index job %s failed", row[0])
                message = exc.message if isinstance(exc, StudioError) else f"任务异常：{type(exc).__name__}；请查看日志"
                self._update(row[0], status="failed", stage="failed", error=message, current_path="", finished_at=utc_now())

    def _paths(self, root, job):
        if job["retry_failed"]:
            with self.db.connect() as connection:
                previous = connection.execute("SELECT id FROM jobs WHERE root_id=? AND operation=? AND id<? AND failed>0 ORDER BY id DESC LIMIT 1", (root["id"], job["operation"], job["id"])).fetchone()
                paths = connection.execute("SELECT path FROM job_items WHERE job_id=? AND status='failed'", (previous[0],)).fetchall() if previous else []
            yield from (Path(row[0]) for row in paths)
            return
        if job["operation"] != "scan":
            kinds = {"documents": ("document",), "visual": ("image", "video"), "transcripts": ("video",), "cleanup": ("image", "video", "document")}[job["operation"]]
            with self.db.connect() as connection:
                placeholders = ",".join("?" for _ in kinds)
                rows = connection.execute(f"SELECT path FROM assets WHERE root_id=? AND kind IN ({placeholders})", (root["id"], *kinds)).fetchall()
            yield from (Path(row[0]) for row in rows)
            return

        def walk_error(error):
            raise StudioError(f"无法读取部分目录：{error.filename}", "folder_permission")

        for current, directories, files in os.walk(root["path"], followlinks=False, onerror=walk_error):
            current_path = Path(current)
            directories[:] = sorted(name for name in directories if name not in SKIP_DIRECTORIES and not (current_path / name).is_symlink() and not within(current_path / name, self.db.directory))
            self._update(job["id"], current_path=str(current_path))
            for name in sorted(files):
                path = current_path / name
                if file_kind(path) and not path.is_symlink() and within(path, Path(root["path"])):
                    yield path

    def _discover(self, root, job):
        for path in self._paths(root, job):
            if self._cancelled(job["id"]):
                raise JobCancelled()
            with self.db.connect(write=True) as connection:
                connection.execute("INSERT OR IGNORE INTO job_items(job_id,path) VALUES(?,?)", (job["id"], str(path)))
        with self.db.connect(write=True) as connection:
            self._recount(connection, job["id"])
        self._update(job["id"], stage="indexing", current_path="")

    @staticmethod
    def _recount(connection, identifier):
        row = connection.execute("SELECT COUNT(*) AS total,COALESCE(SUM(status IN ('ready','skipped','failed')),0) AS done,COALESCE(SUM(status='skipped'),0) AS skipped,COALESCE(SUM(status='failed'),0) AS failed FROM job_items WHERE job_id=?", (identifier,)).fetchone()
        connection.execute("UPDATE jobs SET total=?,done=?,skipped=?,failed=? WHERE id=?", (*tuple(row), identifier))

    def _execute(self, identifier):
        job = self.get(identifier)
        root = self.repository.root(job["root_id"])
        if not root["available"]:
            raise StudioError("素材目录不可用，请连接磁盘后继续", "folder_unavailable", 409)
        self._discover(root, job)
        if self._cancelled(identifier):
            raise JobCancelled()
        if not self.get(identifier)["total"]:
            self._update(identifier, status="completed", stage="completed", current_path="", finished_at=utc_now())
            return
        if job["operation"] in {"visual", "transcripts"}:
            self._update(identifier, stage="loading_model")
            engine = self.engines.vision if job["operation"] == "visual" else self.engines.speech
            engine.load()
            self._update(identifier, stage="indexing")
        while True:
            if self._cancelled(identifier):
                raise JobCancelled()
            with self.db.connect(write=True) as connection:
                item = connection.execute("SELECT * FROM job_items WHERE job_id=? AND status='pending' ORDER BY id LIMIT 1", (identifier,)).fetchone()
                if item:
                    connection.execute("UPDATE job_items SET status='running' WHERE id=?", (item["id"],))
            if item is None:
                break
            self._update(identifier, current_path=item["path"])
            try:
                result = self.indexer.process(root, Path(item["path"]), job["operation"], identifier, lambda: self._cancelled(identifier))
                code, message = "", ""
            except JobCancelled:
                with self.db.connect(write=True) as connection:
                    connection.execute("UPDATE job_items SET status='pending' WHERE id=?", (item["id"],))
                raise
            except Exception as exc:
                result = "failed"
                code = exc.code if isinstance(exc, StudioError) else type(exc).__name__
                message = exc.message if isinstance(exc, StudioError) else f"文件处理失败：{type(exc).__name__}"
                LOG.warning("File indexing failed: %s (%s)", item["path"], code)
                with self.db.connect(write=True) as connection:
                    state_column = {"documents": "text_state", "visual": "visual_state", "transcripts": "transcript_state"}.get(job["operation"], "text_state" if file_kind(Path(item["path"])) == "document" else "visual_state")
                    connection.execute(f"UPDATE assets SET {state_column}='failed',error=? WHERE root_id=? AND path=?", (message, root["id"], item["path"]))
            with self.db.connect(write=True) as connection:
                connection.execute("UPDATE job_items SET status=?,code=?,message=?,asset_id=(SELECT id FROM assets WHERE root_id=? AND path=?) WHERE id=?", (result, code, message, root["id"], item["path"], item["id"]))
                self._recount(connection, identifier)
        if self._cancelled(identifier):
            raise JobCancelled()
        self._update(identifier, status="completed", stage="completed", current_path="", finished_at=utc_now())
