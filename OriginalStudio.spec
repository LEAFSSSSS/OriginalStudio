# -*- mode: python ; coding: utf-8 -*-
import importlib.util
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH)
datas = [(str(root / "static"), "static"), (str(root / "README.md"), "."), (str(root / "THIRD_PARTY_NOTICES.md"), ".")]
hiddenimports = ["originalstudio.api", "originalstudio.picker", "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.lifespan.on"]
binaries = []
if os.environ.get("STUDIO_BUILD_AI") == "1":
    for package in ("torch", "transformers", "tokenizers", "safetensors", "huggingface_hub", "cv2", "numpy", "faster_whisper", "ctranslate2", "onnxruntime", "av", "pillow_heif", "imageio_ffmpeg"):
        if importlib.util.find_spec(package) is None:
            raise RuntimeError(f"Missing AI build dependency: {package}; run install-ai.bat first")
        package_datas, package_binaries, package_imports = collect_all(package)
        datas += package_datas
        binaries += package_binaries
        hiddenimports += package_imports
model = os.environ.get("STUDIO_BUILD_MODEL")
if model:
    datas.append((model, "model"))
a = Analysis([str(root / "run.py")], pathex=[str(root)], binaries=binaries, datas=datas, hiddenimports=hiddenimports, excludes=["tkinter.test", "pytest", "IPython", "matplotlib", "tensorflow", "scipy"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="OriginalStudio", console=True, debug=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="OriginalStudio")
