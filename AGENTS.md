# AGENTS.md

面向在此仓库工作的 AI/开发者。目标：**先计划、再实现、最后写变更日志**，并保持核心与传输解耦。

## 项目

中央民族大学多站点通知的聚合 / 去重 / 存储引擎，独立常驻服务，对外只有 REST + webhook。
数据抓取逻辑移植自 `reference/astrbot_plugin_MUC_Notices/`（只读参考，**不要修改**）。

## 命令

```bash
uv sync --extra dev                                  # 安装（Python >=3.11）
uv run muc-notice-engine run                          # 启动服务（REST + 轮询 + webhook）
uv run muc-notice-engine poll --source muc_tzgg       # 立即抓取一轮
uv run muc-notice-engine sources                      # 列出 14 个来源
uv run muc-notice-engine rss                          # 生成 RSS 文件
uv run ruff check . && uv run pytest                  # 提交前：先 lint 再测试
uv run pytest tests/test_storage.py::test_upsert_is_deduplicating   # 跑单个测试
```

配置：`config.example.toml` -> 复制为 `config.toml`（已 gitignore）。
环境变量（`MUC_USERNAME`、`MNE_API_TOKEN` 等）优先级更高，映射见 `src/muc_notice_engine/config.py`。

## 硬性架构边界

- `src/muc_notice_engine/core/` **禁止** import `transport`，禁止 import FastAPI/uvicorn。
- `transport/` 可以 import `core`。新增推送方式时实现 `core.engine.Publisher` 协议，不要改 core。
- 新增传输/推送消费者：在 `cli.cmd_run` 里 `engine.add_publisher(...)`。

## 改哪里

| 需求 | 文件 |
| --- | --- |
| 新增/修改来源 | `core/sources.py`（解析函数放 `core/parsers.py`） |
| 抓取/日期解析 | `core/fetcher.py` |
| 去重/查询/存储字段 | `core/storage.py` |
| 轮询/过滤/事件 | `core/engine.py` |
| REST 接口 | `transport/api.py` |
| webhook 负载/签名 | `transport/publishers.py` |
| 配置项 | `config.py` + `config.example.toml` |

## 工作流（必须遵守）

1. 功能开发前在 `docs/plans/NNNN-kebab-topic.md` 建计划（模板见 `docs/plans/README.md`）。
2. 实现并在 `docs/changelog/` 写同编号条目（模板见 `docs/changelog/README.md`）。
3. 提交信息格式与参考样例见 `docs/conventions/git.md`（以首次提交为基准）。
4. 模块边界或数据流变化时同步 `docs/architecture.md`；新增文档登记到 `docs/index.md`。

### 提交与推送权限

- **允许**：完成一项工作、或大型任务到达阶段点时，Agent 可以自主执行提交（commit）。
- **禁止**：未经开发者显式要求，**不得执行推送（push）**，不得创建远程分支/PR。
- 阶段点的定义由开发者在任务中给出；没有明确阶段点时按「一次逻辑变更一次提交」处理。

## 容易踩的坑

- `reference/` 是上游副本，仅作参考；改代码改 `src/`。
- `gmssl` 缺失或加密异常时门户登录会**退回明文密码**并记 warning（见 `core/auth.py`）。
- `matplotlib` 是可选依赖；未安装时 `/api/card.png` 返回 501，主流程不受影响。
- 公开源选择器与门户 API 参数均为逆向所得，学校改版会导致 `选择器未命中` 日志。
- SQLite 无迁移框架：改 schema 需在 changelog 写明人工处理方式。
- 不要提交 `config.toml`、`.env`、`data/`、`muc_cookies.json`。
