# Python 工程与时钟基线

- 日期：2026-11-20
- 工作包：DEV-M1-02；I01 的最小工程切片
- 当前边界：已验证最小 Python 包、时钟领域值与时钟端口，实际记录见 [AR-0005](../project/records/AR-0005-python-foundation-recheck.md)
- 关联：[运行时详细设计](05-runtime-coordination.md)、[项目入口](../project/README.md)、[仓库运行说明](../../README.md)

## 1. 版本决策

继续采用既有 Python 3.12 候选：它与首条 Ubuntu 24.04 / ROS 2 Jazzy 候选环境的 Python minor 对齐，也能满足普通 dataclass / Protocol 的内核设计。不因系统默认 3.13.1 改为 3.13。本轮实际选择已安装的 CPython 3.12.11 作为精确复现解释器，[.python-version](../../.python-version)固定 patch，[包元数据](../../pyproject.toml)限制 >=3.12,<3.13；这不声称其他 3.12 patch 已测。

3.12.11 是本轮本地复现版本，不是最新安全补丁或部署批准。后续进入联网服务 / SIM / REAL 部署前必须审查维护补丁并回归；升级 patch 同样记录实际版本、修改版本文件、重建虚拟环境及重复 T26，不静默替换。无需为本轮安装解释器或修改全局 Python。

| 对象 | 固定值 / 权威位置 | 边界 |
| --- | --- | --- |
| CPython / 环境工具 | 3.12.11 / uv 0.10.9；pyproject 约束 uv 版本 | 在 Windows 11 上完成项目环境安装与独立消费者检查 |
| 运行依赖 | dependencies=[] | 只用标准库；不安装 ROS / 引擎 / SDK、HTTP、Pydantic 或 ORM |
| 构建后端 | setuptools==80.9.0、wheel==0.45.1 | 固定在 build-system.requires；构建隔离仍需这些工具可用，不能靠默认最新版 |
| 开发依赖 | pytest==8.4.2 | dependency-groups.dev；安装仅在项目虚拟环境内 |
| 完整开发解析 | [uv.lock](../../uv.lock) | 7 条分发记录（含本地工程），携带索引版本 / 工件哈希；元数据锁定不等于代码已下载、安装或验证 |

本次解析的 pytest 传递依赖为 colorama 0.4.6（Windows）、iniconfig 2.3.1、packaging 26.3、pluggy 1.7.0、pygments 2.21.0；具体解析以锁文件为准，不在多处手工修改版本。构建工具的版本另由 build-system.requires 固定，不能把 uv.lock 当作已经包含全部构建工具的安装清单。

## 2. 最小布局与依赖方向

分发名为 bot3d-kernel，导入名为 framework，沿用架构的 src/framework 建议。只创建本轮实际使用的包，不建立网关、Registry、Planner、Backend、Journal、数据库或 bootstrap 空壳。

- [领域时间值](../../src/framework/domain/time.py)：冻结的 MonotonicInstant 与跨时钟错误；只依赖 dataclasses。
- [应用时钟端口](../../src/framework/application/ports.py)：MonotonicClock Protocol，只有 now()，返回普通领域值；不携带 HTTP DTO、SDK / ROS 对象。
- [时钟适配器](../../src/framework/adapters/clocks.py)：SystemMonotonicClock 与明确注入的 ManualMonotonicClock；不启动服务或设备连接。
- [单元测试](../../tests/)：包安装、依赖边界、端口与时钟三个 T26 切片；fixture 按函数创建，无全局共享时钟。
- [依赖检查器](../../tools/check_import_boundaries.py)：只读 AST 检查，核心为 root / domain / application；适配层可向内，不被内核反向导入。
- [独立 wheel 消费者检查](../../tools/check_wheel_install.py)：仓库外临时空 venv、无 pip / pytest、离线安装本地 wheel，再用 -I 导入与探测；未构建时不能运行成功。

核心允许标准库与向内的 framework 导入；显式拒绝 HTTP / socket / SQLite 等边界依赖和第三方库。AST 同时检查 TYPE_CHECKING 分支、相对导入、已知动态 import / eval / exec，运行测试另用独立解释器拦截传输依赖和服务启动。静态检查不是恶意 Python 沙盒，不能证明不存在所有反射或动态绕过；测试文件中的坏样例只解析、不导入。

## 3. 时钟语义

- MonotonicInstant(clock_id, tick_ns) 是不可变普通领域值；tick_ns 为内部精确整数纳秒，不是公开命令时间字段，也不是设备 / 仿真时间映射。
- clock_id 必须是非空字符串；tick_ns 必须为非负 int，bool、浮点、NaN / Infinity、负数不能混入。没有实现通用 robot / frame / tool 标识或目标数值类型，留给 DEV-M1-03。
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

`--no-editable` 选择非编辑 wheel 安装，pytest 检查实际导入位置和 direct_url。修改源码后用上面的 sync 命令刷新并重装本地分发，再运行测试。复制模式解决了本轮 Windows 缓存安装时的文件访问错误，复验过程见 [AR-0005](../project/records/AR-0005-python-foundation-recheck.md)。

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

三个 T26 切片的结果摘要见 [AR-0005](../project/records/AR-0005-python-foundation-recheck.md)。DEV-M1-03 的基础类型和 T28 切片列于 [I01](../project/iterations/I01-M1-foundation.md)。

设计取舍：只实现必要的时钟端口，不凭尚未实现的目标 / 命令类型预造 Planner / Backend 签名；人工钟显式位于适配层、不进领域；无运行第三方依赖；pytest 仅为开发依赖。独立复核和产品验收仍待指定。本轮不增加公共命令状态，不降低已有 AC。
