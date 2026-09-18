# 0001 初始化独立通知引擎与 REST 服务

- Plan: [0001](../plans/0001-bootstrap-engine.md)
- Type: feat
- Date: 2026-09-18

## Summary

从 AstrBot 插件剥离出与框架无关的通知聚合引擎，重写命令解析、轮询与推送为
REST API + 定时轮询 + webhook 的常驻服务，核心引擎与传输层通过 `Publisher` 协议解耦。

## Changes

- `core/models.py`：`Notice` 数据类、`SourceConfig`、`Parser` 类型。
- `core/sources.py`：移植 14 个来源配置 + `resolve_source`。
- `core/parsers.py`：移植 HTML 标题解析函数。
- `core/auth.py`：移植 SM2 登录与 Cookie 持久化，去掉 AstrBot 依赖，路径改由 `Settings` 提供。
- `core/fetcher.py`：移植 HTML/API 抓取、日期解析、会话失效重登、RSS 生成。
- `core/storage.py`：新增 SQLite 存储与 `INSERT OR IGNORE` 去重、查询、统计、清理。
- `core/engine.py`：新增轮询调度、`Publisher` 协议、推送年龄过滤。
- `core/rendering.py`：移植卡片渲染（matplotlib 可选）。
- `transport/api.py`：新增 FastAPI 路由（通知查询、来源、统计、触发抓取、RSS、卡片、订阅者 CRUD）。
- `transport/publishers.py`：新增 webhook 推送（HMAC-SHA256 可选）与订阅者 SQLite 存储。
- `config.py` / `cli.py`：TOML + 环境变量配置、argparse 入口（run / poll / sources / rss）。
- `cli.py`：修复 Windows 控制台 GBK 编码导致标题含零宽空格时 print 崩溃（流重设为 UTF-8）。
- 文档：`docs/` 索引、架构、规范、计划与变更日志；`AGENTS.md`、`README.md`。

## Verification

- `uv run ruff check .` -> All checks passed
- `uv run pytest -q` -> 13 passed
- `uv run muc-notice-engine sources` -> 列出 14 个来源
- `uv run muc-notice-engine poll --source muc_tzgg` -> 实际抓取到 16 条新通知
- 启动 `run --port 8099` 后：`GET /health` -> notice_count=79；`GET /api/sources` -> 14；`GET /api/notices?limit=3` -> count=3
- `import muc_notice_engine.core.*` 后 sys.modules 中无 fastapi/uvicorn/astrbot

## Breaking changes

不适用（新项目首次提交）。

## Follow-ups

- 门户 API 与选择器可能随学校改版失效，需定期校验。
- 可为 webhook 增加重试与退避策略。
- 如需 AI 摘要，另立计划，不要塞进 core。
