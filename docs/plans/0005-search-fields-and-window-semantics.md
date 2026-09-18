# 0005 查询搜索字段扩展与归档时间窗语义澄清

- Status: draft
- Owner: MoMoJee
- Created: 2026-09-19
- Related: [0004-portal-pagination-attachments.md](0004-portal-pagination-attachments.md)、`core/storage.py`、`core/engine.py`、`transport/api.py`

## 背景与目标

### 问题 1：归档/回填时间窗应取「较晚者」

期望语义（本次澄清）：

```
cutoff = max(archive_floor_date, now - archive_window_days)
```

- `archive_floor_date` 是**最早下限**（防止回填到远古数据），`archive_window_days` 是**滚动近期窗口**；
- 二者取**较晚者**：2030 年运行服务时，`now - 90天` 已远晚于 `2026-08-31`，
  因此默认只归档近 90 天，而不是从 2026-08-31 起拉 4 年多数据。

**调研结论：现行实现与文档已经是「较晚者」，本次无需改行为。**

- `core/engine.py:167` `archive_cutoff()`：`return max(floor, window)`；
- plan 0004 决策 7、`docs/architecture.md`、`docs/changelog/0004` 的文案均为 `max(...)`/「较晚者」；
- 全仓库 grep `较早` 无命中。

问题在于：缺少一个**直白的 2030 场景回归测试**，且 `archive_floor_date` 命名容易被理解成
「取更早」的基准。本计划只补测试与文案，不改逻辑。

### 问题 2：`q` 只匹配标题，搜不到摘要/正文预览里的词

`core/storage.py` 当前 `q` 条件为 `title LIKE ?`。实测（部署库 719 条）：

| 关键词 | title 命中 | summary 命中 | content(预览) 命中 | `GET /api/notices?q=` |
| --- | --- | --- | --- | --- |
| 智慧校园建设 | 0 | 1 | 1 | 0 |
| 网络强国 | 0 | 1 | 1 | 0 |
| 推免 | 0 | 14 | 21 | 0 |
| 校长杯 | 20 | 17 | 32 | 3（仅标题） |

命中的两条示例：

- `my_xgtz:c05e2e78...` 关于开通学生"校园虚拟卡"…（"智慧校园建设"在预览正文）
- `my_bgtz:a1058056...` 网络安全和信息化服务周…（"网络强国"在预览正文）

**目标**：`q` 同时匹配 `title` / `summary` / `content` 三个数据库字段；
不解析附件、不读取落盘 HTML（按开发者要求，性能与实现复杂度考虑）。

范围与边界：

- `summary` 为列表接口生成的 80 字摘要；`content` 为 2000 字预览；
- 未归档、无预览的公开源条目只有标题可命中（现状不变）；
- API 路径与参数不变（`q` 语义扩展），响应结构不变。

## 方案

- `NoticeStore._query`：`q` 条件改为

  ```sql
  (title LIKE ? ESCAPE '\' OR summary LIKE ? ESCAPE '\' OR content LIKE ? ESCAPE '\')
  ```

  三个参数相同；对输入先转义 `\`、`%`、`_`，避免用户输入被当作通配符。
- 索引/性能：现有约 1k 行、3 列 `%kw%` 全表扫描，实测毫秒级，直接 LIKE 即可；
  `title` 索引对 `%...%` 无效但数据量小可接受。
- 备选与否决：
  - FTS5 虚拟表（SQLite 3.45/Python 3.12 可用）：数据量小时收益低、需要触发器/重建，
    **否决**；留作后续触发条件（单表 >5 万行或查询 p95 >100ms 时再评估）。
  - 只搜 `summary`：丢失正文预览信息，**否决**。
- 时间窗：不改代码；新增显式测试，并把文案统一为
  「floor 是最早下限，window 是滚动窗口，**取较晚者**（2030 年只回填近 90 天）」。
- 文档补充：`/api/notices` 的 `q` 描述改为「标题 / 摘要 / 正文预览」；
  在 `docs/architecture.md` 的 REST 说明里补充手动回填用法（见下）。

## 附：手动回填的预期用法（本次一并文档化）

`POST /api/check` 支持 `type`（门户栏目）+ `from_page`/`to_page` + `searchValue`，
这是**设计内的历史回填方式**（plan 0004 决策 8/15）：

- 门户不支持日期过滤，只能用「页数区间 + 关键词」逼近时间段；
- `searchValue` 实测会命中**正文但不含标题**的条目（如 `推免` 返回的多条标题无此词）；
- 回填默认不推送 webhook；
- 自动归档仍受时间窗限制：早于 cutoff 的历史只入库，需要时按条
  `POST /api/notices/{id}/archive` 强制归档。

## 影响面

- core：`storage.py`（`_query` 一个方法）
- transport：`api.py` 仅改 `q` 的 `Query(description=...)` 文案
- 配置：无
- 测试：`tests/test_storage.py` 扩展；`tests/test_engine.py` 补时间窗场景
- 文档：`architecture.md`、`index.md`（如需）、plan/changelog 0005

## 风险与备选

- LIKE 的 ASCII 大小写不敏感、中文按字符匹配，符合预期；
- 命中范围扩大后结果变多，靠 `limit/offset` 分页，不改变排序；
- 输入转义不当会误匹配（`%`/`_`），必须有单测覆盖；
- 若未来引入 FTS5，本计划的 LIKE 行为保底不变。

## 验证方式

- 单元：`q` 命中 `summary`、命中 `content`、命中 `title`；`%`/`_` 转义不误伤；
  source/category 过滤与排序不回归。
- 单元：`test_archive_cutoff_prefers_later`——floor 在过去且 window 较晚时 cutoff == window；
  floor 在未来时 cutoff == floor；并断言「2030 场景」（floor=2026-08-31、window=90 天）cutoff > floor。
- 集成（部署库 719 条）：`?q=智慧校园建设` → 1；`?q=网络强国` → 1；`?q=推免` ≥ 21；
  `?q=校长杯` ≥ 20（标题命中的 20 条仍应全部返回）。
- 回归：现有 35 个测试全部通过，`ruff check` 通过。

## 任务拆分

- [ ] `storage.query`：`q` 扩展到 title/summary/content 并转义 `\` `%` `_`
- [ ] 单元测试：三字段命中、转义、过滤/排序回归
- [ ] `test_engine.test_archive_cutoff_prefers_later`（含 2030 场景）
- [ ] 文案：`api.py` 的 `q` 描述、`architecture.md` 时间窗/回填说明
- [ ] 部署机更新（bundle 或修好代理后 `update.sh`）
- [ ] changelog 0005
