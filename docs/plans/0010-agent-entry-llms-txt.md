# 0010 Agent 入口：/llms.txt 与首页引导

- Status: done（2026-09-19 交付，见 [changelog/0010](../changelog/0010-agent-entry-llms-txt.md)）
- Owner: MoMoJee
- Created: 2026-09-19
- Related: `transport/api.py`、`docs/guides/rest-api.md`、`docs/index.md`

## 背景与目标

外部 Agent/自动化调用方不看仓库文档就直接拼参数调用，容易误用
（例如用 `/api/notices` 当全网搜索、猜 `limit`、不知道 `/api/search` 的规则）。

目标：

1. 首页 `/` 顶部显著提示：**不了解站点规则时，首次调用前先读 `/llms.txt` 与接口文档**。
2. 新增 `GET /llms.txt`（llmstxt.org 约定）：给 Agent 的入口索引，
   只指向文档与关键接口，不重写文档内容；`/llm.txt` 301 跳转到它。
3. 文档同步：rest-api / README 接口表登记该路径。

## 方案

- `transport/llm_txt.py`：`llm_txt()` 返回纯文本入口索引，动态带来源数与站点数；
  列出「首次必读」「按任务查」「规则摘要」「其他」四块，链接用 GitHub blob + 仓库相对路径。
- `transport/api.py`：
  - `GET /llms.txt` -> `PlainTextResponse`；`GET /llm.txt` -> 301 到 `/llms.txt`（公开，不需要 token）；
  - `/` 首页增加 Agent 提示块，指向 `/llms.txt`、rest-api、`/openapi.json`、`/docs`。
- 不改 core、不改数据、不加配置。

## 影响面

- core：无
- transport：`api.py`、新增 `llm_txt.py`
- 配置：无
- 数据/schema：无
- 文档：`docs/guides/rest-api.md`、`README.md`（接口表各加一行）；
  `docs/conventions/docs.md` + `AGENTS.md` + `docs/index.md`（写明 `/llms.txt`
  与接口文档同级、必须随开发同步）
- changelog：`docs/changelog/0010-agent-entry-llms-txt.md`

## 风险与备选

- `/llms.txt` 内容会随接口变化过期：只保留稳定链接与一句话摘要，细则一律指向 docs。
- `/llm.txt` 用 301 兼容，避免 Agent 猜错路径直接 404。

## 验证方式

- `uv run pytest`：新增断言 `/` 含 `/llms.txt`；`/llms.txt` 返回 200、`text/plain`，
  且包含 `docs/guides/rest-api.md` 与 `docs/reference/aop-search.md`；`/llm.txt` 可跳转。
- 生产机更新后 `curl https://muc-notice.unischedulersuper.cn/llms.txt`。

## 任务拆分

- [x] `transport/llm_txt.py` + `api.py` 路由与首页提示
- [x] 测试
- [x] rest-api / README 接口表
- [x] 规范：conventions/AGENTS/index 写明 /llms.txt 必须随开发同步
- [x] changelog 0010 + 计划状态
