# 文档规范

## 目录职责

| 目录 | 只放什么 | 不放什么 |
| --- | --- | --- |
| `docs/`（根） | 长期稳定的说明：索引、架构 | 计划、变更日志 |
| `docs/conventions/` | 规范本身 | 具体某次开发的细节 |
| `docs/plans/` | **实现前**的计划 | 已完成的复盘（移到 changelog） |
| `docs/changelog/` | **交付后**的变更说明 | 未来计划 |

## 文件命名

- 一律使用 `NNNN-kebab-topic.md`：`0001-bootstrap-engine.md`。
- `NNNN` 为四位、从 0001 递增、**不复用不回收**；计划与变更日志编号**尽量一一对应**。
- 例外：**纯分析/调研类**的 changelog 可以没有对应 plan（此时编号只占用 changelog 序列）。
- `kebab-topic` 用简短英文（本仓库文档正文用中文），例如 `webhook-retry`、`source-dedup`。
- 根级长期文档使用固定名：`index.md`、`architecture.md`。不允许 `new.md`、`temp.md`、`最终版.md`。

## 写作规范

1. **说人话、短**：一段不超过 3 行；能列表就不写段落。
2. **可验证**：涉及命令/路径/配置的，必须与代码一致，且可直接复制执行。
3. **不复制代码和配置**：用相对链接指向源文件，避免两处维护导致过期。
4. **写「为什么」**：代码已经表达「是什么」，文档补充决策原因、约束、坑。
5. **单一入口**：新文档必须登记到 `docs/index.md` 的文档地图。
6. **过期的直接删/改**：不要保留「已废弃」段落，历史留给 git。

## 计划（plan）规范

- 位置：`docs/plans/NNNN-kebab-topic.md`，模板见 [plans/README.md](../plans/README.md)。
- 必填头部字段：`Status` / `Owner` / `Created` / `Related`。
- `Status` 取值：`draft`、`approved`、`in-progress`、`done`、`abandoned`。
- 计划先于代码：`Status` 至少为 `approved` 才能开始实现；实现完成后改为 `done` 并链接对应 changelog。
- 计划写**目标、方案、影响面、风险、验证方式**，不写大段实现代码。

## 变更日志（changelog）规范

- 位置：`docs/changelog/NNNN-kebab-topic.md`，模板见 [changelog/README.md](../changelog/README.md)。
- 必须包含：`Plan` 链接、`Type`、`Summary`、`Changes`（按模块）、`Verification`、`Breaking changes`、`Follow-ups`。
- 每次交付（一个可提交的变更集）对应一条；同一次提交若有多个维度，可写多条 `Changes` 但只建一个文件。
- `Verification` 必须写实际跑过的命令与结果，不能写「应该没问题」。

## 防过期检查清单（提交前自问）

- [ ] 新增/删除文档是否更新了 `docs/index.md`？
- [ ] 改动了 `core`/`transport` 边界，是否更新了 `architecture.md`？
- [ ] 新增配置项，是否同步了 `config.example.toml`（以及本文档无需重复配置说明）？
- [ ] changelog 的 `Verification` 是否是真实执行过的命令？
- [ ] 文档里的命令能否直接复制运行？
