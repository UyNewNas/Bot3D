# 领域契约与适配器 v0.1

- 日期：2026-11-19
- 状态：待评审的协议草案；类型、API 路径和 JSON 均为设计示例，尚无实现或生成的 Schema
- 关联：[原则](01-principles-and-scope.md)、[架构](02-system-architecture.md)、[验收](04-delivery-and-validation.md)

## 1. 契约分界与版本

公共契约表达机器人能力、目标、状态和控制权；后端端口表达已经解析的执行请求。ROS 消息、厂商错误码和 Unity 类型不得直接成为公共类型。

- URL 的 /v1 表示主版本；消息中的 api_version 使用主 / 次版本，例如 1.0。
- 增加可选字段可作为兼容变更；改变单位、坐标含义、必填项或状态语义必须升级主版本。
- 未知命令类型、枚举和必填语义直接拒绝，不按猜测降级。扩展字段须在明确的 extensions 区域协商。
- 输入拒绝重复 JSON 键、NaN / Infinity、超长数组和越界数值；数值范围必须有单位和来源。
- 各通道共享同一应用用例，不能出现 HTTP 和 WebSocket 各自下发一次运动的逻辑。

## 2. 身份、绑定与上下文

| 字段 | 含义 / 生命周期 |
| --- | --- |
| robot_id | 稳定的逻辑机器人 ID，例如 arm-main；不是 IP 地址 |
| device_id | 核验后的物理设备身份；SIM 使用明确的仿真实例身份，不能伪装成真机序列号 |
| backend_id | 适配配置 / 后端实例 ID；网络地址变化不等于设备身份不变 |
| backend_kind | SIM 或 REAL，只由服务端绑定决定 |
| backend_epoch | 每次绑定、后端连接重建、协调服务重启或关键上下文失效后生成的新不透明代次，不复用 |
| session_id | 鉴权会话；消息身份从已认证连接获得，不信任正文自报身份 |
| lease_id | 绑定会话、机器人和代次的控制租约；到期或撤销后不可复用 |
| command_id | 客户端生成的不可复用 UUID；示例用短名称便于阅读 |
| request_id | 单次请求关联 ID，不承担幂等或身份认证功能 |
| capability_revision | 当前有效能力集版本；模式、配置或可用性变化时更新 |
| robot_model_revision | 结构、关节映射、限位、碰撞和工具配置的可追踪版本 |
| scene_revision | 本次规划使用的场景对象 / 障碍版本 |
| calibration_revision | 场景、机器人、XR / 传感器变换的标定版本 |

即使 backend_id 不变，backend_epoch 改变也必须重新获取能力、状态和租约。同一物理 device_id 只允许一个可写绑定；只读镜像不具有运动能力。

## 3. 能力模型

能力由能力 ID、语义版本、参数 Schema、范围、前置条件、完成判据和停止语义组成。能力声明分为后端原生能力和应用组合出的有效能力；对前端只公布当前有效能力及不可用原因。

| 能力族 | 首版语义 | 边界 |
| --- | --- | --- |
| manipulation.pose_goal | 指定工具在指定坐标系中的目标位姿 | 需规划 / 原生任务支持；不是保证可达 |
| gripper.set_width | 夹爪开口宽度，单位 m | 仅用于实际支持宽度控制的夹爪；吸盘不是该能力 |
| system.stop | 请求当前绑定执行受控停止并等待确认 | 不是物理急停；允许独立授权，不要求持有运动租约 |
| simulation.pause / step / reset | 操作仿真运行时间或场景 | 独立管理端口，仅 SIM，不能映射成真机运动 / 停车 |
| mobility.navigate_to 等 | 后续能力族预留 | 本轮不定义移动机器人、无人机或人形机器人的通用 move |

能力参数范围不能凭机器人品牌猜测。夹爪宽度、速度、工具坐标和可用控制模式来自设备配置和验证记录。速度比例只能降低已配置上限，不能绕过厂商限制。

能力描述示例（虚构数据，不是实际设备发现结果）：

```json
{
  "api_version": "1.0",
  "robot_id": "arm-main",
  "backend_id": "gazebo-arm-demo",
  "backend_kind": "SIM",
  "backend_epoch": "epoch-sim-07",
  "capability_revision": 3,
  "robot_model_revision": "arm-model-r1",
  "capabilities": [
    {
      "id": "manipulation.pose_goal",
      "version": "1.0",
      "execution_strategy": "planned_trajectory",
      "required_context": ["scene_revision", "calibration_revision", "tool_id"],
      "limits": {"speed_scale_min": 0.01, "speed_scale_max": 0.2},
      "completion_policy": "controller_result_and_fresh_goal_check"
    },
    {
      "id": "system.stop",
      "version": "1.0",
      "requires_motion_lease": false,
      "confirmation_policy": "backend_status_and_stationary_window"
    }
  ]
}
```

stationary_window 的阈值、持续时间和可信反馈来源属于设备验证配置，不能用这个字符串替代实际停车验证。

## 4. 单位、坐标与时间来源

- 领域长度使用 m、角度使用 rad、时间间隔使用 s；明确带 _ms 后缀的期限 / 超时字段使用 ms。
- 四元数使用 [x, y, z, w]，必须有限且满足归一化容差；q 与 -q 表达同一旋转。
- 领域坐标使用右手系；基座 / 世界的默认轴约定为 x 前、y 左、z 上。光学帧等例外必须显式命名并通过变换接入。
- frame_id 是有作用域的 ID，例如 cell/world、arm-main/base_link；禁止缺少坐标系的裸 pose。
- T_A_B 表示把 B 中坐标变换到 A。变换必须有来源、标定版本、时间及有效性；动态变换还需要对应采样时刻，不能静默使用最新值冒充历史值。
- Unity / XR 边界以显式基变换处理轴、左右手系和尺度。位置与旋转分别正确转换；旋转矩阵按 R' = C R C^-1 变换，不凭经验随意取反某个四元数分量。轴向量也要单独测试。
- XR 重定位、原点重置和跟踪丢失会使相关变换失效；冻结新目标，已执行运动请求停止，并重新标定 / 确认。
- 状态同时携带源时间与网关接收时间，并标注 clock_id。仿真时间、设备时间和网关单调时间不能直接相减。

## 5. 命令信封与目标

以下为离散末端目标示例；数值、ID 和时间均仅用于说明。robot_id 必须与入口路径 / 会话授权一致；session_id 由服务端认证上下文提供。

```json
{
  "api_version": "1.0",
  "type": "command.submit",
  "request_id": "req-1042",
  "command_id": "cmd-1042",
  "robot_id": "arm-main",
  "backend_epoch": "epoch-sim-07",
  "lease_id": "lease-op-03",
  "capability_revision": 3,
  "capability": "manipulation.pose_goal",
  "context": {
    "robot_model_revision": "arm-model-r1",
    "scene_revision": "cell-r4",
    "calibration_revision": "cal-sim-r2",
    "tool_id": "tool0"
  },
  "timing": {
    "clock_id": "gateway-clock-01",
    "admit_before_ms": 158040,
    "start_before_ms": 162540,
    "execution_timeout_ms": 30000
  },
  "parameters": {
    "goal": {
      "frame_id": "cell/world",
      "position_m": [0.3, 0.05, 0.25],
      "orientation_xyzw": [0.0, 0.0, 0.0, 1.0]
    },
    "constraints": {
      "speed_scale": 0.1,
      "position_tolerance_m": 0.005,
      "orientation_tolerance_rad": 0.05
    }
  }
}
```

有效能力配置限定可用工具、坐标系、容差和速度范围；客户端不能通过放大容差绕过完成判据。规划成功也不覆盖下发前的当前状态检查。

规划结果须记录关节名称、轨迹、起始状态、有效版本和计划摘要。若当前关节偏离起始状态超过设备配置阈值，必须重新规划或拒绝，不能执行旧计划。

## 6. 状态与事件

状态快照至少包含：

| 类别 | 字段 / 规则 |
| --- | --- |
| 身份 | robot_id、device_id、backend_kind、backend_epoch |
| 可用性 | readiness：OFFLINE / INITIALIZING / READY / DEGRADED / FAULTED |
| 激活 | arming_state：DISARMED / ARMED；ARMED 只是应用许可，不自动给设备上电 |
| 物理运动 | motion_state：STOPPED / MOVING / UNKNOWN，与命令生命周期分开 |
| 实际状态 | 命名关节的位置 / 速度、工具位姿、实际控制模式及可读取的急停 / 保护状态；不可获取的量明确未知，不得填零或默认安全 |
| 目标状态 | 当前任务目标 / 计划引用，明确与 actual 分开 |
| 控制与任务 | 租约持有者的非敏感标识、当前命令、待对账执行记录 |
| 时序 | 源时间 / 时钟、网关接收时间、源序号、state_seq |
| 质量 | 每类数据的 MEASURED / SIMULATED / DERIVED 来源及 FRESH / STALE / UNSYNCED / INVALID 状态 |
| 上下文 | 能力、模型、场景、标定版本和错误原因 |

由编码器与正运动学计算的末端位姿标为 DERIVED，不冒充外部测量。STOPPED 需要配置的可信后端状态与静止判据；没有反馈时显示 UNKNOWN，而不是默认停车。READY 不表示已获得安全认证，也不代表具备租约或已经 ARMED。

命令事件示例：

```json
{
  "api_version": "1.0",
  "type": "command.event",
  "event_stream_id": "stream-01",
  "event_seq": 28,
  "robot_id": "arm-main",
  "backend_epoch": "epoch-sim-07",
  "command_id": "cmd-1042",
  "command_state": "EXECUTING",
  "motion_state": "MOVING",
  "result_certainty": "PENDING",
  "clock_id": "gateway-clock-01",
  "observed_at_ms": 159200
}
```

- state_seq 用于识别状态更新和合并；event_seq 在 event_stream_id 内排序，两者不是同一个序列。
- 订阅先返回快照和事件游标，再发送增量；快照与游标由同一机器人协调器串行生成。
- 慢客户端可跳过中间状态，不能静默丢失关键命令事件。事件缓冲耗尽则断开 / 要求重同步。
- 重连后重新读取快照和未结命令；事件游标失效时显式 RESYNC_REQUIRED。不能仅靠前端最后一次动画或 WS 重连推断执行结果。

## 7. 控制权与激活

1. viewer 可以订阅；operator 在设备和上下文满足前提时申请控制租约。首版不提供无确认的租约抢占。
2. 租约绑定 session_id、robot_id、backend_epoch，服务端以单调时钟管理到期；续租不改变原有命令含义。
3. 获得租约不等于激活。REAL 必须经过身份、模式、停车、标定及本地保护检查与操作者确认，才允许 ARMED。
4. 租约释放、到期、会话丢失或权限撤销时阻止新运动，并对运行中的任务发起停止；确认前保持运动槽锁定。
5. 重连不自动恢复租约、激活状态或在途控制流。新操作者不能覆盖未知运动。
6. system.stop 不要求运动租约、场景有效或时钟同步，但仍须鉴权、停止权限和明确目标绑定；旧代次的停止不能悄悄改为停止另一台新设备。
7. 物理急停不经过上述租约与网络协议；软件 API 不提供“等同实体急停”的承诺。
8. system.stop 同时撤销运动租约并进入 DISARMED；租约失效、显式取消激活、执行超时和关键状态故障也使应用进入 DISARMED，并对在执行任务请求停止。停车确认不会自动重新激活。普通任务取消在确认停车且其余前提仍有效时可以保留原租约，但不隐含下一条运动。

## 8. 命令生命周期与幂等

| 状态 | 含义 | 是否业务终态 |
| --- | --- | --- |
| REJECTED | 不满足接受条件，没有下发 | 是 |
| ACCEPTED | 已记录并占用任务槽，尚不代表开始运动 | 否 |
| PLANNING | 正在规划，可因取消或上下文变化终止 | 否 |
| DISPATCHING | 已持久化下发意图，外部受理结果可能尚不清楚 | 否 |
| EXECUTING | 后端已受理；实际是否运动仍看反馈 | 否 |
| CANCEL_REQUESTED | 已请求取消 / 停止，等待结果 | 否 |
| SUCCEEDED | 后端完成，且通过新鲜目标反馈与停车判据 | 是 |
| CANCELLED | 证明未下发，或已确认任务取消且停车 | 是 |
| FAILED | 规划或执行失败；是否停车另看实际状态 | 是 |
| TIMED_OUT | 超过应用超时；不说明物理动作已停止 | 是 |
| INTERRUPTED | 服务 / 绑定中断，原命令不再继续调度 | 是 |

result_certainty 分为 PENDING、CONFIRMED、UNKNOWN。业务终态与运动锁分开：FAILED / TIMED_OUT / INTERRUPTED 可以同时具有 UNKNOWN 结果和未解决的物理执行记录，此时继续拒绝新运动。终态业务结论保留，后续对账追加事实，不篡改历史事件。

### 幂等规则

- 以 robot_id + command_id 查询幂等记录。摘要包含所有影响执行的字段，包括代次、目标、约束、上下文和期限；request_id 不计入。
- 同键同摘要返回原接受 / 执行结果，不再次下发；同键不同摘要返回 IDEMPOTENCY_CONFLICT。
- 先鉴权，再查已知命令。重复请求只返回有权限查看的原记录，不因旧租约失效而重新执行。
- 对新命令，在机器人协调器内完成校验、占槽和持久化；成功后才回复 ACCEPTED。日志不可用则拒绝新运动。
- 幂等保留窗口由服务声明，不承诺无限期去重。command_id 永不复用；过期命令不能靠刷新期限或换传输通道变成重试。
- 后端响应丢失时先查询原句柄；没有可核对句柄或结果时标记未知，不自动再次 submit。
- 停止不因普通运动日志故障被阻塞；尽可能写独立应急审计，但不能以等待磁盘为停车前提。

最后校验、占槽和下发意图在同一协调序列内处理；异步规划返回后必须检查取消标记、代次和租约。撤租 / STOP 到达后，旧规划结果不得继续下发。数据库与外部执行仍不存在跨系统原子提交，不能宣称 exactly-once。

## 9. 时间与失效语义

| 时间 / 限制 | 定义 |
| --- | --- |
| 网关 clock_id | 每次运行生成新标识，时间值为该网关单调时钟域中的 ms |
| admit_before_ms | 最晚完成新命令接受的网关时间；过期拒绝，不从收到时重新计算 |
| start_before_ms | 最晚开始向后端下发的网关时间；规划和排队不能无限延长目标寿命 |
| execution_timeout_ms | 从 DISPATCHING 起到完成的应用预算，包含等待后端受理；到期发起停止而非假定停车 |
| 租约期限 | 服务端单调时间控制的持权期限，任务执行中也要续租 |
| 状态年龄 | 源采样年龄与接收年龄分别计算，需要明确时钟映射和不确定度 |
| 设备看门狗 / 本地守护 | 本地失联与持权失活处理，须覆盖网关消失但驱动仍在线；独立于应用超时 |

客户端通过时间同步往返样本获得网关时钟偏移区间，并按保守下界构造期限；不假定单向延迟对称。服务端维护时间同步健康、最大期限跨度和允许的不确定度，不采信正文自报“已同步”。不确定度过大时拒绝新运动，但不阻断授权停止。

admit_before_ms 不得晚于 start_before_ms，且两者均受能力 / 部署配置的最大跨度限制。已知重复命令仍可返回历史结果，但不得重新执行。网关重启后旧 clock_id 和 backend_epoch 一并失效。

start_before_ms 是下发期限，不是保证电机在指定时刻开始；若后端会隐式长时间排队，该执行方式须在首版禁用。需要精确定时启动时，必须另行验证控制器时钟与调度能力。

仅使用“从接收开始的 TTL”不能识别接收前已经延误的命令；仅使用接收时间也不能证明源状态新鲜。设备源时钟不能可靠映射时标为 UNSYNCED，并按能力策略禁用需要可信新鲜状态的 REAL 运动。

仿真 pause、加速和回退不改变租约、看门狗或应用超时的单调时间。仿真 reset / 回退须失效旧执行上下文并更新代次，防止旧状态和旧命令混入新世界。

## 10. 适配器端口

以下是职责级接口，不是已经存在的函数。端口传递不可变领域数据与结构化错误，不透传 SDK 对象。

| 端口 | 操作职责 | 必须返回 / 保证 |
| --- | --- | --- |
| PlannerPort | 描述规划能力、plan、cancel | 计划或不可达原因；起始状态、模型 / 场景 / 标定版本和轨迹摘要；不自行执行 |
| RobotBackendPort | 连接 / 核验身份、describe、订阅状态 | 原生能力、真实模式、状态质量、停止 / 失联语义；连接不自动启动运动 |
| RobotBackendPort | execute、query | 已解析的轨迹或原生目标、后端执行句柄、受理 / 完成 / 未知结果；不隐式重试运动 |
| RobotBackendPort | request_stop、关闭连接 | StopReceipt 只确认请求处理情况；停车另由可信反馈确认，关闭连接不等于停止 |
| SimulationControlPort | pause、resume、step、reset | 仅作用于 SIM；重置必须失效旧执行上下文 |
| JournalPort | 幂等查询、记录接受、下发意图、事件与终态 | 事务性本地记录与明示保留窗口；不提供外部动作原子性 |

execute 只接收服务端构造的 ResolvedExecution：命令 ID、目标绑定、执行策略、经过验证的计划 / 原生目标及限制。公共前端不能上传任意轨迹句柄或伪造内部规划结果来绕过检查。

### ROS 2 首条适配路径

- PlannerPort 使用 MoveIt 的规划接口；执行只走已配置的轨迹 Action。具体驱动若要求其他执行链，应替换该策略并重新验收，而不是叠加第二个下发者。
- 命名空间、joint 名称、工具、Action 名 / 类型、反馈 topic / 类型和 QoS 都由适配配置明确声明。
- 状态优先采用来源明确、与配置匹配的关节与控制器反馈；消息类型相同不代表坐标、单位和时序相同。
- QoS 配置按状态与任务分别核对；可靠传输不代表数据新鲜，也不代表运动已经完成。
- 仿真 ROS 节点可使用仿真时钟；REAL 节点不得误用仿真 /clock。应用保护时钟始终独立。
- 规划场景与 SceneFrameService 的版本须对齐；没有发布成功 / 同步确认时，不宣称新障碍已进入规划器。

### 每个适配器的交付卡

1. 设备 / 仿真器、固件、SDK、OS、ROS、控制器、许可证和精确版本。
2. 电气 / 网络要求、设备身份核验、原生控制权和只读连接方式。
3. 能力、单位、关节名称与顺序、坐标、工具和限制来源。
4. 下发、受理、开始、完成、取消、超时、断线和重连的实际语义。
5. 失联处理、停车命令、停车确认、反馈陈旧阈值与实测时延。
6. 标准错误映射、原生错误可追踪字段、不可确定的状态及禁用条件。
7. 配置 / 资产版本、契约测试证据和已知限制。

不能证明停止 / 失联行为或状态新鲜度时，可以提供只读适配，但不能开放 REAL 运动能力。

## 11. 应用接口草案

| 接口 | 用途 / 权限 |
| --- | --- |
| GET /v1/robots | 授权范围内的机器人和绑定摘要；viewer |
| GET /v1/robots/{robot_id}/capabilities | 当前能力、版本及不可用原因；viewer |
| GET /v1/robots/{robot_id}/state | 状态快照与事件游标；viewer |
| GET /v1/robots/{robot_id}/commands/{command_id} | 命令、结果确定性和待对账情况；有权限的读取者 |
| GET /v1/time | 网关时钟样本；结合往返测量，不单凭一次响应认定同步 |
| POST /v1/robots/{robot_id}/leases | 申请控制租约；operator |
| POST /v1/leases/{lease_id}/renew | 续租；原会话 |
| DELETE /v1/leases/{lease_id} | 释放 / 撤销；释放触发在执行任务的停止流程 |
| POST /v1/robots/{robot_id}/activation | 显式请求应用激活 / 取消激活；当前操作者，检查实际前提 |
| POST /v1/robots/{robot_id}/backend-binding | 执行受控后端切换；administrator，不是普通运动参数 |
| POST /v1/robots/{robot_id}/stop | 授权停止的独立入口，调用同一停止用例；不要求运动租约 |
| GET /v1/stream | WebSocket 升级入口：订阅、命令、取消、停止、时间同步 |

首版普通运动仅使用 WebSocket command.submit；HTTP 管理与查询不另建运动执行器。stop 的 HTTP / WS 入口共享幂等、目标校验和优先处理路径。simulation 管理入口独立鉴权，具体资源路径在实现该能力时定版。

取消请求必须引用 command_id 和目标绑定，并核对权限。所有异步回执关联 request_id / command_id；没有收到响应时先查询，而不是生成新 ID 再试一次运动。

## 12. 标准错误

| 错误码 | 含义 / 恢复方向 |
| --- | --- |
| UNSUPPORTED_VERSION / CAPABILITY_UNAVAILABLE | 版本或能力不支持；重新发现能力，禁止静默改语义 |
| UNAUTHORIZED / FORBIDDEN | 身份或权限不足；不泄露其他设备详情 |
| LEASE_REQUIRED / LEASE_EXPIRED / BUSY | 缺控制权、已过期或运动槽占用；不自动排队 |
| STALE_BACKEND_EPOCH | 旧绑定消息；读取新上下文，不直接把旧目标换 ID 重发 |
| CONTEXT_CHANGED | 能力 / 模型 / 场景 / 标定 / 工具前提改变；重新确认目标 |
| STATE_STALE / MOTION_BLOCKED | 状态不可信、未激活或运动未解决；先恢复观测 / 确认停车 |
| CLOCK_UNCERTAIN / ADMISSION_EXPIRED | 时钟质量不足或接受期限过期；停止不受时钟同步门槛阻断 |
| START_DEADLINE_EXCEEDED | 未在期限内下发；终止该目标，不延长原命令 |
| IDEMPOTENCY_CONFLICT | 相同命令 ID 对应不同请求；调查客户端逻辑 |
| PLANNING_FAILED / BACKEND_REJECTED | 不可达或后端拒绝；保留可解释原因 |
| EXECUTION_UNKNOWN / STOP_UNCONFIRMED | 执行结果或停车不能确认；禁止后续运动，进入对账 / 现场处理 |
| RATE_LIMITED / STORAGE_UNAVAILABLE | 资源不足；拒绝新运动，保留停止通路 |
| RESYNC_REQUIRED | 增量流无法续接；重新读取快照和未结命令 |

错误结构包含 code、message、request_id、可选 command_id、当前代次及可公开的原因；不返回凭据、完整内部堆栈或任意 SDK 对象。retryable 只表达某个用例可再次尝试，不授权自动重放运动；需要新运动意图时必须由操作者重新确认。
