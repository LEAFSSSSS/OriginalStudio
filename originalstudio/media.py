import math
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import StudioError
from .settings import resource_dir


def image_info(path: Path) -> tuple[dict, Image.Image]:
    if path.suffix.lower() in {".heic", ".heif"}:
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError as exc:
            raise StudioError("HEIC 格式需要安装 pillow-heif", "dependency_missing", 503) from exc
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            return {"width": image.width, "height": image.height}, image
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise StudioError("无法解码此图片或图片尺寸超出限制", "unreadable_image") from exc


def thumbnail(image: Image.Image, target: Path):
    preview = image.copy()
    preview.thumbnail((640, 480))
    temporary = target.with_suffix(".pending.jpg")
    preview.convert("RGB").save(temporary, "JPEG", quality=83, optimize=True)
    temporary.replace(target)


def open_video(path: Path):
    try:
        import cv2
    except ImportError as exc:
        raise StudioError("视频功能需要安装可选依赖：install-ai.bat", "dependency_missing", 503) from exc
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        raise StudioError("视频无法打开，请检查格式和文件完整性", "unreadable_video")
    return cv2, capture


def video_info(path: Path) -> tuple[dict, Image.Image | None]:
    cv2, capture = open_video(path)
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frames = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if not math.isfinite(fps) or fps <= 0 or not math.isfinite(frames):
            raise StudioError("视频帧率或时长无效", "unreadable_video")
        metadata = {"fps": fps, "duration": frames / fps, "width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))}
        capture.set(cv2.CAP_PROP_POS_MSEC, min(1.0, metadata["duration"] / 3) * 1000)
        success, frame = capture.read()
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)) if success else None
        return metadata, image
    finally:
        capture.release()


def video_frames(path: Path, interval: float, max_frames: int, cancelled):
    cv2, capture = open_video(path)
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if not math.isfinite(fps) or fps <= 0 or not math.isfinite(count) or count <= 0:
            raise StudioError("视频时长无效", "unreadable_video")
        duration = count / fps
        # Long clips are sampled across their full duration, rather than truncated.
        step = max(interval, duration / max_frames)
        for index in range(min(max_frames, max(1, math.ceil(duration / step)))):
            if cancelled():
                return
            position = index * step
            capture.set(cv2.CAP_PROP_POS_MSEC, position * 1000)
            success, frame = capture.read()
            if success:
                yield position, Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    finally:
        capture.release()


@lru_cache(maxsize=1)
def ffmpeg_path() -> str | None:
    bundled = resource_dir() / "bin" / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    executable = str(bundled) if bundled.is_file() else shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return None


def export_clip(source: Path, directory: Path, start: float, end: float) -> dict:
    executable = ffmpeg_path()
    if not executable:
        raise StudioError("片段导出依赖尚未安装，请运行 install-ai.bat 或提供 bin/ffmpeg.exe", "ffmpeg_missing", 503)
    name = f"clip-{uuid4().hex}.mp4"
    target = directory / name
    command = [executable, "-nostdin", "-hide_banner", "-loglevel", "error", "-ss", str(start), "-i", str(source), "-t", str(end - start), "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-movflags", "+faststart", "-y", str(target)]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=600, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    except (subprocess.SubprocessError, OSError) as exc:
        target.unlink(missing_ok=True)
        raise StudioError("导出失败：请检查 FFmpeg 编码能力、源文件及剩余磁盘空间", "clip_export_failed", 422) from exc
    return {"name": name, "url": f"/api/exports/{name}"}
