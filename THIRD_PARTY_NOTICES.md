# 第三方组件与来源

本项目的应用模块、SQLite 结构、接口、任务流程和界面是在这次重写中创建的。`Material` 与 `MaterialStudio` 提供了功能需求参考；运行时不导入它们的应用代码，不读取其索引数据库，也不附带它们的前端资源。第三方模型和库有各自的作者与许可。

| 组件 | 用途 | 上游 |
| --- | --- | --- |
| FastAPI / Starlette / Pydantic | 本机接口、校验、文件响应 | https://github.com/fastapi/fastapi · https://github.com/Kludex/starlette · https://github.com/pydantic/pydantic |
| Uvicorn | ASGI 服务 | https://github.com/encode/uvicorn |
| SQLite | 索引、全文与资料存储 | https://www.sqlite.org/ |
| Pillow / pillow-heif | 图像预览与 HEIF 解码 | https://github.com/python-pillow/Pillow · https://github.com/bigcat88/pillow_heif |
| pypdf | PDF 文本提取 | https://github.com/py-pdf/pypdf |
| NumPy | 向量运算 | https://github.com/numpy/numpy |
| OpenCV | 视频抽帧与元数据 | https://github.com/opencv/opencv-python |
| PyTorch / Transformers / Tokenizers / safetensors / Hugging Face Hub | 模型推理与权重加载 | https://pytorch.org/ · https://github.com/huggingface/transformers |
| Chinese-CLIP base | 中文图文特征 | https://huggingface.co/OFA-Sys/chinese-clip-vit-base-patch16 |
| faster-whisper / CTranslate2 / ONNX Runtime / PyAV | 本地语音识别与解码 | https://github.com/SYSTRAN/faster-whisper · https://github.com/OpenNMT/CTranslate2 · https://github.com/microsoft/onnxruntime · https://github.com/PyAV-Org/PyAV |
| imageio-ffmpeg / FFmpeg | 视频片段导出 | https://github.com/imageio/imageio-ffmpeg · https://ffmpeg.org/ |
| PyInstaller（构建时） | Windows 目录版构建 | https://github.com/pyinstaller/pyinstaller |

Chinese-CLIP 模型卡标注 MIT；模型目录内保留相应许可。当前工作区的图文权重复制自机器上已有的同名第三方模型文件，应用业务代码没有从旧目录复制。源码 ZIP 不包含这些权重。

当前工作区的语音权重来自本机已有的 `Systran/faster-whisper-small` 缓存，快照为 `536b0662742c02347bc0e980a01041f333bce120`；来源记录保存在模型目录的 `MODEL_SOURCE.md`。上游模型页面为 https://huggingface.co/Systran/faster-whisper-small 。源码 ZIP 同样不包含语音权重。

`imageio-ffmpeg` 的 Python 包许可与所含 FFmpeg 程序、编解码器的许可分别记录。Windows 构建脚本会收集安装包中的许可文件并记录实际 FFmpeg 构建信息。分发目录应保留生成的 notices、对应组件许可和上游来源。

前端 SVG 图标和标识由本次界面代码绘制；字体使用操作系统已有字体，无远程字体请求。应用的对外发布许可由项目所有者指定。
