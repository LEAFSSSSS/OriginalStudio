"""Transactional library operations; original files are never written here."""

import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from .errors import StudioError
from .paths import existing_root, path_key, within
from .storage import Database, utc_now


def require_row(connection, table: str, identifier: int):
    # Table names come exclusively from application constants.
    row = connection.execute(f"SELECT * FROM {table} WHERE id=?", (identifier,)).fetchone()
    if row is None:
        raise StudioError("请求的项目不存在", "not_found", 404)
    return dict(row)


def normalize_tags(tags: list[str]) -> list[str]:
    result = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
    if len(result) > 30 or any(len(tag) > 48 for tag in result):
        raise StudioError("最多设置 30 个标签，每个标签不超过 48 个字符")
    return result


def local_midnight_utc(day: date) -> str:
    try:
        return datetime.combine(day, time.min).astimezone(timezone.utc).isoformat(timespec="milliseconds")
    except (OverflowError, OSError, ValueError) as exc:
        raise StudioError("日期超出本机支持范围，请选择其他日期", "date_out_of_range") from exc


class Repository:
    def __init__(self, database: Database):
        self.db = database

    def root(self, identifier: int) -> dict:
        with self.db.connect() as connection:
            root = require_row(connection, "roots", identifier)
        root["available"] = Path(root["path"]).is_dir()
        return root

    def roots(self) -> list[dict]:
        with self.db.connect() as connection:
            rows = connection.execute("SELECT r.*,COUNT(a.id) AS asset_count FROM roots r LEFT JOIN assets a ON a.root_id=r.id GROUP BY r.id ORDER BY r.id").fetchall()
        return [{**dict(row), "available": Path(row["path"]).is_dir()} for row in rows]

    def add_root(self, value: str, name: str | None) -> dict:
        path = existing_root(value)
        if within(path, self.db.directory):
            raise StudioError("程序数据目录不能作为素材目录")
        with self.db.connect(write=True) as connection:
            for row in connection.execute("SELECT path FROM roots"):
                previous = Path(row["path"])
                if within(path, previous) or within(previous, path):
                    raise StudioError("这个目录或其上级/下级已添加，请使用现有目录", "overlapping_root", 409)
            cursor = connection.execute("INSERT INTO roots(path,path_key,name,created_at) VALUES(?,?,?,?)", (str(path), path_key(path), name or path.name or str(path), utc_now()))
            identifier = cursor.lastrowid
        return self.root(identifier)

    def delete_root(self, identifier: int):
        with self.db.connect(write=True) as connection:
            require_row(connection, "roots", identifier)
            active = connection.execute("SELECT 1 FROM jobs WHERE root_id=? AND status IN ('queued','running','stopping')", (identifier,)).fetchone()
            if active:
                raise StudioError("请先停止该目录的索引任务", "job_active", 409)
            asset_ids = [row[0] for row in connection.execute("SELECT id FROM assets WHERE root_id=?", (identifier,))]
            connection.execute("DELETE FROM roots WHERE id=?", (identifier,))
        for asset_id in asset_ids:
            try:
                (self.db.directory / "thumbnails" / f"{asset_id}.jpg").unlink(missing_ok=True)
            except OSError:
                logging.getLogger(__name__).warning("Preview cache still in use: %s", asset_id)

    def stats(self) -> dict:
        with self.db.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS total,COALESCE(SUM(kind='image'),0) AS image,COALESCE(SUM(kind='video'),0) AS video,COALESCE(SUM(kind='document'),0) AS document,COALESCE(SUM(favorite),0) AS favorites FROM assets").fetchone()
        return dict(row)

    def filters(self, filters: dict, *, include_query=True) -> tuple[str, list]:
        conditions, values = ["1=1"], []
        if filters.get("root_id") is not None:
            self.root(filters["root_id"])
            conditions.append("a.root_id=?")
            values.append(filters["root_id"])
        if filters.get("collection_id") is not None:
            with self.db.connect() as connection:
                require_row(connection, "collections", filters["collection_id"])
            conditions.append("EXISTS(SELECT 1 FROM collection_items ci WHERE ci.asset_id=a.id AND ci.collection_id=?)")
            values.append(filters["collection_id"])
        if filters.get("kind"):
            conditions.append("a.kind=?")
            values.append(filters["kind"])
        if filters.get("favorite") is not None:
            conditions.append("a.favorite=?")
            values.append(int(filters["favorite"]))
        if filters.get("tag"):
            conditions.append("EXISTS(SELECT 1 FROM json_each(a.tags) WHERE value=?)")
            values.append(filters["tag"])
        if filters.get("folder"):
            conditions.append("a.path LIKE ? ESCAPE '\\'")
            values.append(like_pattern(filters["folder"]))
        if filters.get("date_from"):
            conditions.append("a.modified_at>=?")
            first = date.fromisoformat(str(filters["date_from"])[:10])
            values.append(local_midnight_utc(first))
        if filters.get("date_to"):
            last = date.fromisoformat(str(filters["date_to"])[:10])
            conditions.append("a.modified_at<?")
            values.append(local_midnight_utc(last + timedelta(days=1)))
        if include_query:
            query = filters.get("q", filters.get("query", "")) or ""
            for term in query.split():
                conditions.append("(a.name LIKE ? ESCAPE '\\' OR a.path LIKE ? ESCAPE '\\' OR a.notes LIKE ? ESCAPE '\\' OR a.tags LIKE ? ESCAPE '\\')")
                values.extend([like_pattern(term)] * 4)
        return " AND ".join(conditions), values

    def hydrate(self, connection, rows) -> list[dict]:
        items = [dict(row) for row in rows]
        if not items:
            return []
        identifiers = [item["id"] for item in items]
        memberships = {}
        for offset in range(0, len(identifiers), 400):
            group = identifiers[offset:offset + 400]
            placeholders = ",".join("?" for _ in group)
            for row in connection.execute(f"SELECT asset_id,collection_id FROM collection_items WHERE asset_id IN ({placeholders}) ORDER BY collection_id", group):
                memberships.setdefault(row["asset_id"], []).append(row["collection_id"])
        for item in items:
            identifier = item["id"]
            item["favorite"] = bool(item["favorite"])
            item["available"] = bool(item["available"])
            item["tags"] = json.loads(item["tags"])
            item["metadata"] = json.loads(item["metadata"])
            item["collection_ids"] = memberships.get(identifier, [])
            item["thumbnail_url"] = f"/api/assets/{identifier}/thumbnail" if item["kind"] != "document" else None
            item["media_url"] = f"/api/assets/{identifier}/media"
            item.pop("path_key", None)
            item.pop("scan_seen", None)
        return items

    def assets(self, filters: dict) -> dict:
        where, values = self.filters(filters)
        page, page_size = filters.get("page", 1), filters.get("page_size", 36)
        ordering = {"recent": "a.modified_at DESC,a.id DESC", "oldest": "a.modified_at,a.id", "name": "a.name COLLATE NOCASE,a.id"}[filters.get("sort", "recent")]
        with self.db.connect() as connection:
            total = connection.execute(f"SELECT COUNT(*) FROM assets a WHERE {where}", values).fetchone()[0]
            rows = connection.execute(f"SELECT a.* FROM assets a WHERE {where} ORDER BY {ordering} LIMIT ? OFFSET ?", [*values, page_size, (page - 1) * page_size]).fetchall()
            return {"items": self.hydrate(connection, rows), "total": total, "page": page, "page_size": page_size}

    def asset(self, identifier: int, *, detail=False) -> dict:
        with self.db.connect() as connection:
            row = require_row(connection, "assets", identifier)
            item = self.hydrate(connection, [row])[0]
            if detail:
                root = require_row(connection, "roots", row["root_id"])
                item["available"] = Path(item["path"]).is_file() and within(Path(item["path"]), Path(root["path"]))
                item["segments"] = [dict(segment) for segment in connection.execute("SELECT * FROM segments WHERE asset_id=? ORDER BY page,start,id LIMIT 200", (identifier,))]
        return item

    def patch_asset(self, identifier: int, changes: dict) -> dict:
        with self.db.connect(write=True) as connection:
            require_row(connection, "assets", identifier)
            self._patch(connection, identifier, changes)
        return self.asset(identifier, detail=True)

    def _patch(self, connection, identifier: int, changes: dict):
        if "collection_ids" in changes:
            for collection_id in changes["collection_ids"]:
                require_row(connection, "collections", collection_id)
        for key in ("favorite", "notes", "tags"):
            if key in changes:
                value = json.dumps(normalize_tags(changes[key]), ensure_ascii=False) if key == "tags" else changes[key]
                connection.execute(f"UPDATE assets SET {key}=? WHERE id=?", (value, identifier))
        if "collection_ids" in changes:
            identifiers = list(dict.fromkeys(changes["collection_ids"]))
            if identifiers:
                placeholders = ",".join("?" for _ in identifiers)
                connection.execute(f"DELETE FROM collection_items WHERE asset_id=? AND collection_id NOT IN ({placeholders})", [identifier, *identifiers])
            else:
                connection.execute("DELETE FROM collection_items WHERE asset_id=?", (identifier,))
            connection.executemany("INSERT OR IGNORE INTO collection_items(collection_id,asset_id,collected_at) VALUES(?,?,?)", [(collection_id, identifier, utc_now()) for collection_id in identifiers])

    def batch(self, payload: dict) -> int:
        identifiers = list(dict.fromkeys(payload["ids"]))
        with self.db.connect(write=True) as connection:
            assets = [require_row(connection, "assets", identifier) for identifier in identifiers]
            if payload.get("collection_id") is not None:
                require_row(connection, "collections", payload["collection_id"])
            for asset in assets:
                changes = {}
                if payload.get("favorite") is not None:
                    changes["favorite"] = payload["favorite"]
                if payload.get("add_tags") or payload.get("remove_tags"):
                    remove = set(payload.get("remove_tags") or [])
                    changes["tags"] = normalize_tags([tag for tag in json.loads(asset["tags"]) if tag not in remove] + (payload.get("add_tags") or []))
                self._patch(connection, asset["id"], changes)
                if payload.get("collection_id") is not None:
                    if payload.get("remove_collection"):
                        connection.execute("DELETE FROM collection_items WHERE asset_id=? AND collection_id=?", (asset["id"], payload["collection_id"]))
                    else:
                        connection.execute("INSERT OR IGNORE INTO collection_items(collection_id,asset_id,collected_at) VALUES(?,?,?)", (payload["collection_id"], asset["id"], utc_now()))
        return len(identifiers)

    def collections(self) -> list[dict]:
        with self.db.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT c.*,COUNT(ci.asset_id) AS item_count FROM collections c LEFT JOIN collection_items ci ON ci.collection_id=c.id GROUP BY c.id ORDER BY c.id")]

    def collection(self, identifier: int) -> dict:
        with self.db.connect() as connection:
            result = require_row(connection, "collections", identifier)
            result["item_count"] = connection.execute("SELECT COUNT(*) FROM collection_items WHERE collection_id=?", (identifier,)).fetchone()[0]
            return result

    def save_collection(self, changes: dict, identifier: int | None = None) -> dict:
        with self.db.connect(write=True) as connection:
            if identifier is not None:
                require_row(connection, "collections", identifier)
            if "name" in changes:
                duplicate = connection.execute("SELECT id FROM collections WHERE name=? COLLATE NOCASE AND id!=?", (changes["name"], identifier or -1)).fetchone()
                if duplicate:
                    raise StudioError("已存在同名收藏集", "duplicate_collection", 409)
            if identifier is None:
                cursor = connection.execute("INSERT INTO collections(name,color,created_at) VALUES(?,?,?)", (changes["name"], changes.get("color", "#31a580"), utc_now()))
                identifier = cursor.lastrowid
            else:
                for key in ("name", "color"):
                    if key in changes:
                        connection.execute(f"UPDATE collections SET {key}=? WHERE id=?", (changes[key], identifier))
        return self.collection(identifier)

    def delete_collection(self, identifier: int):
        with self.db.connect(write=True) as connection:
            require_row(connection, "collections", identifier)
            connection.execute("DELETE FROM collections WHERE id=?", (identifier,))


def like_pattern(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
