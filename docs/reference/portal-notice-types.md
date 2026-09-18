# 信息门户通知分类（type）枚举与归类

数据来源：`POST https://my.muc.edu.cn/comsys-portal-notice-web/getNoticeByPage`，参数
`{"currentPage":N,"pageSize":30,"type":T}`。2026-09-18 对 `T=1..80` 逐个探测，
有效类型各取前 5 页（150 条）采样归类。

原始采样命令与脚本为一次性分析用，已删除；本目录保留结论。

## 有效 type（共 11 个）

无效（返回空）：`2`、`7`、`12–31`、`33–35`、`37–80`。

名称取自响应字段 **`notice_type_name`**（官方名），非推断。

| type | 官方名称 | 归类 | 来源 key | 说明 |
| --- | --- | --- | --- | --- |
| 1 | 新华网 | 新闻 | `my_xhw` | 外部新闻；首屏与 type=9 疑似重叠 |
| 3 | 民委要闻 | 新闻 | `my_mzyw` | 国家民委相关 |
| 4 | 时政头条 | 新闻 | `my_sztt` | 国内时政 |
| 5 | 办公通知 | 通知 | `my_bgtz` | 行政/后勤/安全/假期 |
| 6 | 教学通知 | 通知 | `my_jxtz` | 课程/选课/助教；**推免校内遴选与名额分配在此** |
| 8 | 科研通知 | 通知 | `my_kytz` | 讲座预告、项目申报 |
| 9 | 校园新闻 | 新闻 | `my_xyxw` | 校内新闻 |
| 10 | 就业信息 | 就业 | `my_jyxx` | 招聘会/宣讲/求职 |
| 11 | 公示公告 | 公示 | `my_gsgg` | 结果公示 + 招标采购；**推免名单/实施细则在此** |
| 32 | 学工通知 | 通知 | `my_xgtz` | 学生事务 |
| 36 | 活动报道 | 新闻 | `my_hdbd` | 校园活动报道 |

> 全部 11 个 type 已于 2026-09-18 接入（见 [plans/0004](../plans/0004-portal-pagination-attachments.md)）。

## 分页与正文/附件（补充调研，2026-09-18）

- **翻页可行**：响应 `datas.page` 含 `total`（总条数）、`totalCounts`（总页数）；`currentPage` 有效，超界返回空。
- **正文**：门户 `notice_content` 为完整 HTML；公开源正文容器 `.v_news_content`/`#vsb_content` 命中率高。
- **附件**：门户**相当多通知带文件附件**（抽样 44%；type=6 为 8/10，type=11 为 6/10）。附件不在 `notice_content`，而在详情接口 `POST getNotice` 的 `notice_info.notice_annext[]`；下载走 `GET /comsys-portal-notice-web/download?id=<annex_id>&notice_id=<id>`，**需登录**。公开源抽样未见文件附件，主要是内联图片。
- 实现计划见 [plans/0004](../plans/0004-portal-pagination-attachments.md)。

完整样本见同目录 [portal-notice-types.csv](portal-notice-types.csv)。

## 聚合归类

- **事务通知类**（学生真正需要的）：`5 办公`、`6 教学`、`8 科研`、`32 学工`、`11 公示`。
- **新闻资讯类**（学校宣传，非通知）：`1 要闻`、`9 与 1 重复`、`3 民族团结`、`4 时政`、`36 院系动态`。
- **就业类**：`10 就业创业`（有价值但可选）。

## 对比要点

- `1` 与 `9` 内容完全相同，聚合时需按「来源+标题」或链接去重，否则重复推送。
- 推免信息分散在两类：**遴选/名额分配在 type=6**，**名单公示/实施细则在 type=11**。
- `type=11` 是「公示公告」大杂烩，含大量**招标采购公告**；已按决策整类接入、不做关键词过滤，
  需要静音时可订阅时排除 `my_gsgg`。
- `3`、`4` 是时政新闻，与校园通知无关，不建议接入通知推送。

## 接入策略（已确认）

1. **全部有效 type 都抓取**（1/3/4/5/6/8/9/10/11/32/36），**不做关键词过滤**。
2. 门户来源**支持翻页**（每轮每类 `portal_page_limit` 页；手动历史抓取可用
   `POST /api/check` 的 `type` + `from_page`/`to_page` + `searchValue`）。
3. 自动归档受时间窗限制（`max(2026-08-31, now - 90天)`），避免首跑爆炸；单条可强制归档。
4. 已于 2026-09-18 交付，实现细节见 [plans/0004](../plans/0004-portal-pagination-attachments.md) /
   [changelog/0004](../changelog/0004-portal-pagination-attachments.md)。

> 这些 type 数字是门户内部编码，非官方文档；学校可能调整，接入后需定期校验。
