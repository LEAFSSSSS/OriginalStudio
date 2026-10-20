from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*")
    @classmethod
    def no_nul_characters(cls, value):
        values = value if isinstance(value, list) else [value]
        if any(isinstance(item, str) and "\x00" in item for item in values):
            raise ValueError("输入不能包含 NUL 字符")
        return value


class RootCreate(Payload):
    path: str = Field(min_length=1, max_length=4096)
    name: str | None = Field(default=None, min_length=1, max_length=80)


class FolderBrowse(Payload):
    path: str = Field(default="", max_length=4096)


class Filters(Payload):
    root_id: int | None = Field(default=None, gt=0)
    kind: Literal["image", "video", "document"] | None = None
    q: str = Field(default="", max_length=1000)
    favorite: bool | None = None
    collection_id: int | None = Field(default=None, gt=0)
    tag: str | None = Field(default=None, max_length=48)
    folder: str | None = Field(default=None, max_length=4096)
    date_from: date | None = None
    date_to: date | None = None
    sort: Literal["recent", "name", "oldest"] = "recent"
    page: int = Field(default=1, ge=1, le=1_000_000)
    page_size: int = Field(default=36, ge=1, le=100)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("结束日期不能早于开始日期")
        if self.date_to == date.max:
            raise ValueError("结束日期必须早于 9999-12-31")
        return self


class SearchRequest(Filters):
    mode: Literal["filename", "semantic", "reference", "document", "dialogue"] = "filename"
    query: str = Field(default="", max_length=1000)
    reference_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    negative_query: str = Field(default="", max_length=1000)
    min_score: float = Field(default=0, ge=-100, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_query(self):
        if self.mode in {"semantic", "document", "dialogue"} and not self.query:
            raise ValueError("请输入搜索内容")
        if self.mode == "reference" and not self.reference_id:
            raise ValueError("请先添加参考图片")
        return self


class AnnotationPatch(Payload):
    favorite: bool | None = None
    tags: list[str] | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=4000)
    collection_ids: list[int] | None = Field(default=None, max_length=100)

    @field_validator("tags")
    @classmethod
    def valid_tags(cls, value):
        if value is not None and any(len(tag.strip()) > 48 for tag in value):
            raise ValueError("标签不能超过 48 个字符")
        return value

    @field_validator("collection_ids")
    @classmethod
    def positive_ids(cls, value):
        if value is not None and any(identifier < 1 for identifier in value):
            raise ValueError("收藏集编号无效")
        return value


class BatchRequest(Payload):
    ids: list[int] = Field(min_length=1, max_length=300)
    favorite: bool | None = None
    add_tags: list[str] = Field(default_factory=list, max_length=30)
    remove_tags: list[str] = Field(default_factory=list, max_length=30)
    collection_id: int | None = Field(default=None, gt=0)
    remove_collection: bool = False

    @field_validator("add_tags", "remove_tags")
    @classmethod
    def valid_tags(cls, value):
        if any(len(tag.strip()) > 48 for tag in value):
            raise ValueError("标签不能超过 48 个字符")
        return value


class CollectionCreate(Payload):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(default="#31a580", pattern=r"^#[0-9a-fA-F]{6}$")


class CollectionPatch(Payload):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class JobCreate(Payload):
    root_id: int = Field(gt=0)
    operation: Literal["scan", "visual", "documents", "transcripts", "cleanup"]
    retry_failed: bool = False


class ClipRequest(Payload):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_range(self):
        if not 0 < self.end - self.start <= 3600:
            raise ValueError("片段长度必须大于零且不超过一小时")
        return self
