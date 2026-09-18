"""核心数据模型。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, TypedDict

from bs4 import Tag

Parser = Callable[[Tag], str]


class SourceConfig(TypedDict, total=False):
    """一个通知来源的配置。"""

    key: str
    name: str
    url: str
    selector: str
    parser: Parser
    category: str
    requires_auth: bool
    api_params: dict
    extra_urls: list[str]


@dataclass(slots=True)
class Notice:
    """规范化后的单条通知。"""

    id: str
    title: str
    link: str
    source: str
    source_key: str
    category: str
    date: str
    pub_date: str
    published_at: datetime
    external_id: str = ""
    summary: str = ""
    content: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["published_at"] = self.published_at.isoformat()
        return data


@dataclass(slots=True)
class Attachment:
    """从详情页发现的附件或内联图片。kind ∈ {file, image}。"""

    annex_id: str
    name: str
    url: str
    suffix: str = ""
    kind: str = "file"


@dataclass(slots=True)
class NoticeDetail:
    """一条通知的完整正文与附件（抓取结果，尚未落盘）。"""

    notice: Notice
    content_html: str
    attachments: list[Attachment]
    plain_text: str = ""
