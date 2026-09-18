# 0001 从 AstrBot 插件剥离独立通知引擎

- Status: done
- Owner: MoMoJee
- Created: 2026-09-18
- Related: `reference/astrbot_plugin_MUC_Notices/`

## 背景与目标

原项目 `astrbot_plugin_MUC_Notices` 把「通知抓取」和「AstrBot 聊天交互」耦合在一起。
目标是把与框架无关的抓取/存储/去重能力剥离为**独立常驻服务**：

- 只做信息聚合 + 存储 + 去重。
- 提供非常基础的 REST API，用请求收发信息。
- 重写原「命令参数解析 / 轮询 / 推送」为 REST + 定时轮询 + webhook。
- 传输层与核心引擎**高度解耦**。

验收标准：

1. `core/` 中不出现 AstrBot 或 FastAPI 依赖。
2. `muc-notice-engine poll` 能抓取公开源并打印新通知。
3. `muc-notice-engine run` 启动后 `/health`、`/api/notices` 可用。
4. 至少一个 webhook 订阅者能收到新通知。
5. 测试通过，文档含计划/变更日志/规范。

## 方案

- 保留并移植：`sources.py`、`parsers.py`、`auth_service.py`、`rss_service.py`、`notice_card.py`。
- 删除：`main.py`、`command_utils.py`、`subscription_store.py`（其去重职责由 SQLite 取代）及全部 AstrBot API。
- 新增：
  - `core/storage.py`：SQLite 去重与查询。
  - `core/engine.py`：轮询调度 + `Publisher` 协议。
  - `transport/api.py`：FastAPI 路由，取代聊天命令。
  - `transport/publishers.py`：webhook 推送 + 订阅者存储。
  - `config.py` / `cli.py`：TOML + 环境变量配置、argparse 入口。
- 丢弃原「每日 AI 速览」（依赖 LLM，不属于引擎职责；如需另立计划）。

## 影响面

- core：全新包，边界明确。
- transport：全新 API 与 webhook。
- 配置：`config.example.toml`、`.env.example`。
- 数据/schema：新增 `notices`、`subscribers` 两张 SQLite 表。

## 风险与备选

- 门户 API `type` 值、SM2 流程为逆向所得，可能随学校改版失效（接受，属维护成本）。
- 备选：保留 AstrBot KV 抽象。否决：引入无关复杂度，SQLite 更适合独立服务。
- 备选：同步 HTTP 框架（Flask）。否决：引擎本身是 async，FastAPI 更贴合。

## 验证方式

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest
uv run muc-notice-engine sources
uv run muc-notice-engine poll --source muc_tzgg
```

## 任务拆分

- [x] 复制原仓库到 `reference/` 作为只读参考
- [x] 移植 core（sources / parsers / auth / fetcher）
- [x] 实现 SQLite 存储与去重
- [x] 实现 engine 调度与 Publisher 协议
- [x] 实现 FastAPI + webhook + CLI
- [x] 测试与文档
