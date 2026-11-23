# Python 工程与时钟基线

- 日期：2026-11-20
- 工作包：DEV-M1-02；I01 的最小工程切片
- 当前边界：已验证 Python 包、时钟、基础类型、只读 Registry 与控制权；最新十四个切片及独立安装复验见 [AR-0020](../project/records/AR-0020-control-authority-final.md)，依赖检查补漏见 [AR-0007](../project/records/AR-0007-foundation-boundary-recheck.md)，原 Windows 基线见 [AR-0005](../project/records/AR-0005-python-foundation-recheck.md)
- 关联：[运行时详细设计](05-runtime-coordination.md)、[基础类型与坐标数学](07-domain-types-and-geometry.md)、[项目入口](../project/README.md)、[仓库运行说明](../../README.md)

## 1. 版本决策

继续采用既有 Python 3.12 候选：它与首条 Ubuntu 24.04 / ROS 2 Jazzy 候选环境的 Python minor 对齐，也能满足普通 dataclass / Protocol 的内核设计。不因系统默认 3.13.1 改为 3.13。原 Windows 基线选择已有的 CPython 3.12.11，Linux 补充复验使用相同版本；[.python-version](../../.python-version)固定 patch，[包元数据](../../pyproject.toml)限制 >=3.12,<3.13。其他 3.12 patch 未完成三个 T26 切片的精确复验。

3.12.11 是本地复现版本，不是最新安全补丁或部署批准。后续进入联网服务 / SIM / REAL 部署前必须审查维护补丁并回归；升级 patch 同样记录实际版本、修改版本文件、重建虚拟环境及重复 T26，不静默替换。原 Windows 环境无需另装解释器；Linux 复验在任务隔离目录准备精确版本，没有修改系统解释器或项目版本约束。

| 对象 | 固定值 / 权威位置 | 边界 |
| --- | --- | --- |
| CPython / 环境工具 | 3.12.11 / uv 0.10.9；pyproject 约束 uv 版本 | Windows 11 基线与 Linux 补充复验均完成项目环境安装与独立消费者检查；各次证据分别保留 |
| 运行依赖 | dependencies=[] | 只用标准库；不安装 ROS / 引擎 / SDK、HTTP、Pydantic 或 ORM |
| 构建后端 | setuptools==80.9.0、wheel==0.45.1 | 固定在 build-system.requires；构建隔离仍需这些工具可用，不能靠默认最新版 |
| 开发依赖 | pytest==8.4.2 | dependency-groups.dev；安装仅在项目虚拟环境内 |
| 完整开发解析 | [uv.lock](../../uv.lock) | 7 条分发记录（含本地工程），携带索引版本 / 工件哈希；元数据锁定不等于代码已下载、安装或验证 |

本次解析的 pytest 传递依赖为 colorama 0.4.6（Windows）、iniconfig 2.3.1、packaging 26.3、pluggy 1.7.0、pygments 2.21.0；具体解析以锁文件为准，不在多处手工修改版本。构建工具的版本另由 build-system.requires 固定，不能把 uv.lock 当作已经包含全部构建工具的安装清单。

## 2. 最小布局与依赖方向

分发名为 bot3d-kernel，导入名为 framework，沿用架构的 src/framework 建议。只创建实际使用的模块；Registry、只读端口与独立控制权管理器已有实现，网关、规划 / 执行端口、Journal、数据库和 bootstrap 按后续任务建立。

- [领域时间值](../../src/framework/domain/time.py)：冻结的 MonotonicInstant 与跨时钟错误；只依赖 dataclasses。
- [标识与 SI 值](../../src/framework/domain/values.py)、[坐标数学](../../src/framework/domain/geometry.py)、[位姿目标](../../src/framework/domain/targets.py)：DEV-M1-03 的不可变值与纯数学；具体 API、方向和数值边界见[专题设计](07-domain-types-and-geometry.md)。
- [能力组合](../../src/framework/domain/capabilities.py)与[只读数据](../../src/framework/domain/discovery.py)：DEV-M1-04 的能力版本、原因、身份和最小观测切片，接口见[专题设计](08-readonly-registry-and-capabilities.md)。
- [应用读取端口](../../src/framework/application/ports.py)：MonotonicClock 只有 now()，ReadOnlyBackend 只有 describe() / read_state()；都返回普通领域值，不携带 HTTP DTO、SDK / ROS 对象。
- [只读 Registry](../../src/framework/application/registry.py)：同步内存注册、发现、身份一致性检查和每绑定能力版本；不暴露控制句柄。
- [控制权领域值](../../src/framework/domain/control.py)与[控制权管理器](../../src/framework/application/control_authority.py)：会话授权登记、租约、显式激活、失权事件、上下文退役与聚合未结执行标记，接口见[专题设计](09-control-authority-and-activation.md)。应用层用短 Lock 串行化许可转换；不调用执行或 STOP。
- [时钟适配器](../../src/framework/adapters/clocks.py)：SystemMonotonicClock 与明确注入的 ManualMonotonicClock；不启动服务或设备连接。
- [只读 SIM mock](../../src/framework/adapters/mock_robot.py)：固定身份与观测样例，执行前提固定为 False，无外部连接或控制入口。
- [单元测试](../../tests/)：T26 三个工程切片、T28 三个类型 / 数学切片、T29 / T46 四个能力 / 只读切片，以及 T01 / T07 / T30 / T42 四个控制权切片；fixture 按函数创建，无全局共享时钟。
- [依赖检查器](../../tools/check_import_boundaries.py)：只读 AST 检查，核心为 root / domain / application；适配层可向内，不被内核反向导入。
- [独立 wheel 消费者检查](../../tools/check_wheel_install.py)：仓库外临时空 venv、无 pip / pytest、离线安装本地 wheel，再用 -I 导入与探测；未构建时不能运行成功。

核心允许符合分层规则的标准库与向内的 framework 导入；显式拒绝 HTTP / socket / SQLite 等边界依赖和第三方库，标准库中的 xmlrpc / wsgiref 也属于 HTTP 边界。按[运行时设计第 4 节](05-runtime-coordination.md)，纯领域另外拒绝 threading、_thread、asyncio、concurrent 和 multiprocessing；该限制不禁止应用协调层使用并发机制。

AST 同时检查 TYPE_CHECKING 分支、函数内和相对导入、已知动态 import / eval / exec，运行测试另用独立解释器拦截传输依赖和服务启动。静态检查不是恶意 Python 沙盒，不能证明不存在所有反射、标准库间接路径或动态绕过；测试文件中的坏样例只解析、不导入。此次补漏的失败证据见 [AR-0006](../project/records/AR-0006-foundation-boundary-review.md)。

## 3. 时钟语义

- MonotonicInstant(clock_id, tick_ns) 是不可变普通领域值；tick_ns 为内部精确整数纳秒，不是公开命令时间字段，也不是设备 / 仿真时间映射。
- clock_id 必须是非空字符串；tick_ns 必须为非负 int，bool、浮点、NaN / Infinity、负数不能混入。robot / device / frame / tool 标识和目标数值使用独立的[基础类型规范](07-domain-types-and-geometry.md)，不复用 clock_id。
- elapsed_ns_since 只允许同 clock_id 且后读数不早于前读数；跨时钟域、逆序或非领域对象显式报错，不猜测偏移、不返回默认零。相等时已知经过时间为零，不等于填补未知反馈。
- SystemMonotonicClock 用标准库 monotonic_ns，构造时生成本次对象的 clock_id；组装入口应构造一个并共享，不在每条命令上重建。原点不承诺跨进程 / 跨重启可复用，不读 wall clock，不据此声称硬实时。
- ManualMonotonicClock 只由 advance_ns 显式推进，可推进零、不能回退；旧快照保持不变。默认 0 是明确人工 fixture 初始值，不是缺失设备反馈。该对象只用于单拥有者的测试 / mock，不提供线程安全或真实保护钟保证。
- 两个人工钟可以分别代表保护钟与独立输入源的测试前提，推进一方不改变另一方；这没有实现源钟映射、仿真 reset / 回退或同步协议。相关 T04 / T16 / T42 仍须后续实现与独立验证。

## 4. 安装、构建和运行

在仓库根目录运行以下命令。

```bash
uv sync --locked --no-editable --reinstall-package bot3d-kernel --link-mode copy --default-index https://pypi.org/simple
uv run --no-sync python -I -m pytest
uv run --no-sync python -I -m pytest -m t26_package
uv run --no-sync python -I -m pytest -m t26_imports
uv run --no-sync python -I -m pytest -m t26_ports_clock
uv build --no-sources --link-mode copy --default-index https://pypi.org/simple
uv run --no-sync python -I tools/check_wheel_install.py
```

`--no-editable` 选择非编辑 wheel 安装，pytest 检查实际导入位置和 direct_url。修改源码后用上面的 sync 命令刷新并重装本地分发，再运行测试。复制模式解决了原 Windows 基线中缓存安装时的文件访问错误，复验过程见 [AR-0005](../project/records/AR-0005-python-foundation-recheck.md)。

`check_wheel_install.py` 在仓库外创建一次性空环境，禁止从索引取包，使用 --offline --no-index --no-deps 安装本地 wheel，并要求环境中只有本工程分发。它是安装探测脚本，不是设备启动器；只能清理其自己创建的临时目录。dist 有多个工程 wheel 时必须显式传路径，不默选旧产物。

解释器与开发、构建依赖均已缓存时可给 sync 和 build 加 `--offline`。首次尝试遇到的缓存缺失保留在 [AR-0004](../project/records/AR-0004-python-foundation.md)。.venv、build、dist、缓存和 egg-info 由 Git 忽略。

不依赖开发包安装的检查可以独立运行：

```bash
uv run --offline --no-sync python -I tools/check_import_boundaries.py --self-test
uv run --offline --no-sync python -I tools/check_import_boundaries.py
uv run --offline --no-sync python -I tools/check_project_docs.py --self-test
uv run --offline --no-sync python -I tools/check_project_docs.py
uv run --offline --no-sync python -I tools/check_runtime_design.py --self-test
uv run --offline --no-sync python -I tools/check_runtime_design.py
```

## 5. 测试切片与未完成项

| 切片 | 已编写的断言 / 所需证据 | 不能替代的检查 |
| --- | --- | --- |
| T26/package | 精确解释器、元数据、零运行依赖、非源码 / 非编辑位置、仓库外隔离导入；另在真正空消费者环境离线安装 wheel | 没有 wheel / 没有安装时不能靠语法检查算 PASS |
| T26/imports | 核心源码 AST、相对 / 间接导入和坏样例、独立进程实际导入时拒绝传输栈 / 服务启动 | AST 静态通过不等于运行导入测试已运行 |
| T26/ports-clock | 端口返回普通类型、非法时钟值、不可变快照、显式推进 / 回退拒绝、时钟域隔离、系统单调读数 | 不证明租约、命令期限、静止窗口或真实设备保护 |
| T28/values | 独立标识、作用域 frame、必填工具目标、不可变数组拷贝、SI 换算、有限数与维度 | 不证明绑定、工具配置、工作空间或碰撞策略 |
| T28/basis | T_A_B 的点 / 方向 / 姿态、逆变换、非交换变换组合和错帧拒绝 | 不证明变换来源、时间、标定或有效性 |
| T28/quaternion | xyzw、q / -q 等价、先 other 后 self 的组合、范数闭区间及有限结果 / 溢出 | 不证明 XR 基变换、跟踪或重定位 |
| T29/compose | 五前提组合、全部不可用原因与具体值类型 | 人工全可用输入不授予 mock 执行能力 |
| T29/revision | 初值、等价读、原因 / 配置 / 模式变化、A→B→A 与不可变快照 | 不推断后端未声明的配置变化 |
| T46/discovery | 注册 / 描述 / 状态、完整身份漂移拒绝、镜像独立版本、重复与失败不覆盖 | 不证明运行时 epoch 轮转、设备核验或持久化 |
| T46/readonly | mock 与 Registry 都无执行能力、子类边界、未知 / 空观测、零控制调用 | 不证明真实停车或完整 StateProjection |
| T01/leases | 设备可写唯一、会话 / 租约身份、线程竞争、续期和旧令牌拒绝 | 不提供跨进程锁或设备 fencing |
| T07/authority-loss | 会话撤销、失权效果、迟到请求、聚合执行锁与处置后重新获权 | 不执行物理停止，不证明全部执行原因已关闭 |
| T30/activation | 显式确认、连续 / 停车前提分离、健康运动续租、上下文退役 | 不提供真实认证或反馈资格判定 |
| T42/lease-clock | 半开到期、来源钟隔离、故障时全部撤权与保护入口 | 命令期限 / 执行预算留后续用例 |

I01 十个切片保留回归，I02 新增四个控制权切片；全量与工程结果见 [AR-0020](../project/records/AR-0020-control-authority-final.md)。基础类型、只读 Registry 和控制权分别见[类型设计](07-domain-types-and-geometry.md)、[能力 / 发现设计](08-readonly-registry-and-capabilities.md)与[控制权设计](09-control-authority-and-activation.md)；产品验收仍为 PENDING。

设计取舍：时钟端口只保留必要操作，不为未来命令类型预造 Planner / Backend 签名；人工钟显式位于适配层、不进领域；无运行第三方依赖；pytest 仅为开发依赖。各次独立代码复核见对应 AR，产品验收角色仍待指定。本轮不增加公共命令状态，不降低已有 AC。
