"""Browse local directories without depending on a desktop dialog process."""

import os
import sys
from pathlib import Path

from .errors import StudioError
from .paths import existing_root


def drive_directories() -> list[dict]:
    if sys.platform != "win32":
        return [{"name": "文件系统", "path": "/"}]
    import ctypes
    from ctypes import wintypes

    logical_drives = ctypes.WinDLL("kernel32", use_last_error=True).GetLogicalDrives
    logical_drives.argtypes = []
    logical_drives.restype = wintypes.DWORD
    mask = logical_drives()
    if not mask:
        raise StudioError("无法读取本机盘符，请在上方填写完整目录路径", "folder_unavailable", 503)
    return [{"name": f"{chr(65 + index)}:\\", "path": f"{chr(65 + index)}:\\"} for index in range(26) if mask & (1 << index)]


def browse_folders(value: str = "") -> dict:
    if not value:
        return {"path": None, "parent": None, "items": drive_directories(), "truncated": False}
    path = existing_root(value)
    items, truncated = [], False
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    directory = entry.is_dir()
                except OSError:
                    continue
                if directory:
                    if len(items) == 1000:
                        truncated = True
                        break
                    items.append({"name": entry.name, "path": str(path / entry.name)})
    except OSError as exc:
        raise StudioError("无法读取这个文件夹，请检查权限或硬盘连接", "folder_unavailable", 403) from exc
    items.sort(key=lambda item: item["name"].casefold())
    return {"path": str(path), "parent": str(path.parent) if path.parent != path else "", "items": items, "truncated": truncated}
