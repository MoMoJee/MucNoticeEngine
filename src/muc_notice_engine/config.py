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
    "push_max_age_days",
    "notice_retention_days",
    "api_port",
    "webhook_timeout_seconds",
}
_BOOL_FIELDS = {"poll_on_start"}


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
    rss_title: str = "中央民族大学多站点通知聚合"

    # --- 轮询 / 保留 ---
    poll_interval_minutes: int = 240
    # 服务启动时是否立即抓取一次（否则等到第一个轮询周期）。
    poll_on_start: bool = True
    # 超过这个天数的「新」通知不推送（避免首次启动刷屏），但仍会入库。
    push_max_age_days: int = 30
    # 数据库中超过这个天数的记录会被清理；0 表示不清理。
    notice_retention_days: int = 180

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
            elif key in {"data_dir", "db_path"}:
                value = Path(value)
            kwargs[key] = value
        return cls(**kwargs)


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


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
    """合并 默认值 / config.toml / 环境变量 / 调用方 overrides。"""
    merged: dict[str, Any] = {}
    if config_path is None:
        config_path = Path(DEFAULT_CONFIG_NAME)
    merged.update(_load_toml(Path(config_path)))
    merged.update(_env_overrides())
    if overrides:
        merged.update(overrides)
    return Settings.from_dict(merged)
