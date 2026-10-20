import tempfile
import unittest
import zipfile
from pathlib import Path

from originalstudio.documents import extract_document


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_gb18030_and_literal_html_text(self):
        path = self.directory / "中文.txt"
        path.write_bytes("中文目录中的海边素材".encode("gb18030"))
        result = extract_document(path, 1000)
        self.assertIn("海边", "".join(part["text"] for part in result.segments))
        path = self.directory / "网页.html"
        path.write_text("<h1>标题</h1><script>private()</script><p>正文&amp;内容</p>", encoding="utf-8")
        result = extract_document(path, 1000)
        text = "".join(part["text"] for part in result.segments)
        self.assertIn("正文&内容", text)
        self.assertNotIn("private", text)

    def test_docx_and_length_coverage(self):
        path = self.directory / "文稿.docx"
        with zipfile.ZipFile(path, "w") as document:
            document.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>第一段 海边日出</w:t></w:r></w:p></w:body></w:document>')
        result = extract_document(path, 6)
        self.assertTrue(result.truncated)
        self.assertEqual(len("".join(part["text"] for part in result.segments)), 6)

    def test_subtitle_segments_have_real_timestamps(self):
        path = self.directory / "字幕.srt"
        path.write_text("1\n00:00:01,500 --> 00:00:03,250\n这是海边\n\n2\n00:01:00,000 --> 00:01:02,000\n第二句\n", encoding="utf-8")
        result = extract_document(path, 1000)
        self.assertEqual(result.segments[0]["start"], 1.5)
        self.assertEqual(result.segments[0]["end"], 3.25)
        self.assertEqual(result.segments[1]["text"], "第二句")


if __name__ == "__main__":
    unittest.main()
