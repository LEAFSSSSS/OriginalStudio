import csv
import io
import json

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response

from .errors import StudioError
from .folders import browse_folders
from .paths import generated_file
from .repository import require_row
from .schemas import CollectionCreate, CollectionPatch, FolderBrowse, RootCreate


router = APIRouter(prefix="/api")


@router.get("/roots")
def roots(request: Request):
    items = request.app.state.repository.roots()
    return {"items": items, "total": len(items)}


@router.post("/roots", status_code=201)
def add_root(payload: RootCreate, request: Request):
    return request.app.state.repository.add_root(payload.path, payload.name)


@router.delete("/roots/{identifier}")
def remove_root(identifier: int, request: Request):
    request.app.state.repository.delete_root(identifier)
    return {"ok": True}


@router.post("/folders/pick")
def pick_folder():
    raise StudioError("目录选择器已更新，请刷新页面后重新点击浏览", "picker_updated", 409)


@router.post("/folders/list")
def list_folders(payload: FolderBrowse):
    return browse_folders(payload.path)


@router.get("/collections")
def collections(request: Request):
    items = request.app.state.repository.collections()
    return {"items": items, "total": len(items)}


@router.post("/collections", status_code=201)
def add_collection(payload: CollectionCreate, request: Request):
    return request.app.state.repository.save_collection(payload.model_dump())


@router.patch("/collections/{identifier}")
def edit_collection(identifier: int, payload: CollectionPatch, request: Request):
    return request.app.state.repository.save_collection(payload.model_dump(exclude_none=True, exclude_unset=True), identifier)


@router.delete("/collections/{identifier}")
def delete_collection(identifier: int, request: Request):
    request.app.state.repository.delete_collection(identifier)
    return {"ok": True}


def csv_cell(value):
    text = str(value) if value is not None else ""
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


@router.get("/collections/{identifier}/export.csv")
def export_collection(identifier: int, request: Request):
    repository = request.app.state.repository
    with repository.db.connect() as connection:
        require_row(connection, "collections", identifier)
        rows = connection.execute("SELECT a.*,ci.collected_at FROM collection_items ci JOIN assets a ON a.id=ci.asset_id WHERE ci.collection_id=? ORDER BY ci.collected_at,a.id", (identifier,)).fetchall()
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["name", "kind", "path", "available", "tags", "notes", "collected_at"])
    for row in rows:
        from pathlib import Path

        writer.writerow([csv_cell(row["name"]), row["kind"], csv_cell(row["path"]), Path(row["path"]).is_file(), csv_cell(", ".join(json.loads(row["tags"]))), csv_cell(row["notes"]), row["collected_at"]])
    return Response(output.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="collection-{identifier}.csv"'})


@router.post("/backups", status_code=201)
def backup(request: Request):
    return request.app.state.repository.db.backup()


@router.get("/backups/{name}")
def download_backup(name: str, request: Request):
    path = generated_file(request.app.state.settings.data_dir / "backups", name)
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@router.get("/exports/{name}")
def download_export(name: str, request: Request):
    path = generated_file(request.app.state.settings.data_dir / "exports", name)
    return FileResponse(path, filename=path.name, media_type="video/mp4")
