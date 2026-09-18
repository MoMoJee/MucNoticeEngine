# 0004 门户翻页、补齐 type、正文与附件落盘

- Status: draft（待开发者确认后实施）
- Owner: MoMoJee
- Created: 2026-09-18
- Related: [reference/portal-notice-types.md](../reference/portal-notice-types.md)、`core/fetcher.py`、`core/sources.py`

## 背景与目标

现状缺口：

- 门户每个 type 只抓**第 1 页 20 条**，推免名额分配等通知在第 2–3 页，抓不到。
- 只接入门户 `type=5/6/8/32`，**公示公告（11）、就业信息（10）等未接入**。
- 公开源只存标题+链接，**正文不抓**；附件和正文都**不落盘**。

目标：

1. 门户来源支持**翻页抓取**（可配置页数上限）。
2. 补齐被忽略的 type，重点是 **11 公示公告**（推免名单/细则）、可选 10 就业信息。
3. 抓取并**落盘**通知正文（原文 HTML + 纯文本）与附件/图片到独立文件夹；**数据库不存正文全文**。

## 调研结论（2026-09-18 实测，未改代码）

### 1. 门户翻页：可行

- API 响应 `datas.page` 提供分页元数据：`total`（总条数）、`totalCounts`（总页数）、`currentPage`、`pageSize`。
- `currentPage` 直接传值即可翻页；超出范围返回空数组。
- 实测：`type=11` `total=2315`、`totalCounts=116`（pageSize=20）；`type=5` `total=2315`。
- 结论：**零障碍**，循环 `currentPage` 到 `pageLimit` 或 `totalCounts` 即可。

### 2. 官方 type 名称（来自响应字段 `notice_type_name`）

| type | 官方名称 | 归类 | 已接入 |
| --- | --- | --- | --- |
| 1 | 新华网 | 新闻 | 否 |
| 3 | 民委要闻 | 新闻 | 否 |
| 4 | 时政头条 | 新闻 | 否 |
| 5 | 办公通知 | 通知 | 是 |
| 6 | 教学通知 | 通知 | 是 |
| 8 | 科研通知 | 通知 | 是 |
| 9 | 校园新闻 | 新闻 | 否 |
| 10 | 就业信息 | 就业 | 否 |
| 11 | 公示公告 | 公示 | 否 |
| 32 | 学工通知 | 通知 | 是 |
| 36 | 活动报道 | 新闻 | 否 |

- 事务相关且值得接入：**11（必须）、10（可选）**。
- 新闻类 `1/3/4/9/36` 不建议进通知流。
- 推免信息：**遴选/名额在 6，名单/实施细则在 11**。
- 此前根据采样推断的名称（如 1=民大要闻、9=学校新闻、36=院系动态）以本表官方名为准。
- 待复核：采样中 `type=1` 与 `type=9` 首屏标题高度一致，疑似内容重叠，实施前需确认去重策略。

### 3. 正文解析：可行

- 门户：`notice_content` 是完整 HTML（UEditor），当前只截 2000 字纯文本；应改为保存**完整 HTML** + 提取纯文本。
- 公开源：正文容器 `.v_news_content` / `#vsb_content` 在 `www`、`rsc`、`grs` 抽样**均命中**；少数页面正文长度为 0（如“章程”），需 fallback（放宽选择器 / 取最大文本块）。
- **发现 bug**：`grs_yjszs` 的 `base_url` 写成站点根 `https://grs.muc.edu.cn/`，但列表页在子目录 `/yjsyzsw/`，导致所有链接拼成 `.../info/...` 返回 **404**。修正做法：改用 `page_url` 作为 `urljoin` 基准，或把 `base_url` 设为 `https://grs.muc.edu.cn/yjsyzsw/`。
- 结论：**正文下载可行**，但依赖先修 URL bug。

### 4. 附件解析：可行，但以“图片”为主，“文件”很少

- 门户：`notice_content` 里**主要内联 `<img>`**（UEditor 上传图）。实测图片**无需登录即可下载**（HTTP 200 `image/png`），但 URL 形如 `http://my.muc.edu.cn:80/...`，需**跟随 301 重定向并归一化**。
- 门户中带文件扩展名的 `<a>` 很少，且抽查发现部分为作者本地路径 `file:///D:/...`（**无效，必须过滤**，仅保留 `http/https` + 文件扩展名）。
- 公开源：抽样文章**未见文件附件**，主要是内联图片（新闻页最多 9 张）；推免“合集”正文是**各学院官网链接**（跨站），可作为相关链接保存。
- 结论：**附件解析可行**，解析范围 = 正文内 `<img>` + 文件扩展名 `<a href>`（http/https）；实际以图片为主，真实文档附件占比低。

### 5. 落盘与鉴权

- 门户内联图片公开可下载；门户正文 HTML 来自 API（需登录）。
- 需处理：重定向、`Referer`、超时、单文件大小上限、并发限速、失败跳过。

## 方案（设计，暂不实现）

- **配置新增**：`portal_page_limit`（每类翻页上限，默认 3）、`archive_enable`（默认 true）、`archive_dir`（默认 `data/archive`）、`archive_download_files`、`archive_max_file_mb`、`archive_max_per_notice`。
- **fetcher**：
  - 门户来源按 `currentPage` 循环到 `pageLimit` 或 `totalCounts`。
  - 修正 `grs_yjszs` 的 URL 拼接。
  - 新增 `archive_notice(notice)`：抓正文 HTML → 落盘 `content.html`、提取 `content.txt`、解析并下载附件/图片 → 写 `meta.json`。
- **storage**：`notices` 增加 `archive_dir`（或 `has_archive`）；附件清单可存 JSON 字段或新表 `attachments(notice_id, kind, url, local_path, filename, size, sha1)`。**不存正文全文**。
- **sources**：新增 `type=11` 公示公告（带关键词过滤）、可选 `type=10` 就业信息；新增 source 级 `title_include` / `title_exclude`（复用 `parsers.py` 中已有的关键词函数）。
- **transport**：`GET /api/notices/{id}/content`、`GET /api/notices/{id}/files`；REST `q` 可扩展为标题+正文搜索（可后置）。
- **目录结构**：

```
data/archive/<source_key>/<notice_id>/
├── content.html      # 原文 HTML
├── content.txt       # 纯文本
├── meta.json         # 标题/来源/URL/时间/附件清单
└── files/            # 下载的附件与图片
```

## 影响面

- core：`fetcher.py`、`storage.py`、`models.py`、`sources.py`、`config.py`
- transport：`api.py`
- 配置：`config.example.toml`
- 数据/schema：`notices` 加列 / 新增 `attachments` 表（无迁移框架，需人工或重建）

## 风险与备选

- 选择器与 type 可能随学校改版失效；`file://` 垃圾链接；下载量/磁盘/带宽与限速；附件的版权与隐私（仅个人内网使用，不公开传播）。
- 备选：正文只存纯文本不存 HTML。否决：会丢失附件与格式信息。

## 验证方式

- 单元：翻页解析 `page` 元数据；附件链接过滤（`file://` 丢弃）；归档落盘用离线 HTML fixture。
- 集成：对 `type=6/11` 抓多页，确认 9/9、9/10 名额分配通知入库且归档成功。
- REST：`GET /api/notices/{id}/files` 能列出并取到本地文件。

## 任务拆分

- [ ] 修复 `grs_yjszs` URL 拼接
- [ ] 门户翻页 + `portal_page_limit` 配置
- [ ] 接入 `type=11` / `type=10` + 关键词过滤
- [ ] 正文/附件归档模块 + 配置项
- [ ] storage 加列/建表 + REST 文件接口
- [ ] 测试与文档（changelog、architecture、config 示例）
