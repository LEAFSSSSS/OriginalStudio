import io
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from typing import Annotated

from fastapi import APIRouter, Query, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps

from .errors import StudioError
from .media import export_clip
from .paths import asset_path, generated_file
from .schemas import AnnotationPatch, BatchRequest, ClipRequest, Filters, SearchRequest


router = APIRouter(prefix="/api")


@router.get("/assets")
def assets(request: Request, filters: Annotated[Filters, Query()]):
    return request.app.state.repository.assets(filters.model_dump(mode="json"))


@router.post("/search")
def search(payload: SearchRequest, request: Request):
    return request.app.state.search.search(payload.model_dump(mode="json"))


@router.post("/assets/batch")
def batch(payload: BatchRequest, request: Request):
    return {"updated": request.app.state.repository.batch(payload.model_dump(exclude_none=True))}


@router.post("/references", status_code=201)
async def reference(file: UploadFile, request: Request):
    try:
        content = await file.read(16 * 1024 * 1024 + 1)
    finally:
        await file.close()
    if len(content) > 16 * 1024 * 1024:
        raise StudioError("参考图片最大 16 MiB", "reference_too_large", 413)
    try:
        with Image.open(io.BytesIO(content)) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            image.thumbnail((2048, 2048))
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise StudioError("无法读取这张参考图片，请使用 PNG、JPEG 或 WebP", "invalid_reference") from exc
    identifier = uuid4().hex
    path = request.app.state.settings.data_dir / "references" / f"{identifier}.jpg"
    image.save(path, "JPEG", quality=92)
    return {"id": identifier, "url": f"/api/references/{identifier}", "name": (file.filename or "参考图片")[:240]}


@router.get("/references/{identifier}")
def get_reference(identifier: str, request: Request):
    if not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise StudioError("参考图片不存在", "not_found", 404)
    return FileResponse(generated_file(request.app.state.settings.data_dir / "references", identifier + ".jpg"), media_type="image/jpeg")


@router.get("/assets/{identifier}")
def asset(identifier: int, request: Request):
    return request.app.state.repository.asset(identifier, detail=True)


@router.patch("/assets/{identifier}")
def patch_asset(identifier: int, payload: AnnotationPatch, request: Request):
    return request.app.state.repository.patch_asset(identifier, payload.model_dump(exclude_unset=True, exclude_none=True))


def source_path(request, identifier):
    repository = request.app.state.repository
    item = repository.asset(identifier)
    return item, asset_path(item, repository.root(item["root_id"]))


@router.get("/assets/{identifier}/thumbnail")
def asset_thumbnail(identifier: int, request: Request):
    item, _ = source_path(request, identifier)
    if item["kind"] == "document":
        raise StudioError("文档没有图片预览", "not_found", 404)
    if not item["metadata"].get("scan_complete"):
        raise StudioError("缩略图尚未建立，请重新扫描", "preview_pending", 404)
    path = generated_file(request.app.state.settings.data_dir / "thumbnails", f"{identifier}.jpg")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/assets/{identifier}/media")
def media(identifier: int, request: Request, download: bool = False):
    item, path = source_path(request, identifier)
    if download or item["kind"] == "document":
        return FileResponse(path, filename=path.name, content_disposition_type="attachment")
    return FileResponse(path)


@router.post("/assets/{identifier}/reveal")
def reveal(identifier: int, request: Request):
    _, path = source_path(request, identifier)
    if sys.platform == "win32":
        command = ["explorer.exe", "/select,", str(path)]
    elif sys.platform == "darwin":
        command = ["open", "-R", str(path)]
    else:
        command = ["xdg-open", str(path.parent)]
    try:
        subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    except OSError as exc:
        raise StudioError("无法打开文件管理器，请复制原文件路径", "reveal_failed", 503) from exc
    return {"ok": True}


@router.post("/assets/{identifier}/clip")
def clip(identifier: int, payload: ClipRequest, request: Request):
    item, path = source_path(request, identifier)
    if item["kind"] != "video":
        raise StudioError("只有视频可以导出片段")
    if item["duration"] is not None and payload.end > item["duration"] + 0.1:
        raise StudioError("结束时间超过视频时长")
    lock = request.app.state.clip_lock
    if not lock.acquire(blocking=False):
        raise StudioError("已有片段正在导出，请稍后再试", "export_busy", 409)
    try:
        return export_clip(path, request.app.state.settings.data_dir / "exports", payload.start, payload.end)
    finally:
        lock.release()
