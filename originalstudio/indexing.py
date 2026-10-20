"""One-file indexing, with atomic replacements for searchable data."""

import json
from datetime import datetime, timezone
from pathlib import Path

from .documents import extract_document
from .engines import vector_bytes
from .errors import StudioError
from .media import image_info, thumbnail, video_frames, video_info
from .paths import path_key, within
from .settings import file_kind


class JobCancelled(Exception):
    pass


class Indexer:
    def __init__(self, repository, settings, engines):
        self.repository = repository
        self.db = repository.db
        self.settings = settings
        self.engines = engines

    def _ensure_asset(self, root, path, job_id):
        if not within(path, Path(root["path"])):
            raise StudioError("符号链接的真实路径离开了素材目录", "outside_root")
        stat = path.stat()
        key, kind = path_key(path), file_kind(path)
        if kind is None:
            raise StudioError("不支持的素材类型", "unsupported_type")
        modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="milliseconds")
        with self.db.connect(write=True) as connection:
            old = connection.execute("SELECT * FROM assets WHERE path_key=?", (key,)).fetchone()
            changed = old is None or old["bytes"] != stat.st_size or old["mtime_ns"] != stat.st_mtime_ns
            if old is None:
                connection.execute("UPDATE id_counters SET value=value+1 WHERE name='asset'")
                identifier = connection.execute("SELECT value FROM id_counters WHERE name='asset'").fetchone()[0]
                connection.execute("INSERT INTO assets(id,root_id,path,path_key,name,kind,extension,bytes,mtime_ns,modified_at,scan_seen,visual_state,text_state,transcript_state) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (identifier, root["id"], str(path), key, path.name, kind, path.suffix.lower(), stat.st_size, stat.st_mtime_ns, modified, job_id, "pending" if kind != "document" else "skipped", "pending" if kind == "document" else "skipped", "pending" if kind == "video" else "skipped"))
            else:
                identifier = old["id"]
                connection.execute("UPDATE assets SET path=?,name=?,extension=?,bytes=?,mtime_ns=?,modified_at=?,available=1,scan_seen=? WHERE id=?", (str(path), path.name, path.suffix.lower(), stat.st_size, stat.st_mtime_ns, modified, job_id, identifier))
                if changed:
                    connection.execute("DELETE FROM embeddings WHERE asset_id=?", (identifier,))
                    connection.execute("DELETE FROM segments WHERE asset_id=?", (identifier,))
                    connection.execute("UPDATE assets SET visual_state=?,text_state=?,transcript_state=?,error='',metadata='{}' WHERE id=?", ("pending" if kind != "document" else "skipped", "pending" if kind == "document" else "skipped", "pending" if kind == "video" else "skipped", identifier))
                    try:
                        (self.db.directory / "thumbnails" / f"{identifier}.jpg").unlink(missing_ok=True)
                    except OSError:
                        pass  # The completion marker also prevents stale previews from being served.
        return identifier, changed, old, stat

    @staticmethod
    def _check_stat(path, initial):
        current = path.stat()
        if (current.st_mtime_ns, current.st_size) != (initial.st_mtime_ns, initial.st_size):
            raise StudioError("索引期间原文件发生变化，请重新扫描", "source_changed")

    def _replace_segments(self, connection, identifier, kind, segments):
        connection.execute("DELETE FROM segments WHERE asset_id=? AND kind=?", (identifier, kind))
        connection.executemany("INSERT INTO segments(asset_id,kind,text,page,start,end) VALUES(?,?,?,?,?,?)", [(identifier, kind, item["text"], item.get("page"), item.get("start"), item.get("end")) for item in segments])

    def process(self, root: dict, path: Path, operation: str, job_id: int, cancelled) -> str:
        if operation == "cleanup":
            return self.cleanup(root, path)
        identifier, changed, previous, initial = self._ensure_asset(root, path, job_id)
        if cancelled():
            raise JobCancelled()
        complete = previous and json.loads(previous["metadata"]).get("scan_complete", False)
        preview_missing = file_kind(path) != "document" and not (self.db.directory / "thumbnails" / f"{identifier}.jpg").is_file()
        scan_needed = changed or not complete or not previous["available"] or bool(previous["error"]) or preview_missing or operation == "documents"
        if scan_needed:
            self.scan_asset(identifier, path, initial)
        if operation == "scan":
            return "ready" if scan_needed else "skipped"
        if operation == "documents":
            return "ready"
        asset = self.repository.asset(identifier)
        if operation == "visual":
            self.engines.vision.load()
            with self.db.connect() as connection:
                indexed = connection.execute("SELECT 1 FROM embeddings WHERE asset_id=? AND model=?", (identifier, self.engines.vision.signature)).fetchone()
            if indexed and asset["visual_state"] == "ready":
                return "skipped"
            vectors = []
            if asset["kind"] == "image":
                _, image = image_info(path)
                vectors.append((-1.0, self.engines.vision.encode_image(image)))
            else:
                for position, image in video_frames(path, self.settings.frame_interval, self.settings.max_video_frames, cancelled):
                    vectors.append((position, self.engines.vision.encode_image(image)))
            if cancelled():
                raise JobCancelled()
            if not vectors:
                raise StudioError("视频中没有可读取的画面", "no_video_frames")
            self._check_stat(path, initial)
            with self.db.connect(write=True) as connection:
                connection.execute("DELETE FROM embeddings WHERE asset_id=?", (identifier,))
                connection.executemany("INSERT INTO embeddings(asset_id,position,model,dimensions,vector) VALUES(?,?,?,?,?)", [(identifier, position, self.engines.vision.signature, len(vector), vector_bytes(vector)) for position, vector in vectors])
                connection.execute("UPDATE assets SET visual_state='ready',error='' WHERE id=?", (identifier,))
            return "ready"
        if operation == "transcripts":
            if asset["transcript_state"] in {"ready", "skipped"}:
                return "skipped"
            try:
                segments = self.engines.speech.transcribe(path, cancelled)
            except StudioError as exc:
                if exc.code != "no_audio":
                    raise
                if cancelled():
                    raise JobCancelled()
                self._check_stat(path, initial)
                with self.db.connect(write=True) as connection:
                    connection.execute("UPDATE assets SET transcript_state='skipped',error='',metadata=json_set(metadata,'$.transcript_note',?) WHERE id=?", (exc.message, identifier))
                return "skipped"
            if cancelled():
                raise JobCancelled()
            self._check_stat(path, initial)
            with self.db.connect(write=True) as connection:
                self._replace_segments(connection, identifier, "transcript", segments)
                connection.execute("UPDATE assets SET transcript_state=?,error='',metadata=json_set(metadata,'$.transcript_note',?) WHERE id=?", ("ready" if segments else "skipped", "" if segments else "未检测到可识别的语音", identifier))
            return "ready" if segments else "skipped"
        raise StudioError("未知索引操作")

    def scan_asset(self, identifier, path, initial):
        kind = file_kind(path)
        info, preview, document = {}, None, None
        if kind == "image":
            info, preview = image_info(path)
        elif kind == "video":
            info, preview = video_info(path)
        else:
            document = extract_document(path, self.settings.max_document_chars)
            info["truncated"] = document.truncated
            info["indexed_characters"] = sum(len(item["text"]) for item in document.segments)
            info["text_note"] = "仅保存前部分正文" if document.truncated else ("未提取到文本；扫描版 PDF 需要先 OCR" if not document.segments else "")
        self._check_stat(path, initial)
        if preview is not None:
            thumbnail(preview, self.db.directory / "thumbnails" / f"{identifier}.jpg")
        info["scan_complete"] = True
        with self.db.connect(write=True) as connection:
            connection.execute("UPDATE assets SET width=?,height=?,duration=?,fps=?,metadata=?,error='' WHERE id=?", (info.get("width"), info.get("height"), info.get("duration"), info.get("fps"), json.dumps(info, ensure_ascii=False), identifier))
            if document is not None:
                self._replace_segments(connection, identifier, "document", document.segments)
                connection.execute("UPDATE assets SET text_state=? WHERE id=?", ("ready" if document.segments else "skipped", identifier))

    def cleanup(self, root, path):
        available = path.is_file() and within(path, Path(root["path"]))
        with self.db.connect(write=True) as connection:
            row = connection.execute("SELECT id FROM assets WHERE path=? AND root_id=?", (str(path), root["id"])).fetchone()
            if row is None:
                return "skipped"
            connection.execute("UPDATE assets SET available=? WHERE id=?", (available, row["id"]))
            if not available:
                connection.execute("DELETE FROM embeddings WHERE asset_id=?", (row["id"],))
                connection.execute("DELETE FROM segments WHERE asset_id=?", (row["id"],))
                connection.execute("UPDATE assets SET metadata=json_remove(metadata,'$.scan_complete'),visual_state=CASE WHEN kind='document' THEN 'skipped' ELSE 'pending' END,text_state=CASE WHEN kind='document' THEN 'pending' ELSE 'skipped' END,transcript_state=CASE WHEN kind='video' THEN 'pending' ELSE 'skipped' END WHERE id=?", (row["id"],))
        return "ready" if not available else "skipped"
