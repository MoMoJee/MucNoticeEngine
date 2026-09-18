# 0009 AOP 智能搜索接口（远程检索）

- Status: done（2026-09-19 交付，见 [changelog/0009](../changelog/0009-aop-search-api.md)）
- Owner: MoMoJee
- Created: 2026-09-19
- Related: [0008](0008-lxy-xingong-sources.md)、`transport/api.py`、`docs/guides/rest-api.md`

## 背景与目标

理学院/信工栏目页接入后（0008），两站及全校 VSB9 站点还有一套免登录的
「智能搜索」JSON 接口。调研结论（2026-09-19，详见
[docs/reference/aop-search.md](../reference/aop-search.md) 待建）：

- `POST https://<任意 VSB9 站点>/aop_component/webber/search/search/search/queryPage`
  只需请求头 `Authorization: tourist` 与 `owner: <站点ID>`，无需登录、无 Cookie。
- 同一主机可查询**任意 owner**（已在 xingong 主机上验证 grs/eco/news 等）。
- owner 可从每个站点首页的 `_jsq_(...)` / `_showDynClickBatch(...)` 中提取；
  已枚举 34 个站点（教学科研单位 + 研究生院/人事处/财务处等），全部可查。
- 实测可用参数：关键词、AND/OR、时间（周/月/年/自定义）、排序（时间/相关度）、
  范围（标题/正文/全部）、栏目过滤、分页；单页上限 100 条，`page.current` 从 0 起。
- `advance`/`advanceKeyWord`（站点高级搜索）实测不可靠：
  `NOT` 不生效、两个关键词框的组合语义异常；“不包含”只能由我们本地过滤实现。

目标：**作为一个新的独立接口**接入远程检索，后续再考虑并入现有
`/api/notices?q=` 的本地搜索。本计划不改动轮询、存储与现有接口语义。

## 方案

### 1. 新模块 `core/aop.py`（纯 core，不依赖 FastAPI）

- `AopSite`（dataclass）：`key`（如 `xingong`）、`name`、`host`、`owner`。
- `AOP_SITES`：34 个站点快照（本次调研所得；生成/更新方法写入 reference 文档）。
- `AopSearchHit`：`title`、`link`、`published_at`、`column`、`column_name`、
  `owner`、`owner_name`、`snippet`、`external_id`。
- `AopSearchClient(host=SEARCH_HOST)`，`SEARCH_HOST = "https://www.muc.edu.cn"`：
  - `async search(site, keyword, *, match="any", exclude=None, scope="all",
    order="date", since=None, until=None, limit=20, scan_limit=200)`
  - 请求参数映射：

    | 我们的参数 | 远程字段 |
    | --- | --- |
    | `match=all` / `any` | `searchOperator=1` / `0`（空格分隔关键词） |
    | `scope=title`/`content`/`all` | `searchScope=1`/`2`/`3` |
    | `order=date`/`score` | `orderType="date"`/`"score"` |
    | `since`/`until` | `searchDateType="custom"` + `beginDate`/`endDate`（`YYYY-MM-DD`，可只给一端） |
    | `site` | `owner` + 请求头 `owner` |
    | `exclude` | **本地过滤**：剔除此串（空格分隔）中任一出现在标题/snippet 的结果 |

  - 解析：`collapseTitle` 取纯文本标题；`url` 为 `//` 协议相对时补 `https:`；
    `createDate` 转 `Asia/Shanghai`；按 `link` 去重（同题多栏目属不同文章）；
    单页请求 `size=100`，按 `page.current` 翻页，至多扫描 `scan_limit` 条。
  - 返回 `(hits, meta)`，`meta` 含 `remote_total`、`scanned`、`truncated`。
  - 失败策略：网络/JSON 异常返回空结果并记日志；接口不抛 500。

### 2. REST（`transport/api.py`，沿用现有 `auth` 依赖）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/search/sites` | 站点目录（key/name/host/owner） |
| GET | `/api/search` | 远程检索：`site` `q` `match` `exclude` `scope` `order` `since` `until` `limit`（1..100） |

响应示例：

```json
{
  "site": {"key": "xingong", "name": "信息工程学院", "owner": "1499287359"},
  "query": {"q": "推免", "match": "all", "scope": "all", "order": "date"},
  "remote_total": 26,
  "scanned": 26,
  "truncated": false,
  "count": 2,
  "hits": [
    {
      "title": "信息工程学院2027年接收推免生（第二批次）成绩公示",
      "link": "https://xingong.muc.edu.cn/info/1041/6535.htm",
      "published_at": "2026-09-18T20:51:01+08:00",
      "column": 1041,
      "column_name": "通知公告",
      "owner_name": "信息工程学院",
      "snippet": "…推免…",
      "external_id": "1499287359:1041:6535"
    }
  ]
}
```

语义说明（写进 rest-api）：

- `match=all` 对应“包含以下全部关键词”，`any` 对应“任意一个”；
- `exclude` 为**本地过滤**，`remote_total` 是远端总数，`count` 是过滤后返回数；
  `truncated=true` 表示扫描到 `scan_limit` 仍未凑满；
- `order=score` 为相关度排序（可能返回较旧文章）；
- 不写库、不入 RSS、不触发 webhook。

### 3. CLI（可选，便于手工验证）

`uv run muc-notice-engine search --site xingong --keyword 推免 --match all --exclude 名单 --limit 10`

### 4. 合并路径（本次不做）

后续可在 `/api/notices` 增加 `remote=1` 或 `source=remote:<site>`，
把本地库检索与远程检索合并；届时 `/api/search` 保持兼容。

## 影响面

- core：新增 `core/aop.py`
- transport：`api.py` 新增两个 GET 路由
- 配置：无（搜索主机为模块常量；如后续需要再入 Settings）
- 数据/schema：无（不写库）
- 文档（按 [同步矩阵](../conventions/docs.md#代码变更--文档同步矩阵)）：
  `docs/guides/rest-api.md`（接口与语义）、`README.md`（接口表）、
  新建 `docs/reference/aop-search.md`（协议/参数/owner 枚举方法）并登记 `docs/index.md`、
  `docs/plans/README.md`
- changelog：`docs/changelog/0009-aop-search-api.md`

## 风险与备选

- 非官方接口，字段/路径可能变化：解析失败降级为空结果并记 warning。
- 客户端排除导致分页与总数偏差：文档明示，`scan_limit` 上限约束成本。
- 远端对高频请求的限流未知：单次调用最多 `scan_limit/100` 页，页间加小延迟。
- owner 目录是快照：站点新增/更换 CMS 时需按 reference 文档方法刷新（后续可做自动发现）。
- 备选：解析 `soso.html` 页面（否决：Vue 客户端渲染，页面无结果数据）。

## 验证方式

- 单元：payload 映射（match/scope/order/时间）、响应解析（协议相对 URL、高亮标签剥离、
  日期）、exclude 过滤、去重与 `scan_limit`；transport 用 MockTransport 注入。
- 手工：`uv run muc-notice-engine search --site xingong --keyword 推免 --match all`
  与 `curl 'http://127.0.0.1:8080/api/search?site=lxy&q=推免&match=all&scope=title'`。
- 回归：`uv run ruff check .`、`uv run pytest`。

## 任务拆分

- [x] `core/aop.py`：站点目录 + 客户端 + 解析/过滤
- [x] `transport/api.py`：`/api/search`、`/api/search/sites`
- [x] CLI `search` 子命令
- [x] 测试（core + API）
- [x] `docs/reference/aop-search.md`、rest-api、README、index
- [x] changelog 0009 + 计划状态收尾
