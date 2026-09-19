# 0011 OpenAPI 补全与服务自托管文档

- Status: done（2026-09-19 交付，见 [changelog/0011](../changelog/0011-openapi-and-hosted-docs.md)）
- Owner: MoMoJee
- Created: 2026-09-19
- Related: [0010](0010-agent-entry-llms-txt.md)、`transport/api.py`、`docs/conventions/docs.md`

## 背景与目标

`/docs`、`/redoc`、`/openapi.json` 只有接口形状：200 响应是
`{additionalProperties: true}`，404/409 未声明，语义规则在 markdown 里但只指向 GitHub
（生产机/国内网络不可达）。目标：

1. 用 Pydantic response model 描述所有 JSON 接口的响应字段，并声明 404/409/501 错误响应，
   让 Agent 直接吃 `/openapi.json`。
2. 服务自托管 markdown 语义文档：`GET /llm/{name}.md`（白名单），`/llms.txt` 首选指向它。
3. 在开发文档中写清规则：新增/修改接口必须带 response model 与错误响应；
   文档同步矩阵、检查清单同步更新。

## 方案

- `transport/schemas.py`（新）：`NoticeOut`、`NoticeListOut`、`HealthOut`、`SourceOut`、
  `StatsOut`、`SearchSiteOut`/`SearchResultOut`/`SearchHitOut`、`CheckOut`、`FilesOut`、
  `SubscriberOut`、`ErrorOut` 等；带字段 description。
- `transport/api.py`：
  - JSON 接口加 `response_model=`；文件/HTML 接口用 `responses=` 声明实际 content-type；
  - 统一 `ERROR_RESPONSES`（404/409/501，`ErrorOut`）；
  - 新增 `GET /llm/{doc_name}`：从部署目录 `docs/` 白名单读取（`transport/llm_docs.py`），
    缺失返回 404；`/llms.txt` 首选 `/llm/rest-api.md`、`/llm/aop-search.md`，GitHub 仅兜底。
- 不写库、不改 core、不加配置。

## 影响面

- core：无
- transport：`schemas.py`（新）、`llm_docs.py`（新）、`api.py`、`llm_txt.py`
- 配置：无
- 数据/schema：无
- 文档：
  - `docs/conventions/docs.md`：新增「OpenAPI 与自托管文档」专节 + 同步矩阵 + 检查清单；
  - `docs/guides/rest-api.md`：接口表加 `/llm/{name}.md`、说明 OpenAPI 必须用 response model；
  - `README.md`：接口表加一行；
  - `docs/index.md`、`AGENTS.md`：硬性规则/工作流补充；
- changelog：`docs/changelog/0011-openapi-and-hosted-docs.md`

## 风险与备选

- Pydantic 模型与 `to_dict()` 字段漂移：测试断言 openapi 组件与关键响应 schema。
- wheel 安装无 `docs/`：`/llm/*.md` 返回 404，`/llms.txt` 保留 GitHub 兜底。
- 不把长文塞进 OpenAPI description：接口形状进 schema，语义进 markdown。

## 验证方式

- `uv run pytest`：`/openapi.json` 含 `NoticeOut`/`NoticeListOut`/`SearchResultOut`，
  `/api/notices` 200 `$ref` 正确、404 已声明；`/llm/rest-api.md` 与 `/llm/aop-search.md`
  返回 markdown，未知文档 404；`/llms.txt` 指向服务路径。
- 生产机更新后 `curl .../llm/rest-api.md`、`curl .../openapi.json`。

## 任务拆分

- [x] `transport/schemas.py` + `api.py` response_model/错误响应
- [x] `transport/llm_docs.py` + `/llm/{name}.md` 路由 + `/llms.txt` 改指向
- [x] 测试
- [x] 文档：conventions / rest-api / README / index / AGENTS
- [x] changelog 0011 + 计划状态
