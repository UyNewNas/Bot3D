# 控制租约、显式激活与失权交接

- 日期：2026-11-23；工作包：DEV-M1-05；迭代：[I02](../project/iterations/I02-M1-control-loop.md)
- 约束来源：[身份 / 控制权契约](03-contracts-and-adapters.md)、[串行与失权设计](05-runtime-coordination.md)、[REQ-005—007](../project/requirements.md)

## 1. 范围与选择

本轮交付独立的内存 ControlAuthority、普通不可变领域值和纯前置策略；以已合并 ffae464 的 303 项基线继续。沿用 CPython 3.12.11、uv 0.10.9、pytest 8.4.2，运行第三方依赖为零。

既有 RobotRegistry、ReadOnlyBinding、只读 SIM mock 及其执行能力始终保持只读。控制权管理器的绑定由可信组装代码显式配置，只承载应用许可，不携带后端控制端口，也不实际规划、执行、停止或给设备上电。认证本身由未来接入层完成；本轮登记认证后的会话授权事实，不接受每次请求自报的权限。ActivationEvidence 也只能由可信协调器提交其当前采纳的投影，不能将客户端证据直接透传；时效窗口本身不证明证据是最新采纳的版本。

选择独立的同步内存管理器：短临界区同时保护租约、arming、会话撤销和未结执行标记，避免检查与修改分离。扩展只读 Registry 会混淆既有保证；提前建立整个协调器会跨入 DEV-M1-06—09 / 12。后续协调器必须在同一应用裁决序列中消费本轮结果，再处理外部 I/O；本轮 check 的返回不是可延后消费的下发票据。

数据 / 生命周期 / API 名称和固定 fixture 是本轮实现选择。运行时 epoch 生成 / 切换、真实认证协议、完整 StateProjection、Journal、执行 / STOP 实现、持久事件流和跨进程单写均不在本轮范围。

## 2. 领域值：domain/control.py

所有新数据类 frozen + slots；严格接受具体领域类型，拒绝带行为的子类及嵌套非普通值。字符串必须是内置 str，ID 非空无空白；计数和持续时间是内置 int（拒绝 bool），布尔字段是内置 bool，未知事实用 None。复用 RobotId、BackendIdentity、MotionState、CapabilitySnapshot、MonotonicInstant，不修改原类。

- `Readiness`：OFFLINE / INITIALIZING / READY / DEGRADED / FAULTED；`ArmingState`：DISARMED / ARMED，均为字符串枚举。
- `ControlBinding(robot_id, backend, read_only)`：RobotId、BackendIdentity、显式 bool；只是可信组装数据。配置时一个 robot 只能出现一次，同一 DeviceId 最多一个 read_only=False 的绑定；允许只读镜像，不以不同 epoch / backend_id 绕过设备独占。
- `SessionAuthorization(session_id, robot_ids)`：非空 ID，list / tuple 的具体 RobotId 复制为 tuple，拒绝重复。空授权列表表示没有控制权限。该值由可信认证调用方提交，不是身份凭据。
- `ActivationEvidence(binding, capabilities, readiness, motion_state, observed_at, valid_until, identity_verified, mode_permitted, calibration_valid, local_protection_ready, native_control_exclusive, standstill_verified)`：前六项分别为具体 ControlBinding、CapabilitySnapshot、Readiness、MotionState、两个具体 MonotonicInstant。后六项为 bool 或 None。两个时刻同 clock_id 且 observed_at < valid_until；保护钟域中的有效期由可信投影提供，本轮不推算源钟、新鲜度或静止窗口。
- `ControlLease(lease_id, session_id, binding, issued_at, expires_at, capabilities, grant_generation)`：新鲜不复用的内部 opaque lease_id；绑定必须可写，expires_at > issued_at、同保护钟域；grant_generation 非负，取得租约时等于该绑定当前 revoke_generation。lease_id 从 repr 隐藏；续租保留 ID、会话、完整绑定、初始时刻、能力上下文和 grant_generation。
- `AuthoritySnapshot(binding, arming_state, lease_owner, lease_expires_at, execution_blocked, revoke_generation, clock_faulted, binding_retired)`：lease_owner / lease_expires_at 同时有值或同时 None；不包含 lease_id 或解除执行标记。有 owner 时必须可写、无执行锁、时钟健康且绑定未退役；ARMED 另要求存在 owner。readiness 和 motion 属于独立的 ActivationEvidence，不能从 ARMED 推断。
- `AuthorityLossReason`：RELEASED / EXPIRED / SESSION_LOST / PERMISSION_REVOKED / DEACTIVATED / STOP_REQUESTED / EXECUTION_TIMEOUT / EXECUTION_UNRESOLVED / CRITICAL_FAULT / CONTEXT_CHANGED / CLOCK_FAULT。
- `AuthorityLost(binding, reason, revoke_generation, session_id, lease_id)`：保留原完整绑定、递增后的正代数；最后两项同时有值或同时 None，lease_id 从 repr 隐藏。它是后续停止 / 撤销用例的输入，不是停车或执行结果。
- `ExecutionHold(binding, hold_id, revision)`：由管理器创建的内部标记，hold_id 新鲜且 repr 隐藏，revision 正整数。只交给可信协调器，不放入公开快照。
- `AuthorityDenial`：FORBIDDEN / READ_ONLY / BUSY / LEASE_REQUIRED / STALE_LEASE / LEASE_EXPIRED / STALE_BINDING / INELIGIBLE / CONTEXT_CHANGED / CONFIRMATION_REQUIRED / NOT_ARMED / EXECUTION_UNRESOLVED / STALE_HOLD / CLOCK_UNHEALTHY。
- `PolicyFailure`：EVIDENCE_BINDING / EVIDENCE_CLOCK / EVIDENCE_FUTURE / EVIDENCE_EXPIRED / NOT_READY / CAPABILITY_UNAVAILABLE / IDENTITY_UNVERIFIED / MODE_NOT_PERMITTED / CALIBRATION_INVALID / LOCAL_PROTECTION_UNREADY / NATIVE_CONTROL_UNCONFIRMED / NOT_STOPPED / STANDSTILL_UNCONFIRMED。
- `AuthorityResult(snapshot, lease=None, denial=None, policy_failures=(), losses=())`：不可变具体值，序列复制为 tuple。accepted 只由 denial is None 计算；只有 acquire / renew 成功才带 ControlLease。policy_failures 用于 INELIGIBLE 的具体原因，losses 可以独立于成功 / 拒绝存在；拒绝不得丢掉失权事件。返回租约须与快照的绑定、持有者、期限及 revoke_generation 一致。

所有新聚合值检查字段类型和上述关联约束。拒绝结果不能携带 lease；INELIGIBLE 必须且仅能带非空 policy_failures，失败项不得重复，按枚举顺序排列。AuthorityLost 的 RELEASED / EXPIRED / SESSION_LOST / PERMISSION_REVOKED / DEACTIVATED / EXECUTION_TIMEOUT / CLOCK_FAULT 必须有原 owner / lease；其余保护原因允许无 owner。带 owner 的失权事件不能指向只读绑定。单个 result 的 losses 对每个 robot 最多一条；同绑定事件代数不得高于快照代数；跨绑定事件只允许 CLOCK_FAULT，保留所有受影响绑定的效果。

永久状态约束整个结果：任何 CLOCK_FAULT 事件都要求 snapshot.clock_faulted=True；同绑定 CONTEXT_CHANGED 事件要求 binding_retired=True，历史较低代数的事件也不例外。CLOCK_UNHEALTHY / CONTEXT_CHANGED 拒绝各自要求对应标志为 True，即使本次没有新事件。已有快照约束继而禁止 owner / ARMED。返回的 lease_id 不能同时出现在 losses 的原租约 ID 中；较早失权效果可以与不同的新 token 共存，旧 token 永不复活。

标识 / 文本 / 时刻 / 能力的子类不能成为调用句柄或自定义初始化进入公开值的通路；这不是恶意 Python 沙箱。

## 3. 纯策略

`policy_failures(binding, evidence, now, *, require_stopped: bool) -> tuple[PolicyFailure, ...]` 返回按第 2 节枚举顺序排列的全部失败，不保存状态。完整绑定必须相同；证据时钟匹配、observed_at <= now < valid_until；readiness=READY、pose_goal.available=True；身份、模式、标定、本地保护与原生独占五项均明确 True。require_stopped=True 时另要求 motion_state=STOPPED 和 standstill_verified=True，False / None 均不能替代。

显式激活使用 require_stopped=True；获取 / 续租 / 已有权限检查使用 False。持有者正常运动时 MOVING 或没有静止窗口，不单独取消已有 ARMED。SIM 的激活也要求同样明确的人工停车前提；REAL 标记本身不证明设备通过了真实准入。

## 4. 应用管理器：application/control_authority.py

`ControlAuthority(bindings, clock: MonotonicClock, *, max_lease_ns: int)`：绑定 list / tuple 在构造时复制并验证逻辑 / 可写设备唯一性；max_lease_ns 为显式正整数。clock.now 是现有快速非阻塞读取端口，构造时读一次，保存具体保护钟域与初始 tick。构造失败不产生管理器。单个应用 Lock 串行化所有检查及修改；临界区只有内存和该时钟读取，无网络、SDK、日志、用户回调或真实等待。

### 4.1 会话与范围

`register_session(authorization: SessionAuthorization) -> None`：可信认证方登记新 session_id；只接受当前已配置的 robot_ids，ID 在此管理器生命周期内不复用，撤销后也不能重新登记。重复 ID 抛 ValueError，错误类型抛 TypeError。没有注册或已撤销的会话、viewer、授权范围不符均 FORBIDDEN。请求只传 session_id，不能在 acquire / renew 等调用里换一个权限对象。

所有绑定操作接收完整 ControlBinding。未知 robot 抛 `UnknownControlBinding(KeyError)`；已知 robot 的 backend / epoch / read_only 不一致返回 STALE_BINDING，不改指或撤销当前绑定。mark_execution_unresolved 对已知 robot 的错误完整绑定抛 ValueError，未知 robot 仍抛 UnknownControlBinding；它不返回半有效标记。register_session 含未知 robot 时抛 UnknownControlBinding，整次登记不生效。类型 / 时长的编程错误在进入修改前抛 TypeError / ValueError。无自动注册、绑定切换、租约抢占、权限升级或自动激活。

### 4.2 操作签名

- `acquire(binding, session_id, evidence, *, duration_ns) -> AuthorityResult`
- `renew(binding, session_id, lease_id, evidence, *, duration_ns) -> AuthorityResult`
- `activate(binding, session_id, lease_id, evidence, *, confirmed: bool) -> AuthorityResult`
- `check(binding, session_id, lease_id, evidence) -> AuthorityResult`
- `release(binding, session_id, lease_id) -> AuthorityResult`
- `deactivate(binding, session_id, lease_id) -> AuthorityResult`
- `snapshot(binding) -> AuthorityResult`
- `poll_expired() -> tuple[AuthorityLost, ...]`
- `revoke(binding, reason: AuthorityLossReason, *, lease_id: str | None = None) -> AuthorityResult`
- `revoke_session(session_id, reason: AuthorityLossReason) -> tuple[AuthorityLost, ...]`
- `mark_execution_unresolved(binding) -> tuple[ExecutionHold, AuthorityResult]`
- `resolve_execution(hold: ExecutionHold) -> AuthorityResult`

### 4.3 租约、激活和上下文

每个配置绑定启动时 DISARMED、无租约、无执行标记、revoke_generation=0。acquire 需要已注册且未撤销的授权会话、可写绑定、未占用租约、无执行标记以及连续策略合格。duration_ns 为 1..max_lease_ns 的内置整数，expires_at=now+duration；生成新 lease_id，可用 uuid4 标准库，不把它当身份认证。即使同一持有者再次 acquire，也返回 BUSY，不偷偷续租。

renew / activate / check / release / deactivate 都必须匹配当前 lease_id、session_id 与完整绑定；没有租约为 LEASE_REQUIRED，有不同租约为 STALE_LEASE，错误持有者为 FORBIDDEN。旧租约不能修改同会话后来取得的新租约。renew 的期限为 max(原期限, now+duration)，不缩短，不累加旧期限来突破当前允许跨度，也不改变任何命令寿命。

activate 必须 confirmed=True、激活策略通过且 execution_blocked=False，才设 ARMED；重复合法 activate 可保持 ARMED。check 还要求已经 ARMED、无执行标记和连续策略合格，只返回当前检查结果，不占用任务槽或提供以后可用的执行票据。健康 MOVING 不因激活专用停车条件而失权，合法持有者可以续租；真正未结执行的标记会撤销原租约，不存在带执行锁而继续保留 ARMED 的状态。

绑定在第一次成功 acquire 时记住 capabilities，即使租约后来释放或过期也保留该上下文。此后无租约的授权 acquire，或精确匹配当前持有者的 renew / activate / check，发现证据能力快照（含 revision / configuration / mode / 原因）不同，均原子撤租、DISARMED 并将 binding_retired 永久置 True；返回 CONTEXT_CHANGED 拒绝和同名事件。显式 revoke(CONTEXT_CHANGED) 也退役该绑定。后续旧证据、新证据均不能在此绑定再授权，后续拒绝不重复发事件；旧上下文不能通过释放、重新申请或续租复活。

本轮对任何已采纳能力上下文变化采用保守退役。恢复需要可信生命周期组装使用新 backend_epoch 建立新的绑定 / 管理器，并先处置原绑定未结执行；本模块不实现换绑，也不提供 clear-retired。它不能跨不同管理器阻止调用方恶意复用 epoch。相同上下文下连续策略失效使匹配的当前持有者失权，理由 CRITICAL_FAULT；事实恢复后仍须重新申请并显式激活。仅激活专用的未停车 / 未确认条件失败返回拒绝，不把正常运动当关键故障。旧 session / lease / binding / 不属于该绑定的证据不能借拒绝路径撤销另一个有效持有者。

### 4.4 裁决顺序

所有返回值首先交给可信协调器，协调器消费完整 losses 后再投影客户端可见的拒绝和状态；不能向客户端泄露其他绑定的完整效果。以下顺序固定，保护效果不被业务拒绝遮蔽：

1. 在修改前验证编程输入类型 / 时长；在锁内确定配置的完整绑定。未知 robot 抛异常，已知但不同绑定返回 STALE_BINDING，此时不读钟、不改其他绑定。
2. 对合法绑定读取保护钟并处理目标租约到期；时钟故障一次撤销全部现存租约。此维护独立于会话权限，并保留产生的 effects。
3. 请求者会话未登记、已撤销或无该 robot 权限时返回 FORBIDDEN，附上第 2 步的 effects。否则按 CLOCK_UNHEALTHY、READ_ONLY、本次发现的 LEASE_EXPIRED、已退役 CONTEXT_CHANGED 顺序拒绝。snapshot 只应用时钟故障 / 本次到期拒绝，不检查会话、只读、退役或执行锁门；这些状态始终可在快照中查看。
4. acquire 在已有租约时返回 BUSY；其他租约操作依次检查当前租约存在、owner 匹配、lease_id 匹配，返回 LEASE_REQUIRED / FORBIDDEN / STALE_LEASE。被拒绝的竞争者或旧令牌不进入证据裁决。
5. 有证据的操作先拒绝不属于该绑定的证据，返回 INELIGIBLE 和连续纯策略（require_stopped=False）返回的全部失败，不撤权。其余证据先检查已采纳能力上下文变化，再检查连续策略。当前持有者的连续策略失败返回 INELIGIBLE + CRITICAL_FAULT 失权；未获租约的 acquire 只拒绝。过期 / 未来 / 错时钟证据同样不能维持当前授权。
6. 最后检查执行锁和操作专用条件。无租约且持有执行锁的 acquire 返回 EXECUTION_UNRESOLVED；activate 先要求 confirmed=True，再检查停车条件；check 要求 ARMED。未确认、尚未 ARMED 等条件不得提前掩盖第 5 步的真实连续失效。

有效 release / deactivate 不需要新的 ActivationEvidence；其余保护入口按下一节处理，不依赖读钟。

### 4.5 时间、异常与效果交接

acquire / renew / activate / check / release / deactivate / snapshot 先在合法绑定范围内读取保护钟，再处理该绑定到期；poll_expired 读取一次并按 robot_id 顺序处理全部到期者。now < expires_at 才有效，等值即失效。首次到期清租约、DISARMED、递增撤销代数，返回一个 EXPIRED 事件；该次已授权操作返回 LEASE_EXPIRED（snapshot 也可携带此拒绝），不在同次 acquire 里换发租约。无权限会话仍为 FORBIDDEN 并保留 EXPIRED 事件。下一次显式 acquire 仍需通过全部检查。后续查询不得重复发出同一次失权事件。

保护钟更换 clock_id、tick 回退、返回非法值或抛出 Exception 都触发 fail-closed：所有绑定撤租 / DISARMED，有现存租约的每个绑定按 ID 返回一个 CLOCK_FAULT 事件，事件不能被丢掉；保留所有执行标记，管理器 clock_faulted 永久锁定，后续新权限操作为 CLOCK_UNHEALTHY。不比较跨域裸 tick，也不自动恢复；需要新的运行时和绑定生命周期。初次构造的时钟错误直接抛出，因为尚无授权需要撤销。

revoke、revoke_session、mark_execution_unresolved、resolve_execution 属于可信协调器的保护 / 处置入口，不依赖成功读钟。revoke 作用于精确绑定，撤租 / DISARMED 并递增代数、返回原绑定事件，即使没有租约也可返回无 owner 的保护事件。允许的 reason 为 STOP_REQUESTED / EXECUTION_TIMEOUT / CRITICAL_FAULT / CONTEXT_CHANGED；EXECUTION_TIMEOUT 必须提供原 lease_id，其余可提供以限定旧工作。提供的 ID 不匹配当前租约时拒绝 STALE_LEASE，不能让迟到超时撤销新持有者。

revoke_session 只允许 SESSION_LOST / PERMISSION_REVOKED，先永久撤销该已登记 session，再按 ID 撤销其持有的租约并返回相应事件；没有租约则空 tuple。未知 session 抛 KeyError；重复撤销不重复产生事件。重新认证必须使用新的 session_id，旧请求不能靠尚存的授权对象重新申请。

有效 release 和 deactivate 均采用保守策略：撤租 / DISARMED、递增代数并返回对应事件。它们不依赖新鲜物理反馈。所有失权效果都保留原完整绑定、原 owner / lease，不修改原有不可变快照，不填 STOPPED，不自动清执行标记。效果由调用者同步接收，后续协调器须在同一序列采用后再安排 STOP；本轮没有隐藏队列或已送达保证。

### 4.6 未结执行标记

mark_execution_unresolved 表示真正的执行影响不确定 / 失去控制，由可信协调器显式输入，不从健康 MOVING、STOP 回执或业务终态推断。它在同一锁内生成新 hold_id 和递增 revision、设置执行锁、撤租 / DISARMED、递增 revoke_generation，返回 `(当前 ExecutionHold, 含 EXECUTION_UNRESOLVED 失权事件的 AuthorityResult)`。即使原来没有租约也保留无 owner 的保护事件。调用方不能先标记、再另行撤权，留下可见的中间 ARMED 状态。

当前 hold 是该绑定所有尚未解决原因的聚合修订。再次 mark 生成的新标记包含之前原因和新增原因；resolve 最新标记表示可信协调器已经处置全部这些原因，不能只凭最新一次事件结束便清锁。本模块不保存 attempt 原因集合或证明材料；这些由 DEV-M1-08 / 09 按原绑定记录和审计。普通健康执行占槽 / 可能执行锁不是本 API 的用途。

resolve_execution 只接受当前完整绑定、hold_id 和 revision 都匹配的标记；旧标记返回 STALE_HOLD，不能清更新的未知状态。清标记后仍无租约且 DISARMED，必须重新申请并显式激活；不清 binding_retired / clock_faulted、不改物理观测。它是可信协调器处置的输入，不能暴露成客户端布尔 reset；真实关闭证据与审计留后续用例，不能宣称一个 Python 标记证明已停车。

## 5. 固定样例和测试出口

人工 fixture：robot arm-fixture / arm-fixture-mirror，device mock-device-a；另一个设备 mock-device-b；backend mock-backend-a、SIM、fixture-epoch-a。保护钟 control-clock，初值 0 ns；证据 observed_at=0、valid_until=1000 ns；max_lease_ns=100 ns，首次 duration=10 ns。会话 operator-a / operator-b、viewer；只有前两者显式获 arm-fixture 权限。能力由五项 True 的纯组合构造 revision=1，configuration=fixture-config-1、mode=automatic。所有肯定前提明确给出，缺失样本为 None / UNKNOWN。

| 切片 / marker | 必须证据 |
| --- | --- |
| T01/leases · t01_leases | 配置时 device 可写唯一、只读镜像拒绝、不同设备独立；两个线程在 Barrier 后争用恰好一个成功；会话授权、初始 DISARMED、续租保持身份、旧 token 拒绝 |
| T07/authority-loss · t07_authority_loss | 有效 release / deactivate；断线 / 撤权旧会话不能重用；过期拒绝同时带事件且只发一次，包括 FORBIDDEN；原绑定效果、迟到旧租约保护事件不影响新租约；未结标记原子撤权 / 旧解除标记 / 聚合处置；解除后旧租约不能恢复 |
| T30/activation · t30_activation | READY / 租约 / ARMED / motion 分离；逐项缺失或 False 的前提拒绝；显式确认；错绑定 / 陈旧 / 未来证据；健康 MOVING 续租保留 ARMED；能力上下文退役后旧证据不能重获租约，包括已释放 / 过期后；未确认 / DISARMED 不遮蔽连续失效；只读或未结标记不可激活 |
| T42/lease-clock · t42_lease_clock | duration 1..max、bool / 非整数拒绝；临界前 / 等值 / 之后；独立源钟不延长保护钟期限；时钟跨域 / 回退 / 异常使所有旧权限失效但保护入口可用；重复读不重复发效果 |

线程测试使用 Barrier / Event 和有界 join，不靠睡眠概率循环；renew 后 release 可都成功，release 后 renew 必须拒绝，两个顺序最终都没有租约。新测试先收集并显式断言缺少 API；每次 RED 保存独立日志。保留原 303 项、安装 / 依赖探测和 README 可运行示例。

I02 本轮只完成 DEV-M1-05 的 UNIT / MOCK 切片；实际 STOP、状态投影、任务槽和最终下发竞态仍由后续工作包验证，G-I02 和产品验收保持 PENDING。

## 6. 可运行示例

先按 [README](../../README.md#快速上手) 安装包。将以下代码保存为 `authority_example.py`，运行 `uv run --no-sync python -I authority_example.py`。全部数据是人工 fixture；这里只展示应用许可的转换，不连接只读 mock 或实际设备。10 ns 租期与 1000 ns 证据窗口用于精确演示边界，不是部署参数。

```python
from framework.adapters.clocks import ManualMonotonicClock
from framework.application.control_authority import ControlAuthority
from framework.domain.capabilities import CapabilityInputs, revise_capabilities
from framework.domain.control import (
    ActivationEvidence, ControlBinding, Readiness, SessionAuthorization,
)
from framework.domain.discovery import BackendIdentity, BackendKind, MotionState
from framework.domain.time import MonotonicInstant
from framework.domain.values import DeviceId, RobotId

clock = ManualMonotonicClock(clock_id="control-clock")
binding = ControlBinding(
    RobotId("arm-fixture"),
    BackendIdentity(
        DeviceId("mock-device-a"), "mock-backend-a", BackendKind.SIM, "fixture-epoch-a",
    ),
    read_only=False,
)
capabilities = revise_capabilities(CapabilityInputs(
    planning=True, model=True, frames=True, policy=True, execution=True,
    configuration_revision="fixture-config-1", mode="automatic",
))
evidence = ActivationEvidence(
    binding=binding, capabilities=capabilities,
    readiness=Readiness.READY, motion_state=MotionState.STOPPED,
    observed_at=clock.now(), valid_until=MonotonicInstant("control-clock", 1000),
    identity_verified=True, mode_permitted=True, calibration_valid=True,
    local_protection_ready=True, native_control_exclusive=True, standstill_verified=True,
)
authority = ControlAuthority([binding], clock, max_lease_ns=100)
authority.register_session(SessionAuthorization("operator-a", [binding.robot_id]))

granted = authority.acquire(binding, "operator-a", evidence, duration_ns=10)
assert granted.accepted and granted.lease is not None
print(granted.snapshot.arming_state.name)  # DISARMED

activated = authority.activate(
    binding, "operator-a", granted.lease.lease_id, evidence, confirmed=True,
)
assert activated.accepted
print(activated.snapshot.arming_state.name)  # ARMED

clock.advance_ns(10)
expired = authority.check(binding, "operator-a", granted.lease.lease_id, evidence)
assert expired.denial is not None
print(expired.denial.name, expired.losses[0].reason.name)  # LEASE_EXPIRED EXPIRED
print(expired.snapshot.arming_state.name)  # DISARMED
```

示例中的最终拒绝同时带有一个失权事件。实际协调器须先采纳这个效果，再安排原绑定的停止 / 对账；读取拒绝本身没有完成物理停止。重复查询不会重新发出同一次 EXPIRED 事件。
