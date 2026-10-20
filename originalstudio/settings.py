import os
import sys
from dataclasses import dataclass
from pathlib import Path


IMAGE_EXTENSIONS = frozenset(".jpg .jpeg .png .webp .gif .bmp .tif .tiff .heic .heif .avif".split())
VIDEO_EXTENSIONS = frozenset(".mp4 .mov .mkv .avi .webm .m4v .flv .wmv .mpg .mpeg".split())
DOCUMENT_EXTENSIONS = frozenset(".txt .md .markdown .csv .json .xml .html .htm .srt .vtt .ass .log .yaml .yml .docx .pdf".split())


def file_kind(path: Path) -> str | None:
    extension = path.suffix.lower()
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    if extension in DOCUMENT_EXTENSIONS:
        return "document"
    return None


def resource_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8090
    model: str = "OFA-Sys/chinese-clip-vit-base-patch16"
    device: str = "cpu"
    whisper_model: str = "small"
    offline: bool = False
    frame_interval: float = 3.0
    max_video_frames: int = 600
    max_document_chars: int = 5_000_000
    worker_enabled: bool = True

    def __post_init__(self):
        object.__setattr__(self, "data_dir", Path(self.data_dir).resolve())
        if self.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("本版本仅支持本机监听，请使用 127.0.0.1 或 ::1")
        if not 1 <= self.port <= 65535:
            raise ValueError("端口必须在 1 到 65535 之间")
        if self.frame_interval <= 0 or self.max_video_frames < 1 or self.max_document_chars < 1:
            raise ValueError("索引资源限制必须大于零")

    @classmethod
    def from_env(cls):
        # Only recognized ORIGINALSTUDIO_* options are loaded; process values win.
        configuration = resource_dir() / ".env"
        if configuration.is_file():
            for line in configuration.read_text(encoding="utf-8-sig").splitlines():
                key, separator, value = line.strip().partition("=")
                if separator and key.startswith("ORIGINALSTUDIO_"):
                    os.environ.setdefault(key, value.strip().strip("\"'"))
        default_dir = resource_dir() / "data"
        if getattr(sys, "frozen", False):
            default_dir = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "OriginalStudio"
        data_dir = Path(os.getenv("ORIGINALSTUDIO_DATA", str(default_dir)))
        local_model = data_dir / "models" / "vision"
        local_speech = data_dir / "models" / "speech"
        bundled_model = resource_dir() / "model"
        default_model = str(local_model) if (local_model / "config.json").is_file() else (str(bundled_model) if (bundled_model / "config.json").is_file() else cls.model)
        return cls(
            data_dir=data_dir,
            host=os.getenv("ORIGINALSTUDIO_HOST", "127.0.0.1"),
            port=int(os.getenv("ORIGINALSTUDIO_PORT", "8090")),
            model=os.getenv("ORIGINALSTUDIO_MODEL", default_model),
            device=os.getenv("ORIGINALSTUDIO_DEVICE", "cpu"),
            whisper_model=os.getenv("ORIGINALSTUDIO_WHISPER", str(local_speech) if (local_speech / "model.bin").is_file() else "small"),
            offline=os.getenv("ORIGINALSTUDIO_OFFLINE", "false").lower() == "true",
            frame_interval=float(os.getenv("ORIGINALSTUDIO_FRAME_INTERVAL", "3")),
            max_video_frames=int(os.getenv("ORIGINALSTUDIO_MAX_VIDEO_FRAMES", "600")),
        )
