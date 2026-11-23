# 只读 Registry 与有效能力

- 日期：2026-11-23
- 工作包：DEV-M1-04；[I01](../project/iterations/I01-M1-foundation.md) 的 T29/compose、T29/revision、T46/discovery、T46/readonly
- 基线：[身份 / 能力 / 状态契约](03-contracts-and-adapters.md)、[基础值](07-domain-types-and-geometry.md)

## 1. 范围与实现选择

本轮交付普通领域数据、纯能力组合、内存 Registry 和只读 SIM mock。使用 CPython 3.12.11、uv 0.10.9、零运行第三方依赖；所有代码保持依赖向内。这里的能力描述是内部领域切片，不是完整 HTTP Schema 或运行许可。

沿用既有分层：领域计算不保存 Registry 状态；应用 Registry 维护每个逻辑绑定的版本和发现结果；适配层提供只读样例。通用插件系统、持久化 Registry 和执行后端会超出 I01，因而采用最小内存实现。具体类名、版本初值和原因码由本轮实现确定，既有语义由项目契约约束。

只读绑定全部不持有执行端口，允许多个不同 robot_id 镜像同一 device_id。没有可写绑定、租约、激活、切换、恢复或实际设备连接。完整 StateProjection、状态新鲜度、事件序号与变换有效性由后续任务实现。

## 2. 纯能力组合：domain/capabilities.py

所有值对象采用 frozen dataclass + slots。输入类型错误抛 TypeError，非法值抛 ValueError；不把 bool / 数字 / 字符串相互隐式转换。只读 API 使用具体的数据类，而非可扩展的继承接口：能力、身份、观测及其嵌套值拒绝带行为的子类；后端通过 ReadOnlyBackend 组合这些普通值。执行归一化不能继承输入对象自定义的初始化行为，也不能把附带控制句柄的观测发布出去。此约束是数据契约，不是对恶意 Python 代码的沙箱。

- `CapabilityInputs(planning, model, frames, policy, execution, configuration_revision, mode)`：前五项必须为内置 bool；configuration_revision 为非空且无空白字符串；mode 为同样有效的字符串或 None，None 保留未知。五项为显式声明，不验证外部系统是否实际具备该能力。
- `UnavailableReason` 为字符串枚举，依次是 `planning_unavailable`、`model_unavailable`、`frames_unavailable`、`policy_unavailable`、`execution_unavailable`。
- `PoseGoalCapability(reasons)`：reasons 从 list / tuple 复制为不可变元组，元素必须为上述枚举，拒绝重复并按固定顺序归一化。`available` 由 reasons 是否为空计算，不能直接传入；`capability_id` 固定为 manipulation.pose_goal，`version` 固定为 1.0。这里只声明可用性，不暴露执行方法。
- `compose_pose_goal(inputs: CapabilityInputs) -> PoseGoalCapability`：五项全真才可用，返回全部缺失前提的有序原因；不看品牌或名称。
- `CapabilitySnapshot(revision, configuration_revision, mode, pose_goal)`：revision 是正的内置 int，拒绝 bool；其他字段类型严格验证，所有字段不可变。
- `revise_capabilities(inputs, previous=None) -> CapabilitySnapshot`：首次 revision=1；比较 configuration_revision、mode 与组合后的能力语义。相同语义保持版本，变化时 previous.revision+1；A→B→A 连续递增。该函数纯粹计算，调用方负责将 previous 保持在同一绑定内。

不可用原因变化也算语义变化，即使 available 始终为 false。状态读取次数、展示名称变化和等价的新对象不改变版本。配置 / 模式改变必须显式提供新值；未声明的外部变化无法被本轮推断。

## 3. 身份与只读数据：domain/discovery.py

复用 RobotId / DeviceId 和有限数校验，不将两种标识互换。以下值均 frozen + slots，不携带后端对象或任何控制句柄。

- `BackendKind`：SIM、REAL；`MotionState`：STOPPED、MOVING、UNKNOWN。传值必须为枚举成员，不接受裸字符串冒充枚举。
- `BackendIdentity(device_id, backend_id, backend_kind, backend_epoch)`：device_id 必须为 DeviceId；backend_id / epoch 非空且无空白；其余类型严格验证。
- `ReadOnlyBinding(robot_id, backend)`：robot_id 必须为 RobotId，backend 必须为 BackendIdentity；`read_only` 固定为 True，不能构造为可写。
- `BackendDescription(identity, name, capability_inputs)`：name 是非空且不全为空白的展示字符串（允许内部空格），另两个字段类型严格验证。name 不参加能力版本比较。
- `JointObservation(name, position_rad, velocity_rad_s)`：非空无空白的关节名；位置 / 速度分别为有限内置 int / float 或 None，已知值保存为 float。None 不变成零。
- `ReadOnlyObservation(joints, motion_state, control_mode, estop_active)`：joints 是 None 或 list / tuple 的 JointObservation，复制成 tuple，拒绝重名；motion_state 必须显式给出枚举；control_mode 为非空且不全为空白的字符串或 None，保留内部空格；estop_active 只能为内置 bool 或 None。空关节 tuple 表示已知没有关节，None 表示关节数据未知。
- `BackendState(identity, observation)`：严格验证上述两个值。
- `RobotDescription(binding, name, capabilities)`：为逻辑机器人提供绑定与 CapabilitySnapshot，字段严格验证。
- `RobotState(binding, observation, capability_revision)`：身份与实际观测分开，revision 正整数；`arming_state` 固定返回 DISARMED，表示本轮无应用激活。

这个状态切片提供关节、运动、模式和急停观测样例；工具位姿、时间来源 / 质量、新鲜度与状态序列仍属于后续 StateProjection。不得把 PoseGoal 当成实际反馈。没有观测的 mock 使用 joints=None、motion_state=UNKNOWN、control_mode=None、estop_active=None；不推断 STOPPED 或安全状态。

backend_epoch 在本轮是只读后端显式提供的不透明上下文。Registry 检查身份一致性，不生成或处理运行时换代；重连、重启和绑定切换另由后续任务实现。静态 SIM fixture 不代表现实设备身份已核验。

## 4. 端口、Registry 与 mock

在 `application/ports.py` 增加 `ReadOnlyBackend` Protocol，仅有 `describe() -> BackendDescription` 和 `read_state() -> BackendState`，保留原 MonotonicClock 不变。

`application/registry.py` 的 `RobotRegistry()` 使用内存保存条目，按单拥有者同步调用，不承诺线程安全或持久化：

- `register(robot_id: RobotId, backend: ReadOnlyBackend) -> RobotDescription`：检查 robot_id 和两个读方法，读取描述建立 ReadOnlyBinding；同 robot_id 重复注册抛 `DuplicateRobot(ValueError)`，不替换或提前调用新后端；不同 robot 可共享同一设备。验证成功后才保存条目。
- `describe(robot_id) -> RobotDescription`：读取最新描述，检查整个 BackendIdentity 与原绑定一致；不一致抛 `BindingMismatch(ValueError)`，保持已有条目。将执行前提强制置为 False，再调用 revise_capabilities；返回新不可变描述。
- `discover() -> tuple[RobotDescription, ...]`：按 robot_id.value 排序，按 describe 的身份 / 能力规则计算所有候选描述；全部读取成功并构造结果元组后才提交各绑定的能力版本。任一读取失败就传播异常，所有绑定保留此前发布的版本；空 Registry 返回空 tuple。这保证内存版本的批量提交，不承诺跨后端物理快照一致。
- `read_state(robot_id) -> RobotState`：读取当前描述并计算待发布的能力版本，再读取状态、检查类型和身份；全部验证成功后才保存能力版本并返回带原绑定的观测。失败不消耗尚未发布的版本，不推断或填默认值。读数和描述不声称是并发环境中的原子快照。
- 未知 robot 抛 `UnknownRobot(KeyError)`，错误 ID 类型抛 TypeError；无隐式创建、覆盖、自动重新绑定或静默吞掉后端错误。

Registry 只调用两个读方法，公开返回值不包含后端、端口、调用函数或句柄。即使注入的后端声明 execution=True，Registry 对外的 pose_goal 仍不可用。没有 submit / execute / plan / stop / reset / activate 等控制方法。

`adapters/mock_robot.py` 提供 `ReadOnlyMockBackend(description, state)`，frozen + slots，仅实现上述两个读方法。构造时验证类型、描述 / 状态的完整身份一致以及 backend_kind=SIM，并把自己的 capability_inputs.execution 归一为 False；不提供任何控制或状态修改方法，不调用外部系统。

## 5. 固定验证数据与切片

使用 robot=arm-fixture、device=mock-device-a，镜像 robot=arm-fixture-mirror；后端 fixture 为 backend_id=mock-backend-a、kind=SIM、epoch=fixture-epoch-a。能力 configuration_revision=fixture-config-1、mode=None；展示名可为 Fixture arm。这些是人工样例，不是设备配置。

| 切片 | 输入 / 改变 | 必须断言 |
| --- | --- | --- |
| T29/compose | 五项全真；逐项移除；全部缺失 | 纯函数可用正例；逐项正确原因；全缺失固定顺序；布尔类型严格；不看展示名称 |
| T29/revision | 相同 / 等价描述；缺失原因变化；配置或模式变化；A→B→A | 初值 1；重复不增；每次语义变更恰增 1；旧快照不变；None 不转成默认模式 |
| T46/discovery | 注册、排序、重复 / 未知 ID、描述 / 状态身份漂移、两个镜像 | 身份类型分离；不覆盖；明确报错；每绑定独立版本；失败不改绑定；可见描述与状态正确关联 |
| T46/readonly | 所有输入前提都真；空反馈；显式关节样例；额外控制方法诱饵 | 对外执行仍缺失；公开 mock / Registry 无控制方法；零控制调用；未知不填零 / STOPPED；观测不可变 |

同时扩展 T26 的仓库外安装探测、运行导入隔离和空消费者脚本，使新模块和只读发现样例实际来自已安装 wheel。README 保持项目主页结构，增加短只读发现示例与实际进度。四个切片通过后，I01 的十个技术切片齐备；产品验收仍 PENDING，须指定验收角色后判定，不能自动 CLOSED。
