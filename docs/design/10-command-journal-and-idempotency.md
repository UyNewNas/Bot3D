# DEV-M1-06：命令摘要与内存 Journal

- 日期：2026-11-24
- 范围：I02 / DEV-M1-06；依据 [台账](../project/backlog.md)、[契约 §8](03-contracts-and-adapters.md)、[运行时 §3 / §5](05-runtime-coordination.md)
- 前序：PR #3 / `e653eeac9dd1c366ac1e95af70486f87f192116e`；用户已要求继续该工作包，沿用功能分支 PR 交付。

## 1. 目标和实现选择

在既有标准库内核中建立可复用的命令身份、执行摘要和日志端口，使同键重试能查询原事实，异语义请求不会覆盖原命令。采用不可变领域值、同步端口和短锁内存适配器；不连接设备，不实现协调器、持久化、进程恢复或完整停止链。

比较过直接散列传输 JSON、增加通用事件存储框架，以及显式类型加版本化规范编码。采用第三种：传输 JSON 受字段顺序和请求关联影响；通用框架增加本工作包不需要的扩展语义。以下编码、租约入摘要、CAS 和保留方式是本轮实现决策，未将其表述为用户新增要求。

## 2. 命令值与摘要

`domain.commands` 提供 `CommandKey`、`CommandTiming`、`CommandContext`、`PoseConstraints`、`PoseCommand`、`canonical_execution` 和 `execution_digest`。

- 键是 `RobotId + UUID command_id`；UUID 字符串规范化为标准小写带连字符表示，其他标识不 trim / case-fold / Unicode 归一化。命令标识拒绝 Unicode surrogate 码点，避免其 JSON 转义与合法补充平面字符别名；合法非 ASCII 字符继续保留。
- 当前命令仅支持 API `1.0` 的 `manipulation.pose_goal`。未知版本、能力和额外构造字段拒绝，不能静默漏入摘要。
- 摘要包含规范编码版本、robot、backend_epoch、lease_id、capability_revision、frame、tool、位置、姿态、模型 / 场景 / 标定版本、约束，以及 clock_id 和全部期限。command_id 是独立键；request_id 仅作关联，二者不加入执行摘要。
- 内部期限使用整数 ns，与既有 `MonotonicInstant` 一致；`0 <= admit_before_ns <= start_before_ns`，执行预算严格为正。这里验证值的结构，不验证当前时间或设备配置。
- 执行标量使用基础类型已验证的有限 binary64；统一负零，不按容差取整。四元数按 w、x、y、z 第一个非零分量选正号，使 q 与 -q 等价，不修改基础四元数相等规则。
- 编码为排序键、紧凑分隔、ASCII 转义、禁止非有限数的 JSON UTF-8，编码标识 `bot3d.pose-command.v1`；SHA-256 输出小写 hex。有手工固定内容的独立测试。
- 凭据类 lease_id 不进入默认 repr；规范化字节是内部执行数据，不应直接作为普通日志输出。

## 3. JournalPort 和不可变事实

`application.ports.JournalPort`：

| 接口 | 结果 / 契约 |
| --- | --- |
| `retention` | `JournalRetention`；明示保留作用域、时间窗口和 durable 标志 |
| `lookup(key)` | 原 `CommandRecord` 或明确不存在；失败抛 `JournalUnavailable`，不能冒充不存在 |
| `record_acceptance(acceptance)` | 原子 compare-and-insert；返回 `AcceptanceWrite(record, created)`；同摘要重试 created=false，异摘要抛 `IdempotencyConflict` |
| `append(key, entry, expected_revision=...)` | 原子追加一项事实；返回新不可变记录，旧快照不改变；已存在的相同 entry_id / 内容先返回原记录，再检查版本 |

`CommandAcceptance` 保留最初的完整命令、`BackendIdentity`、可信 session_id、记录时刻和 validation_id。validation_id 关联协调器当次检查依据；本轮不伪造实际检查结果。命令 epoch 与原绑定必须一致，后续查询不能重解析到新绑定。

接受记录只是候选，`CommandRecord.state` 初始为 None。协调器在日志确认后复核撤销代数、期限、权限、状态与上下文，才追加 `CommandEvent(ACCEPTED, PENDING, ...)` 并发布接受。日志不鉴权、不占业务槽、不授予执行许可；调用者先做资源访问授权，已知重试不要求重新获得原运动租约。

每个 `JournalEntry` 有事件 ID、保护钟记录时刻和具体不可变 payload：

- `CommandEvent`：既有公共状态 / certainty / 原因；保留状态与确定性配对和合法转换。
- `DispatchIntent`：唯一 attempt_id、计划摘要和预先确定的原查询关联 query_key。必须已经从 ACCEPTED 进入 PLANNING；每个命令仅一个意图。
- `BackendReceipt`：原 attempt 的不透明原句柄；不能换 attempt / 改句柄；终态后到达仍只追加事实。
- `ReconciliationFact`：原 attempt 的追加核验事实；不改写原终态，不解除执行锁。

版本为已追加事实数量，从 0 开始；并发更新通过 expected_revision 防止覆盖，entry_id 冲突明确报错。时刻属于本实例同一保护钟且非递减。DISPATCHING 必须已有意图；EXECUTING 必须已有原句柄。已收到后端受理回执或进入 EXECUTING 后，必须先记录 CANCEL_REQUESTED 才能记录 CANCELLED；协调器能证明尚未越过最终裁决的待下发工作仍可直接取消。完整运动前提和最终裁决仍由 DEV-M1-08 / 09 实现，日志状态不是物理完成证明。

业务终态与 certainty / 原因一旦记录不能覆盖。后续 receipt / reconciliation 可以追加，不能重新出现状态事件或第二次意图。日志不会调用 planner、execute、STOP 或控制权对象。

## 4. 内存、故障和保留

`adapters.memory_journal.InMemoryJournal` 在一个短锁中完成查重、版本验证和整记录替换。没有段外设备或磁盘 I/O。更新失败不返回成功；遇到存储异常时保守报告 UNKNOWN 写入结果并锁定所有新写入，无自动复位。受影响的键持续返回明确异常，包括查询，不能把未知提交误报为不存在；其他已确认记录仍可查询，精确重试不产生新写入。故障锁拒绝的新写入标记 NOT_COMMITTED，这不消除先前 UNKNOWN。读故障同样锁定受影响键和新写入，首次读异常的 write_outcome 为 None。测试工具通过替换底层 mapping 注入写前失败、写后回执丢失和读故障，不给正式 API 增加测试控制开关。

内存保留范围是当前实例的完整生命周期，无自动过期 / 删除；时间窗口为 None 表示实例作用域，不表示无限跨进程保证。durable=false；新实例没有旧数据。持久化同步、明确 SQLite 保留期、损坏恢复和跨重启去重由 DEV-M1-10 / 11 定义。ID 永不复用；查无记录不证明设备从未执行。

当前追加会在锁内复制、核对完整历史并计算摘要，单次成本随历史长度增长；本实现面向小规模确定性 mock，不承诺固定持锁时间。长历史追加优化留后续吞吐 / 有界通路工作，不以这次功能验证作为负载验收。

本轮 T18 只证明日志错误 / 未知结果与原子快照行为。禁新运动、撤权、应急审计及 STOP 不等待日志的完整集成由 DEV-M1-08 / 09 / 16 验证。

## 5. 验证与后续

固定 CPython 3.12.11、uv 0.10.9、pytest 8.4.2；运行第三方依赖为零，锁文件不变。

| 切片 | 本轮验收 |
| --- | --- |
| T02 / digest-retry | 固定编码、等价数值 / q 符号 / request_id、同键原记录、真实线程竞争 |
| T03 / digest-conflict | 各执行字段独立变更、UUID / robot 作用域、原记录不覆盖、非法输入 |
| T02 / journal-order | 候选与公开接受分离、CAS / entry 去重、唯一意图、原句柄、终态保留与迟到事实 |
| T18 / journal-fault | 写前 / 写后失联、接受 / 意图 / 终态失败、读失败不冒充缺失、故障后新写入锁定 |

回归既有 383 项、依赖边界、sdist→wheel、空消费者和 README 示例。记录实际运行结果后才更新台账；REQ-009 为 DEVELOPING，I02 ACTIVE，产品验收保持 PENDING。
