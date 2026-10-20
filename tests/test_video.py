import hashlib
import importlib.util
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from originalstudio.api import create_app
from originalstudio.media import ffmpeg_path, video_frames, video_info
from originalstudio.settings import Settings
from originalstudio.engines import SpeechEngine
from originalstudio.errors import StudioError


@unittest.skipUnless(importlib.util.find_spec("cv2") and ffmpeg_path(), "Requires optional video dependencies")
class VideoTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("av"), "Requires optional audio decoder")
    def test_silent_video_is_classified_before_model_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            video = base / "no-audio.mp4"
            subprocess.run([ffmpeg_path(), "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:size=96x64:rate=10:duration=0.3", "-c:v", "libx264", "-y", str(video)], check=True, capture_output=True)
            engine = SpeechEngine(Settings(data_dir=base / "state", whisper_model="missing-local-test-model", offline=True))
            with self.assertRaises(StudioError) as error:
                engine.transcribe(video, lambda: False)
            self.assertEqual(error.exception.code, "no_audio")
            self.assertIsNone(engine.model)

    def test_video_scan_range_sampling_and_clip_preserve_original(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "素材"
            root.mkdir()
            video = root / "颜色测试.mp4"
            subprocess.run([ffmpeg_path(), "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=10:duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(video)], check=True, capture_output=True)
            before = hashlib.sha256(video.read_bytes()).hexdigest()
            info, preview = video_info(video)
            self.assertAlmostEqual(info["duration"], 3, places=1)
            self.assertEqual(preview.width, 96)
            frames = list(video_frames(video, interval=0.5, max_frames=3, cancelled=lambda: False))
            self.assertEqual(len(frames), 3)
            self.assertGreaterEqual(frames[-1][0], 2)
            with TestClient(create_app(Settings(data_dir=base / "state")), base_url="http://127.0.0.1:8090") as client:
                client.headers["X-Studio-Token"] = client.get("/api/session").json()["token"]
                identifier = client.post("/api/roots", json={"path": str(root)}).json()["id"]
                job_id = client.post("/api/jobs", json={"root_id": identifier, "operation": "scan"}).json()["id"]
                for _ in range(200):
                    job = client.get(f"/api/jobs/{job_id}").json()
                    if job["status"] == "completed":
                        break
                    time.sleep(0.02)
                self.assertEqual(job["failed"], 0, job)
                asset = client.get("/api/assets").json()["items"][0]
                media = client.get(asset["media_url"], headers={"Range": "bytes=0-99"})
                self.assertEqual(media.status_code, 206)
                self.assertEqual(len(media.content), 100)
                clip = client.post(f'/api/assets/{asset["id"]}/clip', json={"start": 0.5, "end": 1.5})
                self.assertEqual(clip.status_code, 200, clip.text)
                output = client.get(clip.json()["url"])
                self.assertEqual(output.status_code, 200)
                self.assertIn(b"ftyp", output.content[:32])
                clipped, _ = video_info(base / "state" / "exports" / clip.json()["name"])
                self.assertAlmostEqual(clipped["duration"], 1, delta=0.15)
            self.assertEqual(hashlib.sha256(video.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
