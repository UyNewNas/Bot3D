# 开发台账

- 更新日期：2026-11-23
- 当前状态：13 项 TODO、5 项 DONE、13 项 DRAFT、2 项 DEFERRED
- 权威范围：本文件维护开发交付物、依赖和开发状态；需求与测试映射只维护在[追踪矩阵](requirements.md)
- 当前选择：[I02](iterations/I02-M1-control-loop.md)；DEV-M1-05 已完成，最终记录见 [AR-0020](records/AR-0020-control-authority-final.md)，下一工作包为 DEV-M1-06。[I01](iterations/I01-M1-foundation.md) 仍 IN_ACCEPTANCE，产品验收 PENDING

## 1. 使用规则

每行是一个可验收工作包；进入 DOING 时，在该轮 AR 中登记执行角色、代码 / 配置版本、开始条件和具体步骤。细分子任务沿用父 ID 加本轮清单，不复用或删除稳定 ID。

DONE 的共同条件：交付物存在、针对性检查或测试有实际记录、运行 / 复现说明可用、已知限制已登记。DONE 不等于需求 ACCEPTED；测试和验收结果只在[验收记录](acceptance.md)保存。正常等待前序仍是 TODO / DRAFT，真正无法推进时才标 BLOCKED 并关联原因、解除条件与影响。

前置开发仅表示交付依赖，不代替阶段准入、许可或现场授权。后续 DRAFT 必须在相应阶段锁定设备 / 版本 / 参数、拆出当轮切片及测试，再转 TODO；不将整行当作一次可无条件执行的命令。

## 2. M1：可执行任务

M1 不依赖 ROS、Gazebo、Unity 或厂商 SDK。普通领域类型与端口保持技术无关；只建立当期必要工程，不生成整棵架构空壳。内存 Journal 是测试替身，不能代替 M1 的 SQLite 持久化交付。

| 开发 ID | 状态 | 交付物与完成条件 | 前置开发 |
| --- | --- | --- | --- |
| DEV-M1-01 | DONE | [详细设计与决策记录](../design/05-runtime-coordination.md)、[DOC 检查记录](records/AR-0003-runtime-design.md)已交付；范围：状态 / 确定性转换表、业务槽与物理执行锁、STOP / CANCEL / UNKNOWN、最后下发边界、待下发撤销、接受 / 意图 / 外部受理顺序、崩溃点与对账；给出 T31 / T34 可执行测试设计。明确 epoch 不等于下游 fencing，不擅自增加公共命令状态；评审未决项与结论可追溯 | 无 |
| DEV-M1-02 | DONE | 已交付最小 Python 工程、纯领域 / 应用端口、可控单调时钟与测试基础。[工程基线](../design/06-python-foundation.md)固定 Python 3.12.11、开发依赖和复现命令，包安装 / 导入与依赖边界见 [AR-0007](records/AR-0007-foundation-boundary-recheck.md) | DEV-M1-01 |
| DEV-M1-03 | DONE | 已交付[标识 / SI 值、四元数 / 刚体变换与带工具目标](../design/07-domain-types-and-geometry.md)；三个 T28 切片使用独立基准点、轴、姿态和非法值断言，拒绝缺失与非法值，不填默认反馈；数值边界修正与工程回归见 [AR-0011](records/AR-0011-domain-foundation-final.md) | DEV-M1-02 |
| DEV-M1-04 | DONE | 已交付[能力组合 / 版本、不可变身份 / 观测、只读 Registry 与 SIM mock](../design/08-readonly-registry-and-capabilities.md)；T29 / T46 四个切片通过，共享设备镜像保留独立版本，身份漂移拒绝；缺失反馈保持未知且只读对象没有执行能力。证据见 [AR-0015](records/AR-0015-readonly-registry-batch-final.md) | DEV-M1-03 |
| DEV-M1-05 | DONE | 实现单写租约、显式激活与前置策略；租约绑定会话 / robot / epoch，按单调时钟续期 / 到期；READY、ARMED、运动状态分开；失权事件可进入停止用例，未结执行未处置时不能发放可执行控制流 | DEV-M1-04 |
| DEV-M1-06 | TODO | 实现 JournalPort、执行语义规范化摘要与内存测试替身；键为 robot_id＋command_id，request_id 不入摘要；覆盖同键重试和异摘要冲突；明确保留窗口接口，不把内存结果称为持久化保证 | DEV-M1-03 |
| DEV-M1-07 | TODO | 实现可控 Planner / Backend mock：计划、执行、原句柄查询、绑定级停止、反馈与可统计调用；注入拒绝、延迟、响应丢失与仍在运动；Planner 不自行执行，mock 不建立外部设备连接 | DEV-M1-04、DEV-M1-06 |
| DEV-M1-08 | TODO | 实现单机器人串行协调正常链路：规划也占唯一槽、接受后规划、前提复核、意图后下发、服务端 ResolvedExecution；无隐式运动队列；外部调用结果返回协调序列处理。与停止链联调完成前不宣称闭环可用 | DEV-M1-05、DEV-M1-06、DEV-M1-07、DEV-M1-12 |
| DEV-M1-09 | TODO | 实现取消、STOP、到期 / 超时、撤租与物理锁；落实 DEV-M1-01 的最后下发排序，撤销尚未越界的任务，已受理或未知时停止并对账；用可控屏障覆盖 T31，不依靠睡眠碰运气；无停车证据不得解锁 | DEV-M1-08 |
| DEV-M1-10 | TODO | 实现 SQLite 日志，锁定接受 / 意图 / 句柄 / 事件 / 终态事务、同步策略、存储假设与幂等保留；提供迁移和损坏 / 满盘处理说明；实际进程崩溃与异常注入分开验证，不宣称已证明断电可靠性或设备 exactly-once | DEV-M1-06、DEV-M1-08、DEV-M1-09 |
| DEV-M1-11 | TODO | 实现启动恢复与原句柄对账：新 epoch、撤旧租约、DISARMED、不重放；分别处理历史结果、当前停车、旧执行者失效；明确可审计解锁条件并保留原 UNKNOWN 历史；覆盖接受与外部受理之间的各崩溃点 | DEV-M1-09、DEV-M1-10、DEV-M1-12 |
| DEV-M1-12 | TODO | 实现 StateProjection、源 / 接收时间、序号、来源与质量；目标 / 计划 / 实际分离；乱序、重复、延迟与不同 clock_id 有确定规则；配置并验证静止窗口和反馈新鲜度，FK 标 DERIVED | DEV-M1-04 |
| DEV-M1-13 | TODO | 实现三类资产清单、工具映射与坐标 / 标定快照；版本、来源、有效性、许可和转换损失可追踪；模型 / 场景 / 工具 / 标定变化使旧计划失效，执行中按策略停止，不暗换轨迹 | DEV-M1-03、DEV-M1-04、DEV-M1-09 |
| DEV-M1-14 | TODO | 实现受控绑定切换：冻结、旧后端停止确认、撤租、新 epoch、目标只读 DISARMED；旧包 / 旧反馈失效；任何失败保持冻结 / 未激活，不自动回滚为旧可写绑定 | DEV-M1-11、DEV-M1-13 |
| DEV-M1-15 | TODO | 实现同一协调序列生成的快照与游标、独立 state_seq / event_seq、关键事件保留及 RESYNC_REQUIRED；内存消费者重连只查询，不重放输入；真实 WS 留待 M3 | DEV-M1-11、DEV-M1-12 |
| DEV-M1-16 | TODO | 实现有界通路、状态合并、慢消费者处理、阻塞调用隔离与独立停止 / 失权路径；注入规划 / SDK / 日志阻塞与满盘；关键日志不可写时拒新运动，但停止不等待普通日志；记录负载与时延，不声称硬实时 | DEV-M1-09、DEV-M1-10、DEV-M1-15 |
| DEV-M1-17 | TODO | 实现关联日志、分段时延、队列 / 质量指标与健康 / 就绪 / 可运动条件；凭据脱敏、标签有界，提供本地保留及诊断说明；通过可重复输入核对事件关联，不把进程存活当作设备可运动 | DEV-M1-11、DEV-M1-12、DEV-M1-16 |
| DEV-M1-18 | TODO | 实现显式可信配置、依赖组装、同机单实例和有序停机；拒绝不可信插件与跨主机双写配置；停机先禁运动、停止并确认，未知执行不解锁；补最小运行说明和 M1 回归入口，不把强杀当作停车方法 | DEV-M1-11、DEV-M1-14、DEV-M1-16、DEV-M1-17 |

### 建议迭代分配

- I01：DEV-M1-01—DEV-M1-04，详细设计、最小工程、类型与只读发现；见已建立的[迭代定义](iterations/I01-M1-foundation.md)。
- I02：DEV-M1-05—DEV-M1-09、DEV-M1-12，先完成状态投影与测试替身，再接执行和停止；未通过停止与最终下发竞态，不关闭执行切片。
- I03：DEV-M1-10、DEV-M1-11、DEV-M1-13—DEV-M1-18，持久化、恢复、上下文、切换、事件、背压与运行边界。

以上不是任务的实际执行顺序；按“前置开发”拓扑顺序选择。I02 已建立[正式迭代文件](iterations/I02-M1-control-loop.md)与最低验收清单；I03 仍为建议分配，开始前按[验收规则](acceptance.md)锁定当轮范围。

## 3. M2—M5 与扩展工作包

| 开发 ID | 状态 | 交付物与完成条件 | 前置开发 |
| --- | --- | --- | --- |
| DEV-M2-01 | DRAFT | 固定首个 ROS / Gazebo / MoveIt / 控制器 / 模型组合及精确版本、许可、配置和适配器交付卡；核对 namespace、joint 顺序、工具、Action 类型、QoS 与反馈来源；错误配置不得 READY | DEV-M1-18 |
| DEV-M2-02 | DRAFT | 实现 MoveIt 只规划、轨迹 Action 唯一执行的 SIM 闭环；核验场景同步、起点、真实仿真反馈和停车；拒绝、断线、响应丢失不盲重试；发现第二执行者时不得通过准入 | DEV-M2-01 |
| DEV-M2-03 | DRAFT | 实现受权 SIM pause / resume / step / reset；REAL 入口拒绝；应用保护钟独立，reset / 回退使上下文和旧状态失效 | DEV-M2-02 |
| DEV-M2-04 | DRAFT | 实现 Recorder、rosbag2 与事件 / 配置 / 模型 / 标定关联；验证可复现场景与脱敏保留；隔离回放不取得 REAL 写权限 | DEV-M2-02 |
| DEV-M3-01 | DRAFT | 实现版本化 HTTP / WS 网关、严格 JSON / Schema、身份与资源权限；共用应用用例，拒绝底层接口透传；跨主机连接方案与威胁边界经验证 | DEV-M1-18 |
| DEV-M3-02 | DRAFT | 实现会话、WS 状态 / 事件续接、时钟采样、背压和重连；失联处理控制权及在途任务；查询不执行，不恢复旧租约、激活或缓存动作 | DEV-M3-01 |
| DEV-M3-03 | DRAFT | 实现普通屏幕与 XR 共享目标语义、预览 / 确认 / 计划 / 实际反馈；始终显示 SIM / REAL、设备和绑定身份；用完整仿真任务验收而非只看动画 | DEV-M2-02、DEV-M3-02 |
| DEV-M3-04 | DRAFT | 锁定 Unity / OpenXR / 插件 / 输入设备组合；验证坐标尺度、手性、姿态和跟踪失效、重定位 / 原点重置；冻结、停止、失效与重新确认有设备证据 | DEV-M3-03、DEV-M1-13 |
| DEV-M4-01 | DRAFT | 在明确授权后形成真实设备卡、许可与原生控制权核验、只读身份 / 模式 / 状态准入；记录现场规程、保护阈值和批准工况；资料或保护未知不得启用 REAL 运动 | DEV-M2-01、DEV-M1-18 |
| DEV-M4-02 | DRAFT | 按独立批准工况验证实体急停、限位、本地看门狗 / 执行守护、停车反馈及外部 / 旧执行者处置；包含网关消失但驱动在线；不能证明完整停车链则只读，禁止直接照搬仿真故障脚本 | DEV-M4-01、DEV-M3-04 |
| DEV-M4-03 | DRAFT | 让同一任务级代码分别在该机器人 SIM 与获准 REAL 完成共同任务；重新绑定 / 标定 / 授权 / 规划，保存误差和差异；不以重放仿真轨迹达成 | DEV-M4-02、DEV-M2-02 |
| DEV-M5-01 | DRAFT | 锁定第二仿真器和共同任务；保持任务代码，新增适配器 / 模型 / 参数；分别保存成功、误差、转换损失和限制证据，不要求轨迹数值一致 | DEV-M2-02、DEV-M2-04 |
| DEV-M5-02 | DRAFT | 锁定第二机器人及两端 SIM / REAL 层级、共同成功任务；保持任务代码，记录能力、模型、工具和规划配置差异；缺能力正确拒绝不替代迁移成功，涉及 REAL 另过准入 | DEV-M2-02、DEV-M2-04 |
| DEV-M5-03 | DEFERRED | 选定第二 XR 前端 / 设备后，复用机器人契约与任务用例；验证输入 / 坐标 / 显示差异与各自跟踪失效；需另行选择范围，不阻塞 M1—M5 的当前必验项 | DEV-M3-04 |
| DEV-OPT-01 | DEFERRED | 有明确媒体需求后定义独立数据链、带宽、背压、授权、隐私与降级；拥塞 / 故障不阻断停止，媒体不承载运动；需另立扩展迭代 | DEV-M3-02 |

纯仿真迁移可在 G-M2 基线后准备和验证，不等待 M4 的真机操作授权；它不关闭仍需 REAL 的 AC。使用网关 / XR 的迁移必须先满足对应环境准入；引入任何真实设备都需要该设备独立的授权和保护证据。

## 4. 本轮交接

DEV-M1-01 的详细设计与 DOC 检查见 [AR-0003](records/AR-0003-runtime-design.md)。DEV-M1-02 的依赖边界修正见 [AR-0007](records/AR-0007-foundation-boundary-recheck.md)。DEV-M1-03 基础类型见 [AR-0011](records/AR-0011-domain-foundation-final.md)，DEV-M1-04 的能力组合与只读发现见 [AR-0015](records/AR-0015-readonly-registry-batch-final.md)。DEV-M1-05 控制权已完成，十四个切片与工程回归见 [AR-0020](records/AR-0020-control-authority-final.md)。I01 为 IN_ACCEPTANCE，I02 ACTIVE，产品验收 PENDING；下一工作包为 DEV-M1-06。
