# 30 秒真实界面步骤演示

[观看 MP4](https://github.com/LEAFSSSSS/OriginalStudio/releases/download/v0.1.1/OriginalStudio-demo.mp4) · [下载示例素材包](https://github.com/LEAFSSSSS/OriginalStudio/releases/download/v0.1.1/OriginalStudio-demo-materials.zip) · [SHA-256 校验文件](https://github.com/LEAFSSSSS/OriginalStudio/releases/download/v0.1.1/OriginalStudio-demo.sha256)

![拾序：找图、整理与文档检索](demo.gif)

制作日期：2026-10-21。应用版本：v0.1.1，Windows / CPU，本地 Chinese-CLIP 模型。

动图和视频由应用实际运行时的六张截图按步骤编排而成，配有说明字幕，并非连续录屏。画面没有替换搜索结果或修改相似分。扫描和视觉索引在截图前已完成，步骤停留时间经过编排，不能用来推断安装、建索引或搜索速度。

三张示例图片由内置 **imagegen** 工具生成，属于虚构场景，并非实拍。示例文档由本项目编写；演示在独立的示例工作区进行。这里的小样本展示操作流程，不代表真实素材库的检索准确率。

## 演示流程

| 视频时间 | 实际操作 |
| --- | --- |
| 00:00–00:05 | 浏览包含三张图片和一份文档的素材库 |
| 00:05–00:09 | 在语义搜索中输入“湖边的帐篷” |
| 00:09–00:15 | 查看本机模型返回的三个图片结果 |
| 00:15–00:21 | 为首个结果添加收藏、标签、笔记和灵感集 |
| 00:21–00:25 | 查看“周末灵感”中的已整理素材 |
| 00:25–00:30 | 用文档内容搜索“露营”，查看命中的正文 |

[查看完整静态截图](demo-preview.jpg)

## 复现这段演示

1. 按 [首页安装说明](../README.md#快速开始) 安装并启动拾序。语义搜索需要 `install-ai.bat` 和图文模型；仅体验文档检索时可先安装基础依赖。
2. 下载并解压上方的 `OriginalStudio-demo-materials.zip`，包内包含许可和操作说明。
3. 在拾序中点击 **添加目录 → 浏览**，选择包内的 **materials** 文件夹，再连接并扫描。
4. 扫描完成后，从 **建立索引** 中为该目录建立 **视觉索引**，等待任务完成。首次准备模型可能需要较长时间和联网下载，也可以配置 [本地模型](usage.md#模型与离线配置)。
5. 选择 **语义搜索**，输入 **湖边的帐篷**，点击搜索。示例录制时帐篷图片排在首位；不同模型版本与运行配置可能得到不同分数。
6. 打开图片，勾选收藏，输入标签 `露营, 周末`，添加笔记，并保存到自己创建的“周末灵感”灵感集。
7. 返回全部素材，选择 **文档内容**，输入 **露营**，可以找到 `周末创作计划.md` 中的内容。

搜索框中的相似分是余弦相似度乘以 100，不是匹配概率。示例包只包含图片与文档；视频对白和片段导出请使用自己有权使用的视频素材体验。

## 示例文件

| 文件 | 内容 | SHA-256 |
| --- | --- | --- |
| `materials/IMG_1042.png` | 湖泊、山林与帐篷 | `5a9c6387a769f4447d15babe295aeb06d38021f49be1470995893a3a288f5a29` |
| `materials/IMG_2086.png` | 咖啡、笔记本与窗边光线 | `37ea96c4be5d5bc309075f7bc8a0d5b7a87fd172bdcc57c50373559026bfad3e` |
| `materials/IMG_3091.png` | 海浪、礁石与日落 | `60624d603e4d53b45c960b744ac343909d9fcb0fe257197f691840375340c601` |
| `materials/周末创作计划.md` | 为本次演示编写的短文档 | `b3208f8ba0a4d67ba2a2fc3e18235bec6847a2e9ee40fa6986541cf48fa6d6b0` |

示例包按 **GPL-3.0-only** 提供，完整条款随包附带。示例图片和文档保存在发布页的素材 ZIP 中；模型、索引数据库和运行环境不在包内。

## 图片生成提示词

三张图片均使用内置 imagegen 的新图生成模式，背景不透明，没有参考图片。下面保留本次使用的完整提示词，便于了解素材来源；再次生成的画面不保证相同。

### IMG_1042.png

```text
Use case: photorealistic-natural. Asset type: clearly disclosed AI-generated sample material for an open-source local media search demo. A single small ochre camping tent beside a perfectly calm alpine lake, dark pine forest and layered blue mountains, early morning mist. Natural editorial outdoor photograph, no people, landscape composition, realistic materials, soft dawn light. No UI, no text, no letters, no logo, no watermark. Produce one clean standalone image.
```

### IMG_2086.png

```text
Use case: photorealistic-natural. Asset type: clearly disclosed AI-generated sample material for an open-source local media search demo. A white ceramic cup of black coffee beside an open notebook on a warm wooden desk, a small green plant, soft window light, calm morning atmosphere. Natural editorial still-life photograph, landscape composition, realistic textures. No UI, no text, no letters, no logo, no watermark. Produce one clean standalone image.
```

### IMG_3091.png

```text
Use case: photorealistic-natural. Asset type: clearly disclosed AI-generated sample material for an open-source local media search demo. Ocean waves and a pale sandy coast at sunset, orange sun low on the horizon, dark coastal rocks in the foreground, warm sky reflected on blue water. Natural editorial travel photograph, landscape composition, no people. No UI, no text, no letters, no logo, no watermark. Produce one clean standalone image.
```

## English

This is a 30-second sequence assembled from actual v0.1.1 UI screenshots, with captions. It is not a continuous screen recording or a performance benchmark. The three sample images were generated using the built-in imagegen tool. Indexes were prepared before capture; no search results or scores were replaced.

Download the sample ZIP and connect its `materials` folder. Scan it, build a visual index, then search **湖边的帐篷** in **语义搜索**. Open a result to add favorites, tags, notes, and a collection. Search **露营** in **文档内容** to find the sample document. The kit contains the four files listed above, instructions, and the GPL-3.0-only license; models and databases are separate.
