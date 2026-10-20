"""Collect installed distribution license files without traversing user data."""

import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    target = Path(sys.argv[1]).resolve()
    target.mkdir(parents=True, exist_ok=True)
    packages = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        packages.append({"name": name, "version": distribution.version, "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License", ""), "homepage": distribution.metadata.get("Home-page", "")})
        for item in distribution.files or []:
            if any(part.lower().startswith(("license", "copying", "notice")) for part in item.parts):
                source = Path(distribution.locate_file(item))
                if source.is_file() and source.stat().st_size < 5_000_000:
                    destination = target / name / Path(*item.parts)
                    if not destination.resolve().is_relative_to(target):
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    (target / "packages.json").write_text(json.dumps(packages, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from originalstudio.media import ffmpeg_path
        executable = ffmpeg_path()
        if executable:
            result = subprocess.run([executable, "-version"], capture_output=True, timeout=20)
            (target / "ffmpeg-build.txt").write_bytes(result.stdout + result.stderr)
    except ImportError:
        pass


if __name__ == "__main__":
    main()
