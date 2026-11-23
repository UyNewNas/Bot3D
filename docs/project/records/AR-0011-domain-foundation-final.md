# AR-0011：基础类型与项目主页最终复验

| 日期 | 范围 | 环境 | 技术结果 | 产品验收 |
| --- | --- | --- | --- | --- |
| 2026-11-23 | I01 · DEV-M1-03 · T28、工程回归与 README | Linux x86_64、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | UNIT / 安装 / DOC 与独立代码复核 PASS | PENDING |

## 版本与修正范围

基线提交 `319fed05a2d319bc6dc1865963670585fdc27cf9` 加本轮工作树。保留 [AR-0007](AR-0007-foundation-boundary-recheck.md) 的 DEV-M1-02 工程修正；交付 [DEV-M1-03 基础类型](../../design/07-domain-types-and-geometry.md)和项目主页。实现前失败与数值复核过程分别保留在 [AR-0008](AR-0008-domain-foundation-start.md)、[AR-0009](AR-0009-domain-foundation-recheck.md)和 [AR-0010](AR-0010-domain-foundation-final.md)。

执行角色为开发助手，代码与数学由独立助手复核，现实验收角色未指定。

交付 values、geometry、targets 三个领域模块和四个 T28 测试文件。标识、向量、四元数、带帧标签的刚体变换与带工具目标均不可变，SI 换算显式进行，缺失或非法输入明确拒绝。DEF-0004 修正采用普通范围浮点路径与极端范围的 Fraction 精确旋转；公共 API、xyzw / T_A_B 方向和验收容差均未改变，运行第三方依赖仍为零。

README 重写为项目主页，围绕项目用途、技术架构、实现方式、快速上手、路线和文档导航展开；可运行示例只使用本轮已实现 API。ROS 2 / MoveIt 2 / Gazebo、网关和 XR 按规划范围说明。

## 实际执行

最大有限值反例先在旧安装包上运行，结果为 1 failed，退出 1，输出保留于 AR-0010；修正后非编辑安装同步退出 0，再执行以下验证。

| 切片 / 检查 | 状态 | 实际证据 |
| --- | --- | --- |
| T28/values | PASS | 45 passed：标识、作用域、SI、有限数 / 维度、目标必填类型、不可变与错帧转换 |
| T28/basis | PASS | 18 passed：独立基准点 / 方向轴、T_A_B、逆变换、非交换组合与错帧拒绝 |
| T28/quaternion | PASS | 25 passed：xyzw、符号等价、组合顺序、范数闭区间、非法值、三个有限结果回归与真正溢出 |
| T26/package | PASS | 4 passed；新模块进入非编辑安装包，仓库外隔离导入 |
| T26/imports | PASS | 48 passed；核心依赖扫描 8 个模块，检查器自测 32 项 |
| T26/ports-clock | PASS | 30 passed；原时钟 API 与行为回归 |
| 全量 pytest | PASS | 170 passed，退出 0；既有 82 项与本轮 88 项 T28 |
| 依赖锁 | PASS | uv lock --check --offline 退出 0，uv.lock 未改动 |
| sdist→wheel 与空消费者 | PASS | 构建退出 0；仓库外空环境离线安装，仅有 bot3d-kernel，目标 / 变换与时钟探测均通过 |
| README 示例 | PASS | 仓库外使用已安装包与隔离解释器，输出 cell/world: (1.00, 2.25, 3.00) m |
| 数值修正独立复核 | PASS | 三个有限结果按独立几何预期通过；真正越界及略超最大值却会被 float 舍入回最大值的结果均拒绝；普通微小旋转保留，已安装源码与工作树一致 |
| DOC 自测与运行时设计 | PASS | 文档自测 43 项；运行时模型自测 25 项、设计场景 44 项，其中 T31 为 26、T34 为 18，仅算 DOC |
| 文档汇总检查 | PASS | 29 篇 Markdown、73 个表、194 个本地链接；编号 / 追踪、58 条开发依赖和台账状态一致 |
| 最终整体差异复核 | PASS | 独立复跑 170 项测试、文档检查与仓库外 README 示例；核对 wheel 中领域模块与待提交源码逐字节一致、包元数据包含当前主页且运行依赖为零；无阻断问题 |

## 复现命令

在仓库根目录使用指定的 CPython 3.12.11 / uv 0.10.9。源码修改后先重装非编辑包，测试与消费者不注入源码路径。

```bash
uv sync --locked --no-editable --reinstall-package bot3d-kernel --link-mode copy --default-index https://pypi.org/simple
uv lock --check --offline --default-index https://pypi.org/simple
uv run --no-sync python -I -m pytest
uv run --no-sync python -I -m pytest -m t26_package
uv run --no-sync python -I -m pytest -m t26_imports
uv run --no-sync python -I -m pytest -m t26_ports_clock
uv run --no-sync python -I -m pytest -m t28_values
uv run --no-sync python -I -m pytest -m t28_basis
uv run --no-sync python -I -m pytest -m t28_quaternion
uv run --no-sync python -I tools/check_import_boundaries.py --self-test
uv run --no-sync python -I tools/check_import_boundaries.py
uv build --no-sources --link-mode copy --default-index https://pypi.org/simple
uv run --no-sync python -I tools/check_wheel_install.py
uv run --no-sync python -I tools/check_runtime_design.py --self-test
uv run --no-sync python -I tools/check_runtime_design.py
uv run --no-sync python -I tools/check_project_docs.py --self-test
uv run --no-sync python -I tools/check_project_docs.py
git diff --check
```

上述运行记录与相关输入文件校验清单按本 AR 编号留存。历史失败和前两次数值实现的通过 / 失败范围分别保留，不用最终通过覆盖中间发现。

## 验收边界

本轮为类型与纯数学的 UNIT 证据。AC-002 的绑定、AC-004 的配置 / 场景策略、AC-016 的变换来源 / 标定有效性与 XR 复验继续由后续任务实现。I01 仍需 T29 / T46 四个切片，产品验收保持 PENDING。

DEV-M1-03 完成类型 / 数学交付，DEF-0003 与 DEF-0004 经实现、回归和独立数值复核关闭。REQ-002 / REQ-004 / REQ-016 保持 DEVELOPING，不提前 ACCEPTED；DEV-M1-04 为下一项 TODO。I01 累计六个 UNIT 切片通过，保持 ACTIVE，G-I01 / G-M1 不关闭。

本次为 Linux 复验，未重跑 Windows，未进行 SIM、XR 或 REAL 联调；原 Windows 记录仍保留在 AR-0005。数学值本身不携带标定来源 / 时间有效性，也不授予执行资格。普通计算采用 binary64，变换的每一步仍须产生可表示的有限值。
