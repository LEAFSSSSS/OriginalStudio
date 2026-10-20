import os
from pathlib import Path

from .errors import StudioError


def path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def existing_root(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise StudioError("请输入完整的绝对目录路径")
    try:
        path = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise StudioError("目录不存在或无法访问", "folder_unavailable") from exc
    if not path.is_dir():
        raise StudioError("请选择一个文件夹")
    return path


def within(path: Path, root: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, RuntimeError):
        return False


def asset_path(asset: dict, root: dict) -> Path:
    path = Path(asset["path"])
    if not within(path, Path(root["path"])):
        raise StudioError("素材真实路径已离开注册目录，请重新扫描", "outside_root", 403)
    if not path.is_file():
        raise StudioError("原文件暂时不可用，请检查磁盘或重新扫描", "file_unavailable", 404)
    return path


def generated_file(directory: Path, name: str) -> Path:
    if not name or Path(name).name != name or any(char in name for char in "/\\:"):
        raise StudioError("文件名称无效", "not_found", 404)
    result = directory / name
    if not within(result, directory) or not result.is_file():
        raise StudioError("文件不存在", "not_found", 404)
    return result
