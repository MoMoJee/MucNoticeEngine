"""运行配置。

优先级（从低到高）：代码默认值 < config.toml < 环境变量。
配置只描述「引擎怎么跑」，不包含任何传输层概念。
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_NAME = "config.toml"

# 环境变量 -> Settings 字段名
_ENV_MAP: dict[str, str] = {
    "MUC_USERNAME": "muc_username",
    "MUC_PASSWORD": "muc_password",
    "MNE_DATA_DIR": "data_dir",
    "MNE_POLL_INTERVAL_MINUTES": "poll_interval_minutes",
    "MNE_REQUEST_TIMEOUT_SECONDS": "request_timeout_seconds",
    "MNE_MAX_CONCURRENT_REQUESTS": "max_concurrent_requests",
    "MNE_RSS_MAX_ITEMS": "rss_max_items",
    "MNE_PORTAL_PAGE_LIMIT": "portal_page_limit",
    "MNE_PUSH_MAX_AGE_DAYS": "push_max_age_days",
    "MNE_NOTICE_RETENTION_DAYS": "notice_retention_days",
    "MNE_ARCHIVE_ENABLE": "archive_enable",
    "MNE_ARCHIVE_DIR": "archive_dir",
    "MNE_ARCHIVE_WORKERS": "archive_workers",
    "MNE_ARCHIVE_MAX_FILE_MB": "archive_max_file_mb",
    "MNE_ARCHIVE_MAX_PER_NOTICE": "archive_max_per_notice",
    "MNE_ARCHIVE_ENQUEUE_LIMIT_PER_POLL": "archive_enqueue_limit_per_poll",
    "MNE_ARCHIVE_WINDOW_DAYS": "archive_window_days",
    "MNE_ARCHIVE_FLOOR_DATE": "archive_floor_date",
    "MNE_ARCHIVE_TOTAL_LIMIT_GB": "archive_total_limit_gb",
    "MNE_BACKFILL_PUSH": "backfill_push",
    "MNE_API_HOST": "api_host",
    "MNE_API_PORT": "api_port",
    "MNE_API_TOKEN": "api_token",
    "MNE_DB_PATH": "db_path",
}

_INT_FIELDS = {
    "poll_interval_minutes",
    "request_timeout_seconds",
    "max_concurrent_requests",
    "rss_max_items",
    "portal_page_limit",
    "push_max_age_days",
    "notice_retention_days",
    "api_port",
    "webhook_timeout_seconds",
    "archive_workers",
    "archive_max_file_mb",
    "archive_max_per_notice",
    "archive_enqueue_limit_per_poll",
    "archive_window_days",
    "archive_total_limit_gb",
}
_BOOL_FIELDS = {"poll_on_start", "archive_enable", "backfill_push"}


@dataclass
class Settings:
    """引擎 + API 的全部可配置项。"""

    # --- 存储 / 路径 ---
    data_dir: Path = Path("data")
    db_path: Path = Path("data") / "muc_notice.db"
    rss_file: str = "muc_notice_rss.xml"

    # --- 抓取 ---
    request_timeout_seconds: int = 20
    max_concurrent_requests: int = 5
    rss_max_items: int = 150
    # 门户每个 type 每轮抓取的最大页数（每页 20 条）。
    portal_page_limit: int = 3
    rss_title: str = "中央民族大学多站点通知聚合"

    # --- 轮询 / 保留 ---
    poll_interval_minutes: int = 240
    # 服务启动时是否立即抓取一次（否则等到第一个轮询周期）。
    poll_on_start: bool = True
    # 超过这个天数的「新」通知不推送（避免首次启动刷屏），但仍会入库。
    push_max_age_days: int = 30
    # 数据库记录保留期：按 first_seen_at（入库时间）清理，回填的历史从入库时刻起算。
    # 0（默认）表示不清理；归档文件的大小上限见 archive_total_limit_gb。
    notice_retention_days: int = 0

    # --- 正文 / 附件归档 ---
    # 开关；关闭后新通知只入库，不抓正文不下载附件。
    archive_enable: bool = True
    archive_dir: Path = Path("data") / "archive"
    # 后台下载 worker 数；单轮最多入队多少条新通知归档。
    archive_workers: int = 2
    archive_enqueue_limit_per_poll: int = 50
    # 单文件、单通知附件数量上限。
    archive_max_file_mb: int = 50
    archive_max_per_notice: int = 50
    # 自动归档时间窗：published_at >= max(floor_date, now - window_days)。
    archive_window_days: int = 90
    archive_floor_date: str = "2026-08-31"
    # 归档目录总大小上限（GB），超限按 last_access_at 升序淘汰。
    archive_total_limit_gb: int = 64
    # 首轮回填/手动回填是否也触发 webhook 推送。
    backfill_push: bool = False

    # --- 门户认证（可选）---
    muc_username: str = ""
    muc_password: str = ""

    # --- REST API ---
    api_host: str = "127.0.0.1"
    api_port: int = 8080
    # 非空时，/api/* 需要 Authorization: Bearer <token>。/health 始终公开。
    api_token: str = ""

    # --- Webhook 推送 ---
    webhook_timeout_seconds: int = 10

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        # db_path 允许单独指定；未指定时跟随 data_dir
        self.db_path = Path(self.db_path)
        if self.db_path == Path("data") / "muc_notice.db":
            self.db_path = self.data_dir / "muc_notice.db"
        # archive_dir 同理
        self.archive_dir = Path(self.archive_dir)
        if self.archive_dir == Path("data") / "archive":
            self.archive_dir = self.data_dir / "archive"

    @property
    def rss_file_path(self) -> Path:
        return self.data_dir / self.rss_file

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Settings:
        valid = {f.name for f in fields(cls)}
        kwargs: dict[str, Any] = {}
        for key, value in raw.items():
            if key not in valid:
                continue
            if key in _INT_FIELDS:
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
            elif key in _BOOL_FIELDS:
                if isinstance(value, str):
                    value = value.strip().lower() in ("1", "true", "yes", "on")
                else:
                    value = bool(value)
            elif key in {"data_dir", "db_path", "archive_dir"}:
                value = Path(value)
            kwargs[key] = value
        return cls(**kwargs)


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _load_dotenv(path: Path) -> None:
    """把 .env 里的键值读进 os.environ，但不覆盖已存在的真实环境变量。"""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env_overrides() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for env_name, field_name in _ENV_MAP.items():
        value = os.environ.get(env_name)
        if value not in (None, ""):
            result[field_name] = value
    return result


def load_settings(
    config_path: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> Settings:
    """合并 默认值 / config.toml / .env / 环境变量 / 调用方 overrides。"""
    if config_path is None:
        config_path = Path(DEFAULT_CONFIG_NAME)
    config_path = Path(config_path)

    # .env 优先级高于 config.toml、低于真实环境变量。
    _load_dotenv(Path(".env"))
    if config_path.parent != Path("."):
        _load_dotenv(config_path.parent / ".env")

    merged: dict[str, Any] = {}
    merged.update(_load_toml(config_path))
    merged.update(_env_overrides())
    if overrides:
        merged.update(overrides)
    return Settings.from_dict(merged)
