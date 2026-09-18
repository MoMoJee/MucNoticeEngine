# 0008 理学院 / 信息工程学院公开来源接入

- Status: done（2026-09-19 交付，见 [changelog/0008](../changelog/0008-lxy-xingong-sources.md)）
- Owner: MoMoJee
- Created: 2026-09-19
- Related: `core/sources.py`、`core/fetcher.py`、[docs/reference/portal-notice-types.md](../reference/portal-notice-types.md)

## 背景与目标

要把理学院（lxy.muc.edu.cn）和信息工程学院（xingong.muc.edu.cn）的栏目页
接入现有公开源体系，做法与研究生院各栏目一致：只加 `SourceConfig`，
不改 core/transport 架构。两站均为博达 Visual SiteBuilder 9（VSB9），
静态 HTML 列表 + JSON 智能搜索接口。

目标（阶段一）：

1. 新增 11 个公开来源（理学院 3 + 信工 8），`SOURCES` 从 21 增至 32。
2. 让公开源支持 `href="javascript:void(0)" onclick="opennews('…')"` 的链接形态
   （信工多个栏目混用），属 fetcher 通用小改，不影响既有来源。
3. 文档同步：来源数量、选择器/搜索接口调研结论。

另经调研确认两站有同一套「智能搜索」JSON 接口（无需登录），
可作为阶段二（关键词检索 / 回补）单独计划，见文末。

### 已确认的页面结构（2026-09-19 采样）

理学院（`div.new_list3 dd a.fl` + `span.fr.gray` 日期，格式 `YYYY年MM月DD日` 或 `YYYY-MM-DD`）：

| key | 名称 | URL | 条目/页 |
| --- | --- | --- | --- |
| `lxy_xydt` | 理学院 - 学院动态 | https://lxy.muc.edu.cn/xydt1.htm | 15 |
| `lxy_rcpy` | 理学院 - 人才培养 | https://lxy.muc.edu.cn/rcpy.htm | 1 |
| `lxy_kxyj` | 理学院 - 科学研究 | https://lxy.muc.edu.cn/kxyj.htm | 15 |

信息工程学院（`ul.ulminheight .news__title a` + `span.news__date` `[YYYY年MM月DD日]` 或 `[YYYY-MM-DD]`）：

| key | 名称 | URL | 条目/页 |
| --- | --- | --- | --- |
| `xg_tzgg` | 信息工程学院 - 通知公告 | https://xingong.muc.edu.cn/index/tzgg.htm | 10 |
| `xg_kyjx` | 信息工程学院 - 科研教学 | https://xingong.muc.edu.cn/index/kyjx.htm | 10 |
| `xg_jwdt` | 信息工程学院 - 教务动态 | https://xingong.muc.edu.cn/index/jwdt.htm | 10 |
| `xg_dthd` | 信息工程学院 - 党团活动 | https://xingong.muc.edu.cn/index/dthd.htm | 10 |
| `xg_xyxw` | 信息工程学院 - 学院新闻 | https://xingong.muc.edu.cn/index/xyxw.htm | 10 |
| `xg_yjszs` | 信息工程学院 - 研究生招生 | https://xingong.muc.edu.cn/zsjy/yjszs.htm | 10 |
| `xg_bksjx` | 信息工程学院 - 本科生教学 | https://xingong.muc.edu.cn/jyjx/bksjx.htm | 6 |
| `xg_zyrz` | 信息工程学院 - 专业认证 | https://xingong.muc.edu.cn/jyjx/zyrz.htm | 8 |

关键事实：

- 信工 `bksjx`/`yjszs`/`zyrz` 以及列表内的微信/外站条目，链接都在
  `onclick="opennews('…')"`，`href` 是 `javascript:void(0)`；现有 fetcher 会跳过或产生坏链接。
- 部分条目指向站外（`mp.weixin.qq.com`、`news.muc.edu.cn`、`mzyy.muc.edu.cn`），保持原样收录。
- 两站首页（`/`）不单独接入：首页列表与 `xyxw` 等栏目重复，且链接形态更绕，栏目页已覆盖。
- 理学院 `rcpy.htm` 有一条 `content.jsp?…` 受限链接（游客“无权访问”），选择器限定 `info/` 后自然排除。
- 均为 UTF-8 页面，日期均在父级 `li`/`dd` 文本中，现有 `_extract_published_at` 可直接解析。
- 详情页正文容器 `.v_news_content` 命中现有 `ARTICLE_SELECTORS`；微信正文容器为 `#js_content`，未在列表中。

## 方案

阶段一（本计划交付）：

1. `core/sources.py`：按上表新增 11 个来源，`selector`/`parser`/`category` 如下：
   - 理学院：selector `div.new_list3 dd a[href*="info/"]`，`parse_selector_generic`，category `lxy`；
   - 信工：selector `ul.ulminheight .news__title a`，`parse_selector_generic`，category `xingong`。
2. `core/fetcher.py` 新增通用取链函数（仅公开源路径使用）：

   ```python
   # 伪代码：href 为空或 javascript: 时，退回 onclick 中首个引号字符串
   def _resolve_link(self, tag, page_url) -> str:
       href = (tag.get("href") or "").strip()
       if not href or href.lower().startswith("javascript:"):
           href = 首个引号内容(tag.get("onclick"))
       return urljoin(page_url, href) if href else ""
   ```

   替换 `_fetch_source_notices` 里直接读 `href` 的两行；正常 `http(s)` 链接行为不变。
3. `ARTICLE_SELECTORS` 增加 `#js_content`（微信公众号正文），让站外微信条目的详情归档可用。
4. 测试：来源数量/唯一性、onclick 取链、两种日期格式解析；既有 170 余测试保持通过。
5. 文档：见「影响面」。

不做：首页来源、翻页抓取（保持其他公开源「每轮首页」的现状；
需要更多页时可用 `extra_urls`，如 `https://lxy.muc.edu.cn/xydt1/1.htm`、
`https://xingong.muc.edu.cn/index/tzgg/2.htm`）、关键词过滤。

## 影响面

- core：`sources.py`（新增 11 条）、`fetcher.py`（`_resolve_link` + `#js_content`）
- transport：无（`/api/sources` 自动出现新来源）
- 配置：无
- 数据/schema：无
- 文档（按 [同步矩阵](../conventions/docs.md#代码变更--文档同步矩阵)）：
  - `README.md`：来源数字 21 → 32（公开 10 → 21）
  - `docs/guides/rest-api.md`：`/api/sources` 数字
  - `docs/index.md`：代码结构注释中的来源数字
  - `docs/reference/portal-notice-types.md`：新增「公开来源登记 + VSB9/搜索接口」小节
  - `AGENTS.md`：命令注释「列出 21 个来源」
  - `docs/plans/README.md`：登记 0008
- changelog：`docs/changelog/0008-lxy-xingong-sources.md`

## 风险与备选

- 选择器/URL 均逆向所得，学校改版会表现为「选择器未命中」日志；与现有公开源同等风险。
- 收录微信/外站链接后，正文归档可能拿不到（站点限制/反爬），失败会记日志并跳过，不影响入库与推送。
- `onclick` 取链是通用改动，但仍可能命中无关 `javascript:` 链接；只在 `href` 缺失时才启用，并加单测。
- 同一文章出现在多个栏目（如 `xg_tzgg` 与 `xg_yjszs`）时按链接去重，无需额外处理。
- 否决方案：为信工写专用解析器（无必要）；用搜索接口替代列表页（搜索要求关键词，不能代替栏目订阅）。

## 验证方式

- `uv run ruff check .`
- `uv run pytest`（更新来源计数后全绿）
- `uv run muc-notice-engine sources` → 共 32 个来源
- `uv run muc-notice-engine poll --source lxy_xydt,lxy_rcpy,lxy_kxyj,xg_tzgg,xg_kyjx,xg_jwdt,xg_dthd,xg_xyxw,xg_yjszs,xg_bksjx,xg_zyrz`
  → 新条目日期/链接正确，onclick 条目有真实 URL
- 对照网页抽查 3 条标题与日期

## 任务拆分

- [x] `fetcher.py`：`_resolve_link`（onclick/javascript）+ `#js_content`
- [x] `sources.py`：新增 11 个来源
- [x] 测试：来源计数、onclick 取链、日期解析
- [x] 文档同步（README / index / rest-api / portal-notice-types / AGENTS）
- [x] changelog 0008 + 计划状态收尾

## 阶段二（可选，建议另立计划 0009）：智能搜索接口

两站共用 `/views/search/...` 页面，实际请求：

```
POST https://<site>/aop_component/webber/search/search/search/queryPage
Header: Authorization: tourist
Header: owner: <1499287359 信工 | 1686112499 理学院>
Body(JSON): { aliasName:"article", keyWord, orderType:"date", searchType:"text",
              searchScope:3, searchOperator:0, searchDateType:"", auditing:["1"],
              owner, token:"tourist", urlPrefix:"/aop_component/", page:{current,size},
              advance:false, advanceKeyWord:"", lang:"i18n_zh_CN", columnId?: <可选栏目过滤> }
```

响应 `data.page.records[]` 含 `collapseTitle`（纯文本标题）、`url`（可能为 `//` 协议相对）、
`createDate`、`column`、`columnName`、`intro`、`content`（带 `<span>` 高亮）与 `total`。

已实测：无需登录；`columnId` 可过滤栏目；`keyWord` 为空时返回 0 条，故**不能**用它枚举栏目历史，
只能按关键词检索/回补。若要做，建议照 `manual_fetch_portal` 的模式：
`fetcher.fetch_aop_search(...)` + `engine.manual_fetch_search(...)`（回填语义、不推送），
再决定暴露为 CLI 还是 `/api/check` 扩展。是否实施待确认。
