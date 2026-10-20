"""Read local documents into searchable, position-aware chunks."""

import re
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from .errors import StudioError


@dataclass
class DocumentText:
    segments: list[dict]
    truncated: bool = False


class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "tr", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def decode_text(content: bytes) -> str:
    encodings = ["utf-8-sig", "gb18030"]
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.insert(0, "utf-16")
    for encoding in encodings:
        try:
            value = content.decode(encoding)
            if "\x00" not in value:
                return value
        except UnicodeError:
            continue
    raise StudioError("无法识别文本编码；请另存为 UTF-8 后重试", "unsupported_encoding")


def _chunks(text: str, **position):
    # A little overlap preserves phrase matches across chunk boundaries.
    if not text.strip():
        return []
    size, overlap = 5000, 120
    return [{"text": text[offset:offset + size], **position} for offset in range(0, len(text), size - overlap)]


def _docx(path: Path) -> list[dict]:
    parts = []
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if re.fullmatch(r"word/(document|header\d+|footer\d+|footnotes|endnotes)\.xml", name)]
        if "word/document.xml" not in names:
            raise StudioError("DOCX 缺少正文文件", "invalid_document")
        names.sort(key=lambda name: name != "word/document.xml")
        for name in names:
            info = archive.getinfo(name)
            if info.file_size > 64 * 1024 * 1024:
                raise StudioError("DOCX 解压后的正文过大", "document_too_large")
            content = archive.read(name)
            if b"<!ENTITY" in content.upper() or b"<!DOCTYPE" in content.upper():
                raise StudioError("不支持包含实体声明的文档", "invalid_document")
            xml = ElementTree.fromstring(content)
            namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            paragraphs = ["".join(node.itertext()) for node in xml.findall(".//w:p", namespace)]
            parts.append({"text": "\n".join(paragraphs)})
    return parts


def _pdf(path: Path) -> list[dict]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise StudioError("PDF 检索需要安装基础依赖：install.bat", "dependency_missing", 503) from exc
    reader = PdfReader(str(path), strict=False)
    if reader.is_encrypted and not reader.decrypt(""):
        raise StudioError("PDF 已加密，请提供已解密的副本", "encrypted_pdf")
    if len(reader.pages) > 2000:
        raise StudioError("PDF 超过 2000 页，请拆分后再建立索引", "document_too_large")
    return [{"text": page.extract_text() or "", "page": index + 1} for index, page in enumerate(reader.pages)]


def _timestamp(value: str) -> float:
    numbers = value.replace(",", ".").split(":")
    result = 0.0
    for number in numbers:
        result = result * 60 + float(number)
    return result


def _subtitles(text: str) -> list[dict]:
    pattern = r"(?m)^\s*((?:\d+:)?\d{2}:\d{2}[,.]\d{3})\s*-->\s*((?:\d+:)?\d{2}:\d{2}[,.]\d{3})[^\n]*\n(.*?)(?=\n\s*\n|\Z)"
    result = []
    for match in re.finditer(pattern, text.replace("\r\n", "\n"), re.DOTALL):
        content = re.sub(r"<[^>]*>", "", match[3]).strip()
        result.append({"text": content, "start": _timestamp(match[1]), "end": _timestamp(match[2])})
    return result or [{"text": text}]


def extract_document(path: Path, max_chars: int = 5_000_000) -> DocumentText:
    if path.stat().st_size > 64 * 1024 * 1024:
        raise StudioError("文档大于 64 MiB，请拆分后再索引", "document_too_large")
    extension = path.suffix.lower()
    try:
        if extension == ".pdf":
            pages = _pdf(path)
        elif extension == ".docx":
            pages = _docx(path)
        else:
            text = decode_text(path.read_bytes())
            if extension in {".html", ".htm"}:
                parser = PlainHTML()
                parser.feed(text)
                text = "".join(parser.parts)
            pages = _subtitles(text) if extension in {".srt", ".vtt"} else [{"text": text}]
    except StudioError:
        raise
    except Exception as exc:
        raise StudioError(f"文档读取失败：{type(exc).__name__}", "invalid_document") from exc
    segments, consumed, truncated = [], 0, False
    for page in pages:
        text = page["text"].replace("\x00", "")
        remaining = max_chars - consumed
        if len(text) > remaining:
            text, truncated = text[:remaining], True
        consumed += len(text)
        position = {key: value for key, value in page.items() if key != "text"}
        segments.extend(_chunks(text, **position))
        if consumed >= max_chars:
            truncated = truncated or page is not pages[-1]
            break
    return DocumentText(segments=segments, truncated=truncated)
