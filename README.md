# 拾序 · Original Studio

**用中文描述、参考图片或视频台词，找回电脑里的素材。**

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Release](https://img.shields.io/github/v/release/LEAFSSSSS/OriginalStudio)](https://github.com/LEAFSSSSS/OriginalStudio/releases/latest)
[![License](https://img.shields.io/github/license/LEAFSSSSS/OriginalStudio)](LICENSE)
[![Stars](https://img.shields.io/github/stars/LEAFSSSSS/OriginalStudio?style=flat)](https://github.com/LEAFSSSSS/OriginalStudio/stargazers)

[English](README_EN.md) · [下载源码包](https://github.com/LEAFSSSSS/OriginalStudio/releases/latest) · [完整使用说明](docs/usage.md) · [反馈问题](https://github.com/LEAFSSSSS/OriginalStudio/issues)

拾序是一个中文优先的本地素材工作台。把图片、视频、文档接入同一个素材库，用文件名、画面描述、参考图、文档正文或视频对白找到需要的内容，再用收藏、标签和灵感集归档。

![拾序工作区](docs/preview.png)

> **v0.1.1 · 早期预览**：当前交付为源码版，运行环境为 Windows + Python 3.11（64 位）。AI 索引可选安装。发布包不包含模型、虚拟环境或个人素材，尚未提供验证过的 EXE 安装包。

## 能做什么

| 你记得的线索 | 使用方式 |
| --- | --- |
| 记得文件名、标签或备注 | 文件名搜索，配合目录、类型和日期筛选 |
| 记得画面，例如“海边的日落” | 中文语义搜索图片和视频帧，需要先建立视觉索引 |
| 手里有一张参考图 | 上传参考图，寻找相近图片和视频片段 |
| 记得文档里的某句话 | 检索正文，返回上下文、PDF 页码或字幕位置 |
| 记得视频里说过什么 | 本地语音识别后检索台词，定位到时间点 |
| 想整理找到的素材 | 收藏、标签、备注、灵感集、CSV 清单和视频片段导出 |

- 素材保留在原文件夹，索引和整理记录存入本机 SQLite。
- 图文模型与语音模型按需加载，推理在本机执行；首次下载依赖和模型需要联网。
- 索引任务持久保存，支持停止、继续和失败重试。
- FastAPI 后端与原生 JavaScript 界面，无前端构建步骤或 CDN 依赖。

## 快速开始

### 1. 下载

安装 **Python 3.11（64 位）**，然后从 [Releases](https://github.com/LEAFSSSSS/OriginalStudio/releases/latest) 下载并解压 `OriginalStudio-source.zip`。也可以克隆仓库：

```powershell
git clone https://github.com/LEAFSSSSS/OriginalStudio.git
cd OriginalStudio
```

### 2. 安装并启动

在项目文件夹中依次运行，或直接双击相应文件：

```powershell
.\install.bat       # 基础依赖：文件名搜索、文档搜索、收藏整理
.\install-ai.bat    # 可选：图文搜索、视频处理和台词识别
.\run.bat           # 启动本机页面
```

默认地址为 `http://127.0.0.1:8090/`。程序仅监听本机；端口冲突时使用 `run.bat --port 8097`。

### 3. 连接自己的素材

1. 点击 **添加目录 → 浏览**，进入盘符与目标文件夹。
2. 点击 **选择此文件夹 → 连接目录**，执行扫描。
3. 文件名与文档正文扫描后即可检索。
4. 需要画面搜索时建立 **视觉索引**；需要对白搜索时建立 **台词索引**。
5. 把找到的素材加入收藏或灵感集。

[查看目录浏览界面](docs/folder-browser.png) · [模型与离线配置](docs/usage.md#模型与离线配置)

## 支持的素材

- **图片**：JPEG、PNG、WebP、GIF、BMP、TIFF 等，HEIC/HEIF 需要可选依赖。
- **视频**：MP4、MOV、MKV、AVI、WebM 等；解码和浏览器播放取决于具体编码。
- **文档**：TXT、Markdown、CSV、JSON、YAML、XML/HTML、SRT/VTT/ASS、DOCX、有文本层的 PDF。

文档检索不包含 OCR。台词识别读取音轨中的语音，不读取画面字幕。移动或重命名文件会产生新路径身份，当前版本不自动迁移原路径上的标签。

## 文档与参与

- [使用、备份与离线模型配置](docs/usage.md)
- [English API contract](docs/api.md)
- [更新日志](CHANGELOG.md)
- [贡献指南](CONTRIBUTING.md)
- [已有验证与限制](docs/verification.md)
- [第三方组件和模型来源](THIRD_PARTY_NOTICES.md)

欢迎提交可复现的问题、使用反馈和小范围改进。如果拾序帮你找回了一份素材，欢迎点一个 **Star**，也欢迎告诉我们你的使用场景。

## 许可证

Copyright © 2026 LEAFSSSSS。

本项目应用代码采用 **GNU GPL v3.0（GPL-3.0-only）**，完整条款见 [LICENSE](LICENSE)。第三方依赖、模型权重与 FFmpeg 的许可分别见 [第三方说明](THIRD_PARTY_NOTICES.md)。
