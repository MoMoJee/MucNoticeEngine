# AOP 智能搜索（远程检索）协议与站点目录

调研日期：2026-09-19。数据来源：各站点 `/views/search/modules/resultpc/js/soso.js`
与实测请求；非官方文档，学校升级 VSB9 后可能变化。

## 接口

```
POST https://<任意 VSB9 站点>/aop_component/webber/search/search/search/queryPage?r=<随机数>
Content-Type: application/json;charset=utf-8
Authorization: tourist
owner: <站点ID>
```

- **免登录**：`Authorization` 固定 `tourist`，不需要 Cookie。
- **跨站可查**：任意 VSB9 主机可查询任意 `owner`（已在 xingong/www 主机交叉验证）；
  本项目固定使用主站 `https://www.muc.edu.cn`。
- 返回 `code=0000` 为成功；`data.page.records` 为结果，`data.page.total` 为总数。

请求体关键字段（其余用固定值，见 `core/aop.py` 的 `build_query`）：

| 字段 | 取值 | 对应我们的参数 |
| --- | --- | --- |
| `keyWord` | 空格分隔关键词 | `q` |
| `searchOperator` | `1`=全部命中（AND）、`0`=任意命中（OR） | `match=all` / `any` |
| `searchScope` | `1`=标题、`2`=正文、`3`=全部 | `scope=title`/`content`/`all` |
| `orderType` | `date`（按时间）、`score`（相关度） | `order` |
| `searchDateType` | `custom` 时启用 `beginDate`/`endDate` | `since`/`until`（`YYYY-MM-DD`，可只给一端） |
| `columnId` | 栏目 ID（可选，需配合关键词） | 未暴露 |
| `page.current` | 从 `0` 起 | 内部翻页 |
| `page.size` | 单页条数，上限 100（传更大按 100 处理） | 固定 100 |

结果字段：`collapseTitle`（纯文本标题）、`title`（带 `<span>` 高亮）、`url`
（可能是 `//` 协议相对）、`createDate`、`column`、`columnName`、`intro`/`content`
（高亮摘要）、`id`、`ownerName`（部分旧记录为空）。

## 实测限制

- `advance`/`advanceKeyWord`（站点高级搜索的隐藏参数）**不可靠**：
  `NOT` 不生效；「全部 + 任意」两个框组合后语义异常。因此本项目不暴露该语法，
  「不包含」由本地按标题/摘要过滤实现。
- `keyWord` 为空返回 0 条，不能用它枚举栏目历史。
- 同标题文章可能出现在不同栏目（URL 不同），属不同文章；本项目按 URL 去重。
- `order=score` 按相关度排序，可能返回很旧的文章。
- 站点首页 `_jsq_(栏目, 模板, -1, owner)` 或 `_showDynClickBatch(..., owner)`
  的最后一位参数即 owner；目录更新可按此重新提取。

## 站点目录（34 个）

| key | 名称 | host | owner |
| --- | --- | --- | --- |
| www | 中央民族大学（主站） | www.muc.edu.cn | 1775585708 |
| news | 民大新闻 | news.muc.edu.cn | 1775596343 |
| grs | 研究生院 | grs.muc.edu.cn | 1499287447 |
| rsc | 人事处 | rsc.muc.edu.cn | 1499289493 |
| cwc | 财务处 | cwc.muc.edu.cn | 1698027629 |
| xiaoyou | 校友网 | xiaoyou.muc.edu.cn | 1499288180 |
| msy | 民族学与社会学学院 | msy.muc.edu.cn | 1834816456 |
| scemll | 中国民族语言文字应用研究院 | scemll.muc.edu.cn | 1607202447 |
| sla | 文学院 | sla.muc.edu.cn | 1632946457 |
| history | 历史文化学院 | history.muc.edu.cn | 1499283708 |
| phil | 哲学与宗教学学院 | phil.muc.edu.cn | 1694118460 |
| xinchuan | 新闻与传播学院 | xinchuan.muc.edu.cn | 1577114110 |
| sfs | 外国语学院 | sfs.muc.edu.cn | 1499286850 |
| marxism | 马克思主义学院 | marxism.muc.edu.cn | 2077420629 |
| eco | 经济学院 | eco.muc.edu.cn | 1499285060 |
| ms | 管理学院 | ms.muc.edu.cn | 2012564501 |
| law | 法学院 | law.muc.edu.cn | 1779811220 |
| cles | 生命与环境科学学院 | cles.muc.edu.cn | 1499286151 |
| yxy | 药学院 | yxy.muc.edu.cn | 2110912796 |
| lxy | 理学院 | lxy.muc.edu.cn | 1686112499 |
| xingong | 信息工程学院 | xingong.muc.edu.cn | 1499287359 |
| yyxy | 音乐学院 | yyxy.muc.edu.cn | 2008922769 |
| wd | 舞蹈学院 | wd.muc.edu.cn | 1739305935 |
| art | 美术学院 | art.muc.edu.cn | 1681929250 |
| sport | 体育学院 | sport.muc.edu.cn | 1499288004 |
| edu | 教育学院 | edu.muc.edu.cn | 1499283932 |
| cie | 国际教育学院 | cie.muc.edu.cn | 1499285259 |
| muchnic | 海南国际学院 | muchnic.muc.edu.cn | 1972009796 |
| sce | 继续教育学院 | sce.muc.edu.cn | 1815067731 |
| myzx | 中国少数民族研究中心 | myzx.muc.edu.cn | 1499284099 |
| gjaqyjy | 国家安全研究院 | gjaqyjy.muc.edu.cn | 1824114434 |
| vbep | 中国兴边富民战略研究院 | vbep.muc.edu.cn | 1636520272 |
| mmsi | 质谱成像与系统生物学研究中心 | mmsi.muc.edu.cn | 1790691648 |
| nmlr | 国家语言资源监测与研究民族语言中心 | nmlr.muc.edu.cn | 1507633105 |

> 目录快照存于 `core/aop.py` 的 `AOP_SITES`；非 VSB9 站点（如 `lib`、`my`）没有 owner。
> 站点清单来源：`https://www.muc.edu.cn/zzjg/jxhkydw1.htm`（教学和科研单位）。
