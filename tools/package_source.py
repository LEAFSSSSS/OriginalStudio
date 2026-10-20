"""Create a source-only delivery archive, excluding runtime and user data."""

import zipfile
import os
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    output = root / "release" / "OriginalStudio-source.zip"
    output.parent.mkdir(exist_ok=True)
    excluded = {".venv", "data", ".verification", "release", "build", "__pycache__", ".git"}
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for current, directories, files in os.walk(root):
            directories[:] = sorted(name for name in directories if name not in excluded)
            for name in sorted(files):
                path = Path(current) / name
                if name != ".env" and path.suffix not in {".pyc", ".log"}:
                    archive.write(path, Path("OriginalStudio") / path.relative_to(root))
    print(output)


if __name__ == "__main__":
    main()
