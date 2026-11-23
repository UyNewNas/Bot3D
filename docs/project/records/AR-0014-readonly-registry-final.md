# AR-0014：只读 Registry 与能力组合最终复验

| 日期 | 范围 | 环境 | 技术结果 | 产品验收 |
| --- | --- | --- | --- | --- |
| 2026-11-23 | I01 · DEV-M1-04 · T29 / T46、工程回归与 README | Linux x86_64、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | UNIT / MOCK、安装、DOC 与子类复核 PASS；批量发现复核 FAIL | PENDING |

## 版本与范围

基线为 `b084218d82caa20e13d5e2ef3055f69046785547` 加本轮修正工作树。实现前缺口见 [AR-0012](AR-0012-readonly-registry-start.md)，首次实现与子类边界失败见 [AR-0013](AR-0013-readonly-registry-review.md)。具体接口与约束见[只读 Registry 设计](../../design/08-readonly-registry-and-capabilities.md)。执行角色为开发助手，独立助手参与契约、实现及修正复核，现实验收角色未指定。

本轮交付 capabilities / discovery 领域值、纯能力组合与版本、只读后端 Protocol、RobotRegistry 和 SIM mock。逻辑机器人与设备身份分开，描述 / 状态读取核对完整后端身份，多个只读镜像分别维护能力版本。缺失观测保持 None / UNKNOWN，公开能力固定缺少执行支持。

DEF-0006 的修正要求具体数据类及其嵌套值，拒绝可重写初始化或附带调用句柄的子类；保留既有 RobotId / DeviceId 构造行为。静态类型约束不宣称是恶意 Python 的安全沙箱。README 在项目介绍、架构、实现方式和快速上手的结构下增加只读发现示例，并同步当前模块与路线。

## 实际执行

| 切片 / 检查 | 状态 | 实际证据 |
| --- | --- | --- |
| T29/compose | PASS | 35 passed；五前提、完整原因顺序、严格输入和子类拒绝 |
| T29/revision | PASS | 17 passed；首次版本、等价读取、配置 / 模式 / 原因变化、A→B→A、旧快照不变 |
| T46/discovery | PASS | 35 passed；注册 / 排序、独立身份与镜像版本、重复拒绝、身份漂移、失败不发布版本 |
| T46/readonly | PASS | 45 passed；双层执行隔离、具体数据边界、不可变观测、缺失未知与零控制调用 |
| T26/package | PASS | 4 passed；安装位置、元数据及仓库外隔离导入 |
| T26/imports | PASS | 48 passed；实际导入隔离及边界负例 |
| T26/ports-clock | PASS | 30 passed；原时钟端口和类型行为保持 |
| T28/values / basis / quaternion | PASS | 分别 45 / 18 / 25 passed；原 88 项类型 / 数学回归 |
| 全量 pytest | PASS | 302 passed，退出 0；原有 170 项加本轮 132 项 |
| 子类回归与针对性复核 | PASS | 26 项先失败、后通过；独立复核判定原 finding 已解决，修正差异无新增问题 |
| 安装 / 依赖锁 | PASS | 固定版本离线非编辑安装及 uv lock --check 退出 0；uv.lock 无修改，运行第三方依赖为零 |
| 依赖边界 | PASS | 11 个核心模块扫描通过；同轮未改变的检查器自测 32 项通过，原始输出保留在 AR-0013 |
| sdist→wheel 与空消费者 | PASS | 离线构建通过；仓库外空环境仅安装 bot3d-kernel，时间、几何与实际只读 Registry 探测通过 |
| 工件一致性 | PASS | wheel 中全部 framework Python 模块逐字节等于源码；元数据 README 等于当前主页，无 Requires-Dist |
| README 两个示例 | PASS | 仓库外隔离解释器输出 cell/world: (1.00, 2.25, 3.00) m；只读示例输出 mock-device-a / False / UNKNOWN；无 stderr |
| DOC 工具自测与运行时设计 | PASS | 同轮未改变的工具：文档自测 43、运行时自测 25、设计场景 44（T31=26、T34=18）；原始输出保留在 AR-0013，仅算 DOC |
| DOC 汇总与差异检查 | PASS | 34 篇 Markdown、80 个表、228 个本地链接、3 个严格 JSON 块；编号 / 追踪、58 条开发依赖与台账一致；git diff --check 退出 0 |
| 整分支复核 | FAIL | 候选 63d4637 的独立探测退出 1：后续绑定读取失败后，前面绑定未发布的版本仍被提交，见 DEF-0007 |

复验输出独立保存在本地 `AR-0014/task-1-fix-1-*` 与 `AR-0014/final-*`，前两次记录和失败日志保持原样。输入校验清单按本 AR 编号留存，完整代码版本由包含此记录的提交定位。

## 复现命令

在仓库根目录使用固定的 CPython 3.12.11 / uv 0.10.9。已缓存解释器与依赖时可离线运行；首次准备的安装命令见[工程基线](../../design/06-python-foundation.md)。

```bash
uv sync --locked --no-editable --reinstall-package bot3d-kernel --offline --link-mode copy --default-index https://pypi.org/simple
uv lock --check --offline --default-index https://pypi.org/simple
uv run --no-sync python -I -m pytest
uv run --no-sync python -I -m pytest -m t29_compose
uv run --no-sync python -I -m pytest -m t29_revision
uv run --no-sync python -I -m pytest -m t46_discovery
uv run --no-sync python -I -m pytest -m t46_readonly
uv run --no-sync python -I -m pytest -m t26_package
uv run --no-sync python -I -m pytest -m t26_imports
uv run --no-sync python -I -m pytest -m t26_ports_clock
uv run --no-sync python -I -m pytest -m t28_values
uv run --no-sync python -I -m pytest -m t28_basis
uv run --no-sync python -I -m pytest -m t28_quaternion
uv run --no-sync python -I tools/check_import_boundaries.py
uv run --no-sync python -I tools/check_import_boundaries.py --self-test
uv build --no-sources --offline --link-mode copy --default-index https://pypi.org/simple
uv run --no-sync python -I tools/check_wheel_install.py
uv run --no-sync python -I tools/check_runtime_design.py --self-test
uv run --no-sync python -I tools/check_runtime_design.py
uv run --no-sync python -I tools/check_project_docs.py --self-test
uv run --no-sync python -I tools/check_project_docs.py
git diff --check
```

## 验收边界与下一轮

DEF-0005 的 API 缺口与 DEF-0006 的子类边界经实现、反例回归及独立复核关闭。302 项测试通过后进行的整分支复核发现 DEF-0007，因此此候选不能发布，DEV-M1-04 继续 DOING，I01 尚不能完成技术出口。G-I01 的产品验收仍为 PENDING，G-M1 未关闭；REQ-002 / REQ-003 等跨阶段需求继续 DEVELOPING，不提前 ACCEPTED。

本轮是 Linux、单拥有者同步、内存 Registry 与静态 SIM mock 的证据；未重跑 Windows，也不代表实际 SIM / XR / REAL 联调。backend_epoch 是外部声明的静态身份上下文；读状态不是并发原子快照，不含完整 StateProjection、新鲜度或来源质量。下一轮先锁定 I02 的租约、状态投影和 mock 执行 / 停止范围，再从 DEV-M1-05 推进。

## DEF-0007：失败的批量发现提前消费能力版本

原 discover 逐项调用会立即保存版本的 describe。独立探测先把 alpha / bravo 注册在版本 1，再临时改变 alpha 模式，并让 bravo 返回不同 epoch。discover 抛 BindingMismatch，没有返回任何结果；将 alpha 模式恢复后再次描述，能力与先前已发布版本完全相同，版本却变成 3。

该失败发生在单拥有者的一次同步调用内，与并发或物理快照一致性无关。探测脚本和退出 1 的输出分别保存在本地 `whole-review-63d4637-discover-864vBU6t/probe.py` 与 `output.log`。修正要求先计算所有候选结果，整批读取成功后才提交版本；增加两个绑定的失败 / 重试回归，成功证据另记 [AR-0015](AR-0015-readonly-registry-batch-final.md)。原有通过与本次失败均保留。
