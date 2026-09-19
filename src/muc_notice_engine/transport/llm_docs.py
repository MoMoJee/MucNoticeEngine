"""服务自托管的 markdown 文档（`GET /llm/<name>.md`）。

Agent 常只能访问服务域名，GitHub 可能不可达；这里从部署目录 `docs/` 读取白名单文件，
只读、不解析。wheel 安装若不带 docs，则返回 404，由 /llms.txt 的 GitHub 链接兜底。
"""

from __future__ import annotations

from pathlib import Path

# src/muc_notice_engine/transport/llm_docs.py -> 项目根
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOCS_ROOT = PROJECT_ROOT / "docs"

# 对外可托管的文档白名单：URL 名 -> 仓库内路径
HOSTED_DOCS: dict[str, str] = {
    "index.md": "index.md",
    "rest-api.md": "guides/rest-api.md",
    "aop-search.md": "reference/aop-search.md",
    "portal-notice-types.md": "reference/portal-notice-types.md",
}


def load_doc(name: str) -> str | None:
    """返回白名单文档内容；未登记、文件缺失或路径异常时返回 None。"""
    relative = HOSTED_DOCS.get(name)
    if relative is None:
        return None
    path = (DOCS_ROOT / relative).resolve()
    if not path.is_file() or DOCS_ROOT.resolve() not in path.parents:
        return None
    return path.read_text(encoding="utf-8")
