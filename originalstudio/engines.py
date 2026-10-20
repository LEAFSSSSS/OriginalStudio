"""Optional inference adapters. Importing this module does not import ML runtimes."""

import hashlib
import importlib.util
import json
import threading
from array import array
from pathlib import Path

from .errors import StudioError
from .media import ffmpeg_path
from .settings import Settings


def installed(*packages: str) -> bool:
    return all(importlib.util.find_spec(package) is not None for package in packages)


def vector_bytes(values) -> bytes:
    return array("f", values).tobytes()


def bytes_vector(content: bytes) -> array:
    value = array("f")
    value.frombytes(content)
    return value


class VisionEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.lock = threading.RLock()
        self.model = None
        self.processor = None
        self.last_error = ""
        self.signature = ""

    def status(self) -> dict:
        available = installed("torch", "transformers", "numpy")
        message = "图文模型已加载，可进行本地视觉检索" if self.model is not None else "模型将在首次视觉索引或搜索时加载"
        return {"installed": available, "loaded": self.model is not None, "model": self.settings.model, "message": self.last_error or (message if available else "双击 install-ai.bat 安装本地图文与视频依赖")}

    def load(self):
        with self.lock:
            if self.model is not None:
                return
            if not self.status()["installed"]:
                raise StudioError("图文搜索依赖尚未安装，请先运行 install-ai.bat", "visual_dependency_missing", 503)
            try:
                import torch
                from transformers import ChineseCLIPModel, ChineseCLIPProcessor

                options = {"cache_dir": str(self.settings.data_dir / "models"), "local_files_only": self.settings.offline}
                processor = ChineseCLIPProcessor.from_pretrained(self.settings.model, **options)
                model = ChineseCLIPModel.from_pretrained(self.settings.model, **options).to(self.settings.device).eval()
                identity = {"model": self.settings.model, "revision": getattr(model.config, "_commit_hash", None), "config": model.config.to_dict()}
                local = Path(self.settings.model)
                if local.is_dir():
                    identity["files"] = [(file.name, file.stat().st_size, file.stat().st_mtime_ns) for file in sorted(local.iterdir()) if file.suffix in {".bin", ".safetensors", ".json", ".txt"}]
                signature = hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()
                self.processor, self.model, self.signature = processor, model, signature
                self.last_error = ""
                if self.settings.device == "cpu":
                    torch.set_num_threads(min(4, max(1, torch.get_num_threads())))
            except Exception as exc:
                self.last_error = "图文模型加载失败，请检查模型位置、网络或离线缓存"
                raise StudioError(self.last_error, "visual_model_unavailable", 503) from exc

    def _encode(self, *, text=None, image=None) -> list[float]:
        self.load()
        import torch

        with self.lock, torch.inference_mode():
            if text is not None:
                inputs = self.processor(text=[text], padding=True, truncation=True, max_length=52, return_tensors="pt").to(self.settings.device)
                feature = self.model.get_text_features(**inputs)
            else:
                inputs = self.processor(images=image, return_tensors="pt").to(self.settings.device)
                feature = self.model.get_image_features(**inputs)
            feature = feature / feature.norm(dim=-1, keepdim=True).clamp(min=1e-12)
            return feature[0].detach().cpu().tolist()

    def encode_text(self, text: str) -> list[float]:
        return self._encode(text=text)

    def encode_image(self, image) -> list[float]:
        return self._encode(image=image)


class SpeechEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.lock = threading.RLock()
        self.model = None
        self.last_error = ""

    def status(self) -> dict:
        available = installed("faster_whisper")
        message = "语音模型已加载，识别在本机执行" if self.model is not None else "首次建立台词索引时准备本地语音模型"
        return {"installed": available, "loaded": self.model is not None, "model": self.settings.whisper_model, "message": self.last_error or (message if available else "双击 install-ai.bat 安装本地语音识别依赖")}

    def load(self):
        with self.lock:
            if self.model is not None:
                return
            if not self.status()["installed"]:
                raise StudioError("台词索引依赖尚未安装，请先运行 install-ai.bat", "speech_dependency_missing", 503)
            try:
                from faster_whisper import WhisperModel

                self.model = WhisperModel(self.settings.whisper_model, device="cpu", compute_type="int8", cpu_threads=4, num_workers=1, download_root=str(self.settings.data_dir / "models" / "whisper"), local_files_only=self.settings.offline)
                self.last_error = ""
            except Exception as exc:
                self.last_error = "语音模型加载失败，请检查网络或本地模型路径"
                raise StudioError(self.last_error, "speech_model_unavailable", 503) from exc

    def transcribe(self, path: Path, cancelled) -> list[dict]:
        try:
            import av
            with av.open(str(path)) as container:
                if not container.streams.audio:
                    raise StudioError("视频没有音轨，已跳过台词索引", "no_audio")
        except StudioError:
            raise
        except ImportError as exc:
            raise StudioError("音轨解码依赖未安装，请运行 install-ai.bat", "dependency_missing", 503) from exc
        except Exception as exc:
            raise StudioError("无法读取视频音轨，请检查文件格式和完整性", "unreadable_audio") from exc
        self.load()
        with self.lock:
            segments, _ = self.model.transcribe(str(path), beam_size=3, vad_filter=True)
            results = []
            for segment in segments:
                if cancelled():
                    return []
                if segment.text.strip():
                    results.append({"text": segment.text.strip(), "start": segment.start, "end": segment.end})
            return results


class Engines:
    def __init__(self, settings: Settings):
        self.vision = VisionEngine(settings)
        self.speech = SpeechEngine(settings)

    def capabilities(self) -> dict:
        return {"visual": self.vision.status(), "transcripts": self.speech.status(), "video": {"installed": installed("cv2"), "message": "视频解码使用本地 OpenCV" if installed("cv2") else "视频扫描需要 install-ai.bat"}, "pdf": {"installed": installed("pypdf"), "message": "仅支持含文本层的 PDF"}, "export": {"installed": ffmpeg_path() is not None, "message": "本地片段导出已就绪" if ffmpeg_path() else "运行 install-ai.bat 安装片段导出依赖，也可提供 bin/ffmpeg.exe"}}
