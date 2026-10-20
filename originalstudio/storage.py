import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


SCHEMA = """
CREATE TABLE id_counters(name TEXT PRIMARY KEY,value INTEGER NOT NULL);
INSERT INTO id_counters(name,value) VALUES('asset',0);
CREATE TABLE roots (
    id INTEGER PRIMARY KEY, path TEXT NOT NULL, path_key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE assets (
    id INTEGER PRIMARY KEY, root_id INTEGER NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
    path TEXT NOT NULL, path_key TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
    kind TEXT NOT NULL, extension TEXT NOT NULL, bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL, modified_at TEXT NOT NULL,
    width INTEGER, height INTEGER, duration REAL, fps REAL,
    available INTEGER NOT NULL DEFAULT 1, scan_seen INTEGER,
    favorite INTEGER NOT NULL DEFAULT 0, tags TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '', visual_state TEXT NOT NULL DEFAULT 'pending',
    text_state TEXT NOT NULL DEFAULT 'pending', transcript_state TEXT NOT NULL DEFAULT 'pending',
    error TEXT NOT NULL DEFAULT '', metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX assets_root_kind ON assets(root_id, kind);
CREATE INDEX assets_modified ON assets(modified_at DESC);
CREATE TABLE collections (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, color TEXT NOT NULL DEFAULT '#31a580', created_at TEXT NOT NULL
);
CREATE TABLE collection_items (
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    collected_at TEXT NOT NULL, PRIMARY KEY(collection_id, asset_id)
);
CREATE INDEX collection_assets ON collection_items(asset_id);
CREATE TABLE segments (
    id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    kind TEXT NOT NULL, text TEXT NOT NULL, page INTEGER, start REAL, end REAL
);
CREATE INDEX segments_asset_kind ON segments(asset_id, kind);
CREATE VIRTUAL TABLE segment_fts USING fts5(text, content='segments', content_rowid='id', tokenize='trigram');
CREATE TRIGGER segments_ai AFTER INSERT ON segments BEGIN
    INSERT INTO segment_fts(rowid,text) VALUES(new.id,new.text);
END;
CREATE TRIGGER segments_ad AFTER DELETE ON segments BEGIN
    INSERT INTO segment_fts(segment_fts,rowid,text) VALUES('delete',old.id,old.text);
END;
CREATE TRIGGER segments_au AFTER UPDATE ON segments BEGIN
    INSERT INTO segment_fts(segment_fts,rowid,text) VALUES('delete',old.id,old.text);
    INSERT INTO segment_fts(rowid,text) VALUES(new.id,new.text);
END;
CREATE TABLE embeddings (
    id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    position REAL NOT NULL DEFAULT -1, model TEXT NOT NULL, dimensions INTEGER NOT NULL, vector BLOB NOT NULL,
    UNIQUE(asset_id,position,model)
);
CREATE INDEX embeddings_model ON embeddings(model,asset_id);
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY, root_id INTEGER NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
    operation TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', stage TEXT NOT NULL DEFAULT 'queued',
    total INTEGER NOT NULL DEFAULT 0, done INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
    current_path TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
    retry_failed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE job_items (
    id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    path TEXT NOT NULL, asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending', code TEXT NOT NULL DEFAULT '', message TEXT NOT NULL DEFAULT '',
    UNIQUE(job_id,path)
);
CREATE INDEX job_pending ON job_items(job_id,status);
PRAGMA user_version=2;
"""


class Database:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "workspace.sqlite3"
        for name in ("thumbnails", "references", "exports", "backups", "models", "logs"):
            (directory / name).mkdir(exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                connection.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + "\nCOMMIT;")
            elif version == 1:
                cached_ids = [int(path.stem) for path in (directory / "thumbnails").glob("*.jpg") if path.stem.isdecimal() and len(path.stem) < 19]
                maximum = max(connection.execute("SELECT COALESCE(MAX(id),0) FROM assets").fetchone()[0], max(cached_ids, default=0))
                connection.executescript("BEGIN IMMEDIATE; CREATE TABLE id_counters(name TEXT PRIMARY KEY,value INTEGER NOT NULL); PRAGMA user_version=2;")
                connection.execute("INSERT INTO id_counters(name,value) VALUES('asset',?)", (maximum,))
            elif version != 2:
                raise RuntimeError(f"不支持的数据库版本 {version}，请使用相应版本程序打开")

    @contextmanager
    def connect(self, *, write=False):
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=20000")
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def backup(self) -> dict:
        from uuid import uuid4

        name = f"originalstudio-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}.sqlite3"
        target = self.directory / "backups" / name
        with self.connect() as source:
            destination = sqlite3.connect(target)
            try:
                source.backup(destination)
            finally:
                destination.close()
        return {"name": name, "url": f"/api/backups/{name}", "created_at": utc_now()}
