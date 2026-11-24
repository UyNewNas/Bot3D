# AR-0019：控制权交付文档最终复验

| 日期 | 范围 | 环境 | 技术结果 | 产品验收 |
| --- | --- | --- | --- | --- |
| 2026-11-23 | I02 · DEV-M1-05 · 台账与交付文档 | Linux x86_64、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | DOC PASS；整分支复核 FAIL | PENDING |

## 修正范围

DEF-0010 的 DOC 失败保留在 [AR-0018](AR-0018-control-authority-invariant-final.md)。本次只将开发台账标题恢复为现有的非零状态计数格式，并更新最终证据入口。实际状态仍为 13 TODO、5 DONE、13 DRAFT、2 DEFERRED；没有 DOING。未修改产品源码、测试、依赖或检查器。

## 实际证据

| 检查 | 状态 | 结果 |
| --- | --- | --- |
| DOC 汇总 | PASS | 42 篇 Markdown、94 个表、276 个本地链接、3 个严格 JSON 块；编号、58 条开发依赖、两轮迭代与台账统计一致 |
| 差异格式 | PASS | git diff --check 退出 0，无输出 |
| UNIT / MOCK 与安装 | PASS（沿用） | AR-0018 的 379 项全量、四个新 marker 11 / 13 / 35 / 17、13 模块边界、sdist→wheel 与独立空消费者；本次没有修改相关输入 |
| 文档示例与工件 | PASS（沿用） | AR-0018 的三个示例、16 个 framework 源码字节匹配、当前 README 元数据与零运行依赖；本次未修改示例或 README |
| 独立技术复核 | PASS（任务与修正） | AR-0017 的公开结果问题已由 AR-0018 的回归与针对性复核关闭；整分支技术复核仍为发布前置 |
| 独立整分支复核 | FAIL | 候选 78292d7 的 AuthorityResult 仍可构造永久状态矛盾和同一租约同时有效 / 已失权；见下面 DEF-0011 / DEF-0012 |

复现 DOC 检查：`uv run --no-sync python -I tools/check_project_docs.py` 与 `git diff --check`。本次新输出单独保存在本地 AR-0019，不覆盖前次失败。DEF-0010 由本次符合既有格式的统计与实际 DOC 复验关闭。

## 整分支复核与修正交接

整分支独立复核覆盖 `ffae464..78292d7`，提出两项公开结果构造约束问题，正常管理器转换未发现相应漏检：

- DEF-0011：同绑定 CONTEXT_CHANGED 事件可以配未退役甚至 ARMED 的快照；安装包反例输出 `accepted True loss CONTEXT_CHANGED retired False arming ARMED`。无新 effects 的 CONTEXT_CHANGED / CLOCK_UNHEALTHY 拒绝也未要求对应永久标志。退役 / 故障不可自行恢复，较旧代数的历史事件仍必须保持这一事实。
- DEF-0012：AuthorityResult 可同时返回一个当前租约，以及携带相同 lease_id 的 RELEASED 事件。一个不复用 token 不能同时有效和失权；不同新 token 与旧租约失权事件应继续允许共存。

两项由一次集中修正补齐构造校验与负例 / 合法对照，修正后只做一次针对性复核；失败、全量与安装复验接 [AR-0020](AR-0020-control-authority-final.md)。这些问题不改变租约、绑定生命周期或应用管理器的 API。

## 交付状态

DEV-M1-05 为 DONE：独占会话租约、显式激活、单调钟到期、失权效果、能力上下文退役与聚合未结执行门禁均已交付。README 继续以项目介绍、技术架构、实现方式和可运行示例为主，内部过程由专题设计与项目记录承载。

REQ-005 / REQ-006 保持 DEVELOPING，I02 ACTIVE；I01 IN_ACCEPTANCE，产品验收均 PENDING。后续从 DEV-M1-06 的规范化命令摘要、JournalPort 与内存替身继续，再按 I02 依赖组合状态投影与执行 / 停止链。当前结果不包含真实认证、物理 STOP、设备 fencing、持久化、SIM / XR / REAL 联调或现场验收。
