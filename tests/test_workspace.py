"""End-to-end behavior checks using isolated files and databases."""

import csv
import io
import shutil
import os
from datetime import datetime, timedelta
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from originalstudio.api import create_app
from originalstudio.settings import Settings


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="original-studio-")
        self.base = Path(self.temp.name)
        self.root = self.base / "素材"
        self.root.mkdir()
        (self.root / "海边笔记.txt").write_text("午后的海边，阳光照在蓝色的海面。\n这是第二行。", encoding="utf-8")
        (self.root / "城市.md").write_text("# 夜景\n城市夜景适合用在片头。", encoding="utf-8")
        Image.new("RGB", (100, 80), "blue").save(self.root / "蓝色海面.png")
        self.app = create_app(Settings(data_dir=self.base / "state"))
        self.client = TestClient(self.app, base_url="http://127.0.0.1:8090")
        self.client.__enter__()
        token = self.client.get("/api/session").json()["token"]
        self.client.headers.update({"X-Studio-Token": token})
        result = self.client.post("/api/roots", json={"path": str(self.root)})
        self.assertEqual(result.status_code, 201, result.text)
        self.root_id = result.json()["id"]

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def run_job(self, operation="scan", **kwargs):
        response = self.client.post("/api/jobs", json={"root_id": self.root_id, "operation": operation, **kwargs})
        self.assertEqual(response.status_code, 202, response.text)
        job_id = response.json()["id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            job = self.client.get(f"/api/jobs/{job_id}").json()
            if job["status"] not in {"queued", "running", "stopping"}:
                self.assertEqual(job["status"], "completed", job)
                return job
            time.sleep(0.03)
        self.fail("The isolated indexing task did not finish")

    def test_scan_and_short_chinese_fulltext_search(self):
        self.run_job()
        listed = self.client.get("/api/assets", params={"root_id": self.root_id}).json()
        self.assertEqual(listed["total"], 3)
        result = self.client.post("/api/search", json={"mode": "document", "query": "海边"}).json()
        self.assertEqual(result["total"], 1, result)
        self.assertIn("阳光", result["items"][0]["excerpt"])
        self.assertEqual(result["items"][0]["name"], "海边笔记.txt")
        long_query = self.client.post("/api/search", json={"mode": "document", "query": "城市夜景"}).json()
        self.assertEqual(long_query["total"], 1)

    def test_collection_annotations_and_rescan_preserve_identity(self):
        self.run_job()
        asset = self.client.get("/api/assets", params={"q": "蓝色"}).json()["items"][0]
        collection = self.client.post("/api/collections", json={"name": "剪辑参考"}).json()
        patch = {"favorite": True, "tags": ["海边", "蓝色", "海边"], "notes": "=1+1", "collection_ids": [collection["id"]]}
        updated = self.client.patch(f'/api/assets/{asset["id"]}', json=patch)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["tags"], ["海边", "蓝色"])
        self.run_job()
        stored = self.client.get(f'/api/assets/{asset["id"]}').json()
        self.assertTrue(stored["favorite"])
        self.assertEqual(stored["notes"], "=1+1")
        content = self.client.get(f'/api/collections/{collection["id"]}/export.csv').content.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(content)))
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["notes"].startswith("'="))

    def test_changed_file_reindexes_and_missing_file_never_deletes_annotations(self):
        self.run_job()
        asset = self.client.get("/api/assets", params={"q": "笔记"}).json()["items"][0]
        self.client.patch(f'/api/assets/{asset["id"]}', json={"favorite": True})
        path = self.root / "海边笔记.txt"
        path.write_text("新的内容：森林与山脉。", encoding="utf-8")
        self.run_job()
        found = self.client.post("/api/search", json={"mode": "document", "query": "山脉"}).json()
        self.assertEqual(found["total"], 1)
        self.assertEqual(found["items"][0]["id"], asset["id"])
        path.unlink()
        self.run_job("cleanup")
        stored = self.client.get(f'/api/assets/{asset["id"]}').json()
        self.assertFalse(stored["available"])
        self.assertTrue(stored["favorite"])
        self.assertEqual(self.client.get(f'/api/assets/{asset["id"]}/media').status_code, 404)

    def test_scope_filters_pagination_and_batch_atomicity(self):
        self.run_job()
        first_page = self.client.get("/api/assets", params={"page_size": 1}).json()
        self.assertEqual(first_page["total"], 3)
        self.assertEqual(len(first_page["items"]), 1)
        asset = first_page["items"][0]
        response = self.client.post("/api/assets/batch", json={"ids": [asset["id"], 999999], "favorite": True})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.client.get(f'/api/assets/{asset["id"]}').json()["favorite"])
        self.assertEqual(self.client.get("/api/assets", params={"root_id": 999999}).status_code, 404)
        nested = self.root / "子目录"
        nested.mkdir()
        self.assertEqual(self.client.post("/api/roots", json={"path": str(nested)}).status_code, 409)

    def test_session_origin_validation_and_untrusted_host(self):
        response = self.client.post("/api/collections", json={"name": "bad"}, headers={"X-Studio-Token": "wrong"})
        self.assertEqual(response.status_code, 403)
        response = self.client.get("/api/session", headers={"Origin": "https://untrusted.example"})
        self.assertEqual(response.status_code, 403)
        response = self.client.get("/api/status", headers={"Host": "untrusted.example:8090"})
        self.assertEqual(response.status_code, 403)
        response = self.client.post("/api/search", json={"mode": "semantic", "query": ""})
        self.assertEqual(response.status_code, 422)
        response = self.client.get("/api/assets", params={"date_from": "2026-10-20", "date_to": "2026-10-19"})
        self.assertEqual(response.status_code, 422)

    def test_reference_upload_and_backup(self):
        image = io.BytesIO()
        Image.new("RGB", (10, 10), "green").save(image, format="PNG")
        response = self.client.post("/api/references", files={"file": ("参考.png", image.getvalue(), "image/png")})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.client.get(response.json()["url"]).status_code, 200)
        bad = self.client.post("/api/references", files={"file": ("bad.png", b"not an image", "image/png")})
        self.assertEqual(bad.status_code, 422)
        backup = self.client.post("/api/backups", json={})
        self.assertEqual(backup.status_code, 201, backup.text)
        self.assertTrue(self.client.get(backup.json()["url"]).content.startswith(b"SQLite format 3"))

    def test_restored_database_scan_rebuilds_missing_thumbnails(self):
        self.run_job()
        asset = self.client.get("/api/assets", params={"kind": "image"}).json()["items"][0]
        self.client.patch(f'/api/assets/{asset["id"]}', json={"favorite": True})
        backup = self.client.post("/api/backups", json={}).json()
        recovered = self.base / "recovered"
        recovered.mkdir()
        shutil.copy2(self.base / "state" / "backups" / backup["name"], recovered / "workspace.sqlite3")
        self.client.__exit__(None, None, None)
        self.app = create_app(Settings(data_dir=recovered))
        self.client = TestClient(self.app, base_url="http://127.0.0.1:8090")
        self.client.__enter__()
        self.client.headers["X-Studio-Token"] = self.client.get("/api/session").json()["token"]
        self.run_job()
        self.assertEqual(self.client.get(asset["thumbnail_url"]).status_code, 200)
        self.assertTrue(self.client.get(f'/api/assets/{asset["id"]}').json()["favorite"])

    def test_new_assets_never_inherit_deleted_roots_thumbnails(self):
        (self.root / "海边笔记.txt").unlink()
        (self.root / "城市.md").unlink()
        self.run_job()
        original = self.client.get("/api/assets", params={"kind": "image"}).json()["items"][0]
        self.assertEqual(self.client.delete(f"/api/roots/{self.root_id}").status_code, 200)
        another = self.base / "另一目录"
        another.mkdir()
        (another / "损坏.png").write_bytes(b"not an image")
        self.root_id = self.client.post("/api/roots", json={"path": str(another)}).json()["id"]
        self.run_job()
        current = self.client.get("/api/assets").json()["items"][0]
        self.assertNotEqual(original["id"], current["id"])
        self.assertEqual(self.client.get(current["thumbnail_url"]).status_code, 404)

    def test_changed_corrupt_image_cannot_serve_previous_preview(self):
        self.run_job()
        asset = self.client.get("/api/assets", params={"kind": "image"}).json()["items"][0]
        Path(asset["path"]).write_bytes(b"changed corrupt image")
        self.run_job()
        self.assertEqual(self.client.get(asset["thumbnail_url"]).status_code, 404)

    def test_date_filter_uses_local_calendar_day(self):
        path = self.root / "清晨.txt"
        path.write_text("日期检查", encoding="utf-8")
        local_time = datetime(2026, 10, 19, 2, 0)
        os.utime(path, (local_time.timestamp(), local_time.timestamp()))
        self.run_job()
        result = self.client.get("/api/assets", params={"q": "清晨", "date_from": "2026-10-19", "date_to": "2026-10-19"}).json()
        self.assertEqual(result["total"], 1, result)
        previous = (local_time.date() - timedelta(days=1)).isoformat()
        result = self.client.get("/api/assets", params={"q": "清晨", "date_from": previous, "date_to": previous}).json()
        self.assertEqual(result["total"], 0)

    def test_nul_queries_and_non_ascii_token_are_rejected(self):
        response = self.client.post("/api/search", json={"mode": "document", "query": "hello\x00"})
        self.assertEqual(response.status_code, 422)
        response = self.client.post("/api/collections", json={"name": "invalid token"}, headers={b"x-studio-token": b"\xff"})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
