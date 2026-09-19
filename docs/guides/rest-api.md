# REST API 参考与历史回填指南

服务默认监听 `http://127.0.0.1:8080`（部署机为 `8085`），启动方式见 [README](../../README.md)。
浏览器打开 `/docs` 有可交互的 Swagger UI；本文补充「参数语义、限制、怎么用」。

> 改了任何接口/参数/语义，必须同步本文件、`README.md` 的接口表、`/llms.txt`
> （`transport/llm_txt.py`）与响应模型（`transport/schemas.py`），见
> [conventions/docs.md](../conventions/docs.md) 的同步矩阵。
>
> **Agent 读文档的顺序**：`/llms.txt`（入口）→ `/openapi.json`（接口形状）→
> `/llm/rest-api.md`、`/llm/aop-search.md`（语义，本文件的服务自托管副本）。

## 认证

- 配置 `api_token`（`MNE_API_TOKEN`）后，除 `/`、`/health`、`/docs`、`/redoc`、`/openapi.json`、
  `/llms.txt`（及 `/llm.txt` 301 跳转）外的接口都需要 `Authorization: Bearer <token>`。
- 未配置 token 时全部公开。

```bash
curl -H 'Authorization: Bearer <token>' http://127.0.0.1:8080/api/notices
```

## 接口速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 引导页，链接到 `/docs` 与 `/llms.txt` |
| GET | `/llms.txt` | Agent 入口索引（只指路不复制文档；`/llm.txt` 301 跳转） |
| GET | `/llm/{name}.md` | 服务自托管的语义文档：`index.md`、`rest-api.md`、`aop-search.md`、`portal-notice-types.md` |
| GET | `/health` | 健康检查 + 归档队列状态（始终公开） |
| GET | `/api/sources` | 来源列表（32 个：21 公开 + 11 门户 type） |
| GET | `/api/notices` | 查询通知（`source`/`category`/`since`/`q`/`limit`/`offset`） |
| GET | `/api/notices/{id}` | 单条通知 |
| GET | `/api/notices/{id}/content` | 正文 HTML（已归档原文，或 2000 字预览） |
| GET | `/api/notices/{id}/content.zip` | 正文 + 附件打包 zip（需已归档） |
| GET | `/api/notices/{id}/files` | 落盘文件清单；`?name=` 下载单个文件 |
| POST | `/api/notices/{id}/archive` | 强制归档一条（绕过时间窗，202） |
| POST | `/api/check` | 立即抓取一轮；带 `type` 时按门户历史回填 |
| GET | `/api/stats` | 按来源统计（总数/已推送/最新时间） |
| GET | `/api/search/sites` | 可检索站点目录（AOP 智能搜索） |
| GET | `/api/search` | 远程全文检索（`site`/`q`/`match`/`exclude`/`scope`/`order`/`since`/`until`/`limit`） |
| GET | `/api/rss` | 返回生成的 RSS 文件 |
| GET | `/api/card.png` | 通知卡片图（需 `[render]` 可选依赖） |
| GET/POST/DELETE | `/api/subscribers` | webhook 订阅管理 |

## 通用约定

- **id 形态**：`source_key:sha1(source_key|link)`，入库后稳定；`external_id` 是门户
  `notice_id` 或公开源 URL slug，仅用于详情抓取与归档目录命名。
- **时间**：`published_at` 为 ISO 8601（`+08:00` 时区）；`since` 按它过滤。
- **排序**：`published_at DESC, source ASC`；分页用 `limit`（1–500，默认 50）+ `offset`。
- **错误**：404 不存在/未归档；409 归档功能被关；422 参数不合法（如订阅 url 非 http）。

## 查询与搜索

```bash
# 按来源与时间查
curl 'http://127.0.0.1:8080/api/notices?source=my_gsgg,my_jxtz&since=2026-09-01T00:00:00%2B08:00'

# 关键词搜索：匹配 标题 / 摘要 / 正文预览（不搜附件、不读归档 HTML）
curl 'http://127.0.0.1:8080/api/notices?q=%E6%99%BA%E6%85%A7%E6%A0%A1%E5%9B%AD'
```

- `q` 作用在数据库字段 `title` / `summary` / `content`（`content` 只有前 2000 字预览）；
  输入里的 `%`、`_` 按字面处理，不当通配符。
- 搜不到的词可能在附件或归档原文里——本接口不解析这些文件。

## 远程检索（AOP 智能搜索）

不查本地库，直接检索学校 VSB9 站点的全文索引（免登录）。站点目录见
`GET /api/search/sites`；协议细节、站点 owner 目录与实测限制见
[reference/aop-search.md](../reference/aop-search.md)。

| 参数 | 取值 | 说明 |
| --- | --- | --- |
| `site` | 站点 key（如 `xingong`、`lxy`） | 也接受 owner/host/名称；未知返回 404 |
| `q` | 关键词，空格分隔 | 必填 |
| `match` | `all` / `any`（默认 `any`） | 全部命中 / 任意命中 |
| `exclude` | 空格分隔 | **本地过滤**：标题/摘要命中任一词则剔除 |
| `scope` | `all` / `title` / `content` | 检索范围 |
| `order` | `date` / `score` | 按时间 / 相关度 |
| `since`、`until` | `YYYY-MM-DD` | 可只给一端 |
| `limit` | 1–100（默认 20） | 返回条数 |

```bash
curl 'http://127.0.0.1:8080/api/search?site=xingong&q=%E6%8E%A8%E5%85%8D&match=all&exclude=%E5%90%8D%E5%8D%95'
```

- 响应里 `remote_total` 是远端命中总数，`count` 是本地过滤/截断后实际返回数，
  `scanned` 是实际扫描的远端条数（含去重/排除前的记录）；
  `truncated=true` 表示扫描到上限（默认 200 条）仍未凑满 `limit`。
- 远端调用失败时 HTTP 仍为 200，但 `error` 非空、`hits` 可能为空/部分，按可降级处理。
- **不写库**：不新增通知、不入 RSS、不触发 webhook；需要沉淀时用公开源或 `POST /api/check` 回填。
- 站点高级搜索的「不包含」语法在远端不可靠，故由 `exclude` 本地实现；每次最多扫描
  200 条、页间约 0.2s 间隔，避免给对方站点压力。

## 正文与附件

正文有两态，先看归档再看预览：

1. **已归档**：`/content` 返回落盘原文（`content.html`，保留原始链接）。
2. **未归档**：返回 200 的预览页，响应头 `X-Muc-Content: preview`；连预览都没有则 404。

```bash
curl -o content.html http://127.0.0.1:8080/api/notices/<id>/content
curl -o content.zip  http://127.0.0.1:8080/api/notices/<id>/content.zip
curl http://127.0.0.1:8080/api/notices/<id>/files
curl -OJ 'http://127.0.0.1:8080/api/notices/<id>/files?name=01-%E5%90%8D%E5%8D%95.xlsx'
```

- `content.zip` 内含 `content.html`、`content.txt`、`meta.json` 与 `files/`；未归档返回 404。
- `/files?name=` 只按清单里的文件名精确匹配，且落在归档目录内（防路径穿越）。
- **访问 `/api/notices/{id}` 与上述内容接口会刷新 `last_access_at`**，归档淘汰按它排序；
  只浏览列表不会。被淘汰的文件可 `POST /api/notices/{id}/archive` 重新落盘。

## 归档语义（重要）

- 自动归档只处理落入时间窗的通知：

  ```
  cutoff = max(archive_floor_date, now - archive_window_days)
  ```

  两者**取较晚者**：`floor` 是最早下限（默认 `2026-08-31`），`window` 是滚动窗口
  （默认 90 天）。所以 2030 年运行只会自动归档近 90 天，不会从 2026 年拉起。
- 早于 cutoff 的历史通知**只入库、不自动归档**；需要时逐条
  `POST /api/notices/{id}/archive`（默认 `archive_enable=true`）。
- 归档总量默认上限 64GB（`archive_total_limit_gb`），超限按最近访问时间升序淘汰。
- 公开源 v1 只归档正文，不下载内联图片/附件；门户会下载附件与正文内联图。

## 抓取与回填

`POST /api/check` 请求体可选（字段见 Swagger）：

| 字段 | 作用 |
| --- | --- |
| `source` | 逗号分隔的 `source_key`，只抓这些来源 |
| `type` | 门户 type（1/3/4/5/6/8/9/10/11/32/36）；给了就走进历史回填，此时忽略 `source` |
| `from_page` / `to_page` | 门户页码区间（每页 20 条），默认 1/1 |
| `search_value` | 门户 `searchValue` 关键词，会匹配正文（标题不含也算） |
| `backfill` | 普通轮询是否按回填处理；默认 `true`（不推送） |

- **回填只保证入库**：默认不触发 webhook；`backfill_push=true` 时才推送。
- **首次启动的首轮抓取自动视为回填**（持久化标记，只发生一次）。
- 普通轮询返回 `{new_count, items}`（items 为本轮实际推送的通知）；
  回填返回 `{new_count, items, backfill: true}`（items 为新增入库的通知）。
- 归档仍受上面的时间窗限制。

## 历史回填指南

**目标场景**：拿到早于自动抓取范围的通知，例如「2026-03-26 之前的推免通知」。

**限制**：门户列表接口**不支持日期过滤**（实测多种日期参数均被忽略），只能用
「栏目 + 页数区间 + 关键词」逼近。

推荐步骤：

1. 定栏目：门户 11 个 type 的官方名与来源 key 见
   [reference/portal-notice-types.md](../reference/portal-notice-types.md)。
   推免在 `type=6`（遴选/名额）与 `type=11`（名单/细则）。
2. 定关键词：`searchValue` 会命中正文，比标题精确；先用小范围试探：

   ```bash
   curl -X POST http://127.0.0.1:8080/api/check \
     -H 'Content-Type: application/json' \
     -d '{"type":6,"from_page":1,"to_page":1,"search_value":"推免"}'
   ```

   > 注意：没有 dry-run，命中即入库。
3. 翻页：每次把 `to_page` 加一段（例如 1→10→20→…），观察返回条目的
   `published_at`；当整页都早于目标日期即可停止。

   ```bash
   curl -X POST http://127.0.0.1:8080/api/check \
     -H 'Content-Type: application/json' \
     -d '{"type":6,"from_page":5,"to_page":15,"search_value":"推免"}'
   ```
4. 核对入库量：`GET /health`（`notice_count`、`archive.pending`）与 `GET /api/stats`。
5. 需要正文/附件时逐条强制归档：

   ```bash
   curl -X POST http://127.0.0.1:8080/api/notices/<id>/archive
   ```
6. 检索：归档窗口之外的历史可用 `?q=` 搜摘要/正文预览，或 `?since=&source=` 翻列表。

**注意**：

- 回填很老的数据会进入数据库但默认不归档；不归档就没有正文/附件可下载。
- **保留期默认关闭**（`notice_retention_days=0`）。开启后按 **`first_seen_at`（入库时间）**
  清理数据库记录：回填的历史从入库时刻起算 N 天，不会被按发布日期误删
  （环境变量 `MNE_NOTICE_RETENTION_DAYS`）。
- 每页 20 条、页间有约 0.2s 礼貌间隔；一次请求 10 页约 200 条，别一次开几百页。
- 门户搜索只覆盖门户自身索引；搜不到就换关键词或改用公开源。

## 运维小抄

```bash
curl http://127.0.0.1:8080/health          # 队列/归档总量
curl http://127.0.0.1:8080/api/stats       # 每来源入库量
```

`/health.archive.pending > 0` 表示还有归档任务在跑（下载附件可能较慢）；
归档总量接近 `archive_total_limit_gb` 时，旧文件会按最近访问时间被淘汰。
