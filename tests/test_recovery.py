import hashlib
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from originalstudio.api import create_app
from originalstudio.settings import Settings
from originalstudio.indexing import JobCancelled


class ColorVision:
    signature = "test-color-encoder-v1"

    def load(self):
        pass

    def status(self):
        return {"installed": True, "loaded": True, "model": "synthetic-color", "message": "test adapter"}

    def encode_text(self, text):
        return [1.0, 0.0, 0.0] if "红" in text else [0.0, 0.0, 1.0]

    def encode_image(self, image):
        color = image.resize((1, 1)).getpixel((0, 0))
        return [1.0, 0.0, 0.0] if color[0] > color[2] else [0.0, 0.0, 1.0]


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "root"
        self.root.mkdir()
        self.settings = Settings(data_dir=self.base / "state")
        self.app = create_app(self.settings)
        self.client = TestClient(self.app, base_url="http://127.0.0.1:8090")
        self.client.__enter__()
        self.client.headers["X-Studio-Token"] = self.client.get("/api/session").json()["token"]
        self.root_id = self.client.post("/api/roots", json={"path": str(self.root)}).json()["id"]

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def wait_job(self, identifier):
        for _ in range(500):
            job = self.client.get(f"/api/jobs/{identifier}").json()
            if job["status"] not in {"queued", "running", "stopping"}:
                return job
            time.sleep(0.02)
        self.fail("job timeout")

    def create_job(self, operation):
        result = self.client.post("/api/jobs", json={"root_id": self.root_id, "operation": operation})
        self.assertEqual(result.status_code, 202, result.text)
        return result.json()["id"]

    def test_visual_index_reference_and_model_signature_isolation(self):
        for name, color in [("红.png", "red"), ("蓝.png", "blue")]:
            Image.new("RGB", (40, 40), color).save(self.root / name)
        original = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.root.iterdir()}
        self.wait_job(self.create_job("scan"))
        self.app.state.engines.vision = ColorVision()
        self.assertEqual(self.wait_job(self.create_job("visual"))["failed"], 0)
        response = self.client.post("/api/search", json={"mode": "semantic", "query": "红色", "min_score": 50}).json()
        self.assertEqual(response["total"], 1, response)
        self.assertEqual(response["items"][0]["name"], "红.png")
        self.assertEqual(response["items"][0]["score"], 100)
        self.app.state.engines.vision.signature = "different-model"
        result = self.client.post("/api/search", json={"mode": "semantic", "query": "红色"}).json()
        self.assertEqual(result["total"], 0)
        self.assertEqual(original, {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.root.iterdir()})

    def test_stop_then_resume_counts_once_and_preserves_metadata_after_restart(self):
        for index in range(24):
            (self.root / f"笔记-{index:02}.txt").write_text(f"第{index}份素材 海边日出", encoding="utf-8")
        original = self.app.state.jobs.indexer.process

        def slower(*args, **kwargs):
            time.sleep(0.025)
            return original(*args, **kwargs)

        self.app.state.jobs.indexer.process = slower
        identifier = self.create_job("scan")
        for _ in range(100):
            current = self.client.get(f"/api/jobs/{identifier}").json()
            if current["done"] >= 2:
                break
            time.sleep(0.02)
        self.client.post(f"/api/jobs/{identifier}/stop", json={})
        stopped = self.wait_job(identifier)
        self.assertEqual(stopped["status"], "stopped")
        self.assertLess(stopped["done"], stopped["total"])
        resumed = self.client.post(f"/api/jobs/{identifier}/resume", json={})
        self.assertEqual(resumed.status_code, 200, resumed.text)
        finished = self.wait_job(identifier)
        self.assertEqual(finished["status"], "completed")
        self.assertEqual((finished["done"], finished["total"]), (24, 24))
        asset = self.client.get("/api/assets").json()["items"][0]
        self.client.patch(f'/api/assets/{asset["id"]}', json={"favorite": True, "notes": "保存在磁盘"})
        self.client.__exit__(None, None, None)
        self.app = create_app(self.settings)
        self.client = TestClient(self.app, base_url="http://127.0.0.1:8090")
        self.client.__enter__()
        saved = self.client.get(f'/api/assets/{asset["id"]}').json()
        self.assertEqual(saved["notes"], "保存在磁盘")
        self.assertTrue(saved["favorite"])

    def test_running_jobs_recover_as_interrupted_and_require_explicit_resume(self):
        self.client.__exit__(None, None, None)
        settings = Settings(data_dir=self.base / "state", worker_enabled=False)
        self.app = create_app(settings)
        self.client = TestClient(self.app, base_url="http://127.0.0.1:8090")
        self.client.__enter__()
        self.client.headers["X-Studio-Token"] = self.client.get("/api/session").json()["token"]
        identifier = self.create_job("scan")
        with self.app.state.repository.db.connect(write=True) as connection:
            connection.execute("UPDATE jobs SET status='running' WHERE id=?", (identifier,))
        self.client.__exit__(None, None, None)
        self.app = create_app(settings)
        self.client = TestClient(self.app, base_url="http://127.0.0.1:8090")
        self.client.__enter__()
        self.assertEqual(self.client.get(f"/api/jobs/{identifier}").json()["status"], "interrupted")

    def test_media_resolution_blocks_indexed_path_outside_root(self):
        Image.new("RGB", (40, 40), "red").save(self.root / "safe.png")
        self.wait_job(self.create_job("scan"))
        asset = self.client.get("/api/assets").json()["items"][0]
        outside = self.base / "outside.txt"
        outside.write_text("must not be served", encoding="utf-8")
        with self.app.state.repository.db.connect(write=True) as connection:
            connection.execute("UPDATE assets SET path=? WHERE id=?", (str(outside), asset["id"]))
        response = self.client.get(f'/api/assets/{asset["id"]}/media')
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("must not be served", response.text)

    def test_cancel_after_fingerprint_resumes_document_body(self):
        path = self.root / "恢复.txt"
        root = self.app.state.repository.root(self.root_id)
        for content in ("首轮待恢复正文", "二轮更新后的正文"):
            path.write_text(content, encoding="utf-8")
            with self.assertRaises(JobCancelled):
                self.app.state.jobs.indexer.process(root, path, "scan", -1, lambda: True)
            finished = self.wait_job(self.create_job("scan"))
            self.assertEqual(finished["failed"], 0)
            result = self.client.post("/api/search", json={"mode": "document", "query": content}).json()
            self.assertEqual(result["total"], 1, result)

    def test_returning_file_with_unchanged_fingerprint_rebuilds_cleaned_text(self):
        path = self.root / "移回文档.txt"
        path.write_text("移回素材需要恢复全文索引", encoding="utf-8")
        self.wait_job(self.create_job("scan"))
        parked = self.base / "parked.txt"
        path.rename(parked)
        self.wait_job(self.create_job("cleanup"))
        parked.rename(path)
        self.wait_job(self.create_job("scan"))
        result = self.client.post("/api/search", json={"mode": "document", "query": "恢复全文"}).json()
        self.assertEqual(result["total"], 1, result)

    def test_cleanup_resolves_changed_links_using_stored_asset_identity(self):
        inner = self.root / "nested"
        inner.mkdir()
        (inner / "note.txt").write_text("原目录的可搜索正文", encoding="utf-8")
        self.wait_job(self.create_job("scan"))
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "note.txt").write_text("外部文件不应读取", encoding="utf-8")
        inner.rename(self.base / "parked")
        try:
            inner.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("This Windows account cannot create directory links")
        self.wait_job(self.create_job("cleanup"))
        result = self.client.post("/api/search", json={"mode": "document", "query": "可搜索正文"}).json()
        self.assertEqual(result["total"], 0, result)
        asset = self.client.get("/api/assets").json()["items"][0]
        self.assertFalse(asset["available"])


if __name__ == "__main__":
    unittest.main()
