# AR-0024：状态投影最终交付

| 日期 | 范围 | 环境 | 技术结果 | 产品验收 |
| --- | --- | --- | --- | --- |
| 2026-11-24 | I02 / DEV-M1-12 | Linux、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | 六项审查问题已修正；598 项回归、安装 / 工件与 DOC 检查 PASS | PENDING |

## 范围与基线

接续 DEV-M1-06 PR #4 的 `b4f3802484c835bca83511d0e5a15a7b8557d1df`，在独立 `feat/dev-m1-12-state-projection` 分支交付[状态投影设计](../../design/11-state-projection.md)与[实施计划](../../superpowers/plans/2026-11-24-dev-m1-12-state-projection.md)。基线和首轮 RED→GREEN 见 [AR-0023](AR-0023-state-projection-start.md)。本记录所在提交定位最终源代码与文档。

交付包含不可变反馈 / 上下文 / 时间映射 / 快照，目标与计划引用分离，确定的采纳和重复 / 乱序规则，分项来源与质量，源 / 接收双年龄，可信静止窗口及 DERIVED FK。所有阈值显式配置，本轮人工值仅用于测试。运行仍只依赖标准库，原 Registry、控制权和命令日志行为保留。

本对象由单一协调序列持有；快照是其观察时刻的事实，不能替代未来执行 / 停止用例对最新采纳版本的复核。readiness、租约 / ARMED、命令状态、原写入者失效与执行锁分别由既有或后续组件负责。

## 测试与独立复核

| 检查 | 实际结果 |
| --- | --- |
| 基线 | 固定工具、非编辑安装、隔离解释器；493 passed |
| 首轮行为 RED→GREEN | 87 个明确缺失安装 API 的断言失败；实现后新增 87 项和全量 580 项通过 |
| 独立整分支审查 | 独立读取 b4f3802..6acf17b，复跑 87 项投影测试，发现 2 Critical / 4 Important；安装包反例见下节 |
| 集中修正 RED | 新增 18 项回归，15 failed / 3 passed；包括正确边界和合法重复对照 |
| 集中修正 GREEN | 非编辑重装后 598 passed；原 493 项 + 本轮 105 项 |
| 最终分项、工件与文档检查 | 全部已运行，结果见下节；不以 DOC 场景替代产品执行证据 |

### 六项发现与处置

1. **Critical：映射只覆盖接收时刻。** valid_from=20 时，源时刻 8 / 13 / 18、统一接收于 20 的旧包曾能得到 FRESH / STOPPED。现要求完整映射采样区间、原接收和当前观察时刻均被有效窗口覆盖；含不确定度跨越起点的失败例和恰好位于起点的合法对照。
2. **Critical：静止证明内的迟到矛盾被忽略。** 已采纳 1 / 2 / 3 后，序号 2 重传却声明运动曾按普通乱序丢弃并保留 STOPPED。现保留能覆盖保证窗口的最短观测后缀及原包；窗口内同序号事实矛盾锁定 INVALID。测试覆盖速度、位置、控制器、源时刻和缺数据，合法原包重传与窗口外旧包保持既有语义。
3. **Important：上下文回切复活旧反馈。** A→B→A 曾只按值相等判断，旧数据和 FK 可恢复。现记录上下文采纳代数，回切后仍须新包，原包重复不能重新获得新鲜度。
4. **Important：新映射刷新相同源时刻。** 旧源 tick=0 已陈旧，更换 offset=40 后以更高序号重传 tick=0 曾恢复 FRESH。现保留更新时的源水位，源时间严格前进才采用新映射；中间缺时刻的包不能重置该约束。
5. **Important：FK 缺源标识。** 同后端两个源的相同序号可互用 FK。现 ForwardKinematicsResult 必须携带 source_id，并与原采纳包核对；同源合法结果仍可使用。
6. **Important：直接 DERIVED 输入绕过依据质量。** 同包缺失 / 无效关节时，直接给出的 DERIVED 位姿曾显示 FRESH。现该输入明确声明由同包关节计算，继承关节质量，并保留更严重的位姿自身错误；apply_fk 继续强制派生来源并保留原时间。

以上为一次独立审查后的集中修正。修正由执行者通过失败反例、合法对照和全量回归核验，不把它称为第二次独立审查；原始失败输出保留。

**性能边界：** 当前投影按保留窗口的样本数复制、检查事实并计算关节位置范围。窗口会滚动淘汰早期包，但未测高频吞吐、固定处理时间或容量 / 背压；这些由 DEV-M1-16 继续，当前仅用于人工可控 mock。不会为了性能省略停车证明依赖的冲突检查。

## 最终工程证据

| 检查 | 实际结果 |
| --- | --- |
| 最终非编辑重装与隔离全量 | 598 passed，退出 0；包从本 worktree 的 .venv/site-packages 导入 |
| T06/projection | 43 passed，目标 / 计划 / 实际、分项来源、上下文代数、原源 FK 及输入边界 |
| T06/order | 6 passed，重复 / 乱序、冲突与换钟锁定、源暂停、state_seq |
| T42/feedback-clock | 26 passed，独立年龄、保守区间、半开边界、映射有效期 / 更新、保护钟和接收错误 |
| T10/stationary | 30 passed，完整窗口、断层 / 速度 / 位移、停止轮次、窗口内矛盾与合法重传 |
| 核心依赖 | 17 个核心模块 PASS；安装消费者禁止外部服务导入及 I/O 的既有检查继续通过 |
| sdist→wheel / 空消费者 | 固定工具离线构建成功；仓库外空 venv 仅安装 bot3d-kernel，完整已安装 API 演练通过 |
| 源 / 工件一致性 | 全部 21 个 framework Python 文件在源码、已安装包、sdist、wheel 中逐字节一致；README 与三处 UTF-8 元数据一致 |
| 工具与依赖 | CPython 3.12.11、uv 0.10.9、pytest 8.4.2；uv.lock 与基线完全相同，运行第三方依赖为零 |
| README 示例 | 4 个 Python 示例在仓库外 `python -I` 运行，精确输出通过且无 stderr；新增状态例输出 STOPPED、DUPLICATE 5 3 0、STALE UNKNOWN |
| 文档结构 | 51 篇 Markdown、113 个表、335 条本地链接、3 个严格 JSON 块、59 条无环开发依赖；状态总数、两个迭代和 24 个 AR 索引一致 |
| 设计级回归 | 44 个 DOC 场景，T31=26、T34=18；不计作产品线程 / 存储 / 设备实现证据 |
| 差异格式 | git diff --check 通过 |

## 复现命令

在固定工具可用的工作区运行；本次 `.local/AR-0023/environment.sh` 仅用于选择工具与缓存，不是分发运行依赖。

```bash
source .local/AR-0023/environment.sh
uv sync --locked --no-editable --reinstall-package bot3d-kernel --offline --link-mode copy --default-index https://pypi.org/simple
uv run --no-sync python -I -m pytest -q
uv run --no-sync python -I -m pytest -q -m t06_projection
uv run --no-sync python -I -m pytest -q -m t06_order
uv run --no-sync python -I -m pytest -q -m t42_feedback_clock
uv run --no-sync python -I -m pytest -q -m t10_stationary
uv run --no-sync python -I tools/check_import_boundaries.py
uv build --no-sources --offline --link-mode copy --default-index https://pypi.org/simple
uv run --no-sync python -I tools/check_wheel_install.py
uv run --no-sync python -I tools/check_project_docs.py
uv run --no-sync python -I tools/check_runtime_design.py
git diff --check
```

原始输出保存在本工作区 `.local/AR-0023/` 和 `.local/AR-0024/`；其中包含 baseline、projection-red、review-red、review-green 与最终工程日志及工件哈希清单。源代码、测试、设计、可运行示例与本摘要随 Git 提交交付。

## 状态与后续

工程出口已通过，DEV-M1-12 为 DONE，REQ-014 为 DEVELOPING；I02 ACTIVE、I01 IN_ACCEPTANCE、产品验收 PENDING。本轮只完成 T06、T10/stationary、T42/feedback-clock 的状态证据切片，不关闭物理 STOP、执行解锁、命令预算或 T27 完成。

下一工作包是 DEV-M1-07 可控 Planner / Backend mock，再按依赖接 DEV-M1-08 / 09 协调与停止链。

已创建功能 [PR #5](https://github.com/UyNewNas/Bot3D/pull/5)，面向 master，明确依赖仍未合并的 PR #4 及其前序控制权分支。本工作包独立差异从 b4f3802 比较；功能提交为 `3dbd142a5af51dea7711f69a76a32178eb901829`。发布时远端 Git tree SHA 与本地已验证内容完全一致；后续交付记录提交仅补充 PR 链接。未自动合并、连接设备或发布运行服务。
