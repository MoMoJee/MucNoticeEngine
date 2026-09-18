# 开发计划

**规则：功能开发前先在这里建计划，计划获批（`Status: approved`）后再写代码。**
规范见 [../conventions/docs.md](../conventions/docs.md)。

## 命名

`NNNN-kebab-topic.md`：四位递增编号，不复用，与 `docs/changelog/` 同编号对应。

## 已有计划

| 编号 | 标题 | 状态 |
| --- | --- | --- |
| [0001](0001-bootstrap-engine.md) | 从 AstrBot 插件剥离独立通知引擎 | done |
| [0002](0002-dotenv-config.md) | 支持从 .env 读取配置 | done |
| [0004](0004-portal-pagination-attachments.md) | 门户翻页、补齐 type、正文与附件落盘 | done |
| [0005](0005-search-fields-and-window-semantics.md) | q 搜索字段扩展、归档时间窗语义与 API 文档体系 | done |
| [0006](0006-retention-first-seen.md) | 保留期改为按入库时间且默认关闭 | done |
| [0008](0008-lxy-xingong-sources.md) | 理学院 / 信息工程学院公开来源接入 | done |

## 模板

新建文件时复制以下内容；删除注释后填写。

```markdown
# NNNN 标题

- Status: draft
- Owner: <你的名字>
- Created: YYYY-MM-DD
- Related: <相关 issue / 文件>

## 背景与目标

为什么做、要解决什么问题、明确的验收标准。

## 方案

整体思路与关键取舍。列出会新增/修改的模块。

## 影响面

- core：
- transport：
- 配置：
- 数据/schema：
- 文档（按 [同步矩阵](../conventions/docs.md#代码变更--文档同步矩阵) 列出）：

## 风险与备选

有哪些不确定性，为什么不选其它方案。

## 验证方式

实现后准备用什么命令/测试证明它工作。

## 任务拆分

- [ ] 任务 1
- [ ] 任务 2
```
