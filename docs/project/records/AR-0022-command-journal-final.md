# AR-0022：命令日志与幂等最终交付

| 日期 | 范围 | 环境 | 技术结果 | 产品验收 |
| --- | --- | --- | --- | --- |
| 2026-11-24 | I02 / DEV-M1-06 | Linux、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | UNIT / MOCK、安装、工件与 DOC 检查 PASS；审查问题已修正 | PENDING |

## 交付范围

基于 DEV-M1-05 PR #3 的 `e653eeac9dd1c366ac1e95af70486f87f192116e`，交付[命令日志设计](../../design/10-command-journal-and-idempotency.md)和[实施计划](../../superpowers/plans/2026-11-24-dev-m1-06-command-journal.md)。本记录所在提交定位最终源码和文档；初始基线与 RED 证据见 [AR-0021](AR-0021-command-journal-start.md)。

- `PoseCommand` 等不可变领域值和带版本规范编码；SHA-256 排除传输 request_id，覆盖执行参数、期限、上下文、epoch 与租约。
- `JournalPort`、候选接受、状态 / 意图 / 原句柄 / 对账事实和不可变原终态；状态与确定性使用既有协议枚举。
- `InMemoryJournal` 原子插入、同键重试 / 冲突、事件 ID 去重和 revision CAS；只保留原绑定及原尝试。
- 写入故障对受影响键保持 UNKNOWN，拒绝新写入；未受影响历史仍能读取。实例保留明确 durable=false，无自动删除或恢复声明。

日志不占业务槽、不鉴权、不执行、不授予控制权；候选记录不是公开 ACCEPTED。完整接受复核、后端调用次数、物理停车和 STOP 不等待普通日志仍由后续协调 / 停止链验证。

## 实际测试与复核

| 检查 | 实际结果 |
| --- | --- |
| 既有基线 | 383 passed；独立助手验证固定环境与非编辑安装来源 |
| 摘要初始 RED→GREEN | 51 missing-API 断言失败后实现；全量 434 passed |
| 日志初始 RED→GREEN | 45 missing-API 断言失败后实现；全量 479 passed |
| 独立整分支审查 | 独立读取 e653eea..138bb97，并复跑 479 项；无 Critical，3 项 Important 和 1 项 Minor，见下节 |
| 三项问题修正 RED | 12 failed、2 passed、88 deselected；9 个 Unicode 输入反例、1 个意图顺序反例、2 个取消顺序反例；合法 Unicode 和未下发取消对照已通过 |
| 修正后隔离全量 | 493 passed，退出 0；全部 110 项新增测试和原 383 项回归通过 |
| 安装消费者 | 现有包测试在仓库外 `python -I` 中运行扩展探针，覆盖同键重试、不同租约冲突、原句柄和 UNKNOWN 终态追加事实 |
| T02/digest-retry | 7 passed，等价摘要和合法 Unicode 精确身份 |
| T03/digest-conflict | 54 passed，执行字段变化、非法值与 Unicode 别名拒绝 |
| T02/journal-order | 41 passed，并发插入 / CAS、顺序、历史终态与取消路径 |
| T18/journal-fault | 8 passed，写前 / 写后不确定性、读故障与未受影响历史 |
| 核心依赖边界 | 15 个核心模块 PASS，原检查器未修改 |
| sdist→wheel / 空消费者 | 固定工具离线构建成功；仓库外空 venv 仅安装 bot3d-kernel；基础类型、只读发现、控制权和日志演练通过 |
| 文件 / 元数据一致性 | 全部 19 个 framework Python 文件在源码、安装包、sdist 和 wheel 中逐字节一致；当前 README 与三处 UTF-8 元数据一致；锁文件未变，运行第三方依赖为零 |
| README 示例 | 3 个 Python 示例在仓库外隔离解释器运行，精确输出通过，无 stderr |
| DOC 检查 | 47 篇 Markdown、104 个表、307 个本地链接、3 个严格 JSON 块、59 条无环开发依赖，编号 / 状态 / 两个迭代与 AR 索引一致 |
| 设计模型回归 | 44 个 DOC 场景通过；T31=26、T34=18；不计作产品实现或硬件验证 |
| 差异格式 | git diff --check 通过 |

首次工件检查脚本使用邮件 BytesParser 默认字符集，中文 README 被误解码为替换字符而触发一致性断言。直接比较原始 UTF-8 正文确认工件实际一致；改为明确 UTF-8 解码后安装包 / sdist / wheel 元数据比对全部通过。原误报保留在 `artifact-verification.log`，复验为 `artifact-verification-utf8.log`；未修改包内容来迎合错误解析。

### 独立审查发现与处置

1. **Unicode 编码别名。** Python 字符串中的 surrogate 对可能与合法补充平面字符产生相同 JSON 转义。命令标识现拒绝 surrogate 码点，合法非 ASCII 字符继续可用且不做 Unicode 归一化。9 个字段反例先失败后通过。
2. **意图早于规划。** 原实现允许 ACCEPTED 后立即写意图。现必须已经进入 PLANNING；独立的提前写入反例先失败后通过，拒绝后原记录保持不变。
3. **取消跳过请求。** 原实现允许已受理状态直接 CANCELLED。现 EXECUTING 或已有后端回执时，必须经 CANCEL_REQUESTED；保留协调器能证明未裁决下发的直接取消。两个反例和合法对照验证完成。

这三项属于同一轮集中修正，修正由执行者通过 RED→GREEN 和全量回归验证，未把该结果表述为另一次独立审查。历史失败输出保留，未覆盖。

**未优化的 Minor：** 每次追加复制并核对完整历史，单次成本随记录数量增长，连续追加整体可能为二次成本；锁内不做外部 I/O，但不保证固定持锁时间。当前仅用于小规模内存 mock；长历史性能与有界通路留后续工作。设计已明确该限制。

**审查范围裁决：** 鉴权 / 控制权复核、最终下发 fencing、物理取消 / 停车证据、SQLite 持久性和重启恢复保留在对应后续工作包。当前日志测试不能代替上述集成；若把它们误当成已完成，会错误声称真实执行安全或跨进程去重。

## 复现命令

在已安装锁定工具的工作区运行；本次 `.local/AR-0021/environment.sh` 只用于选择精确版本，不是分发的运行依赖。

```bash
source .local/AR-0021/environment.sh
uv sync --locked --no-editable --reinstall-package bot3d-kernel --offline --link-mode copy --default-index https://pypi.org/simple
uv run --no-sync python -I -m pytest -q
uv run --no-sync python -I -m pytest -q -m t02_digest
uv run --no-sync python -I -m pytest -q -m t03_conflict
uv run --no-sync python -I -m pytest -q -m t02_journal
uv run --no-sync python -I -m pytest -q -m t18_journal_fault
uv run --no-sync python -I tools/check_import_boundaries.py
uv build --no-sources --offline --link-mode copy --default-index https://pypi.org/simple
uv run --no-sync python -I tools/check_wheel_install.py
uv run --no-sync python -I tools/check_project_docs.py
uv run --no-sync python -I tools/check_runtime_design.py
git diff --check
```

本次原始日志保存在 `.local/AR-0021/` 和 `.local/AR-0022/`，含 `journal-red.log`、`journal-green.log`、`review-red.log`、`review-green.log` 与最终检查。最终源码 / 工件比对清单随本地验证输出保存；代码、测试、设计、运行方式和该摘要随 Git 提交交付。

## 状态与下一步

技术出口已通过，DEV-M1-06 为 DONE，REQ-009 保持 DEVELOPING。复用既有 DEV-M1-04 身份类型，台账前置补充 04，不复制另一套绑定模型；不依赖控制权管理器执行。I02 ACTIVE、I01 IN_ACCEPTANCE、产品验收 PENDING。后续先推进 DEV-M1-12 状态投影，再推进 DEV-M1-07 可控 Planner / Backend mock，随后按依赖接协调与停止链。

功能 PR 面向 master，明确依赖仍未合并的 PR #3；DEV-M1-06 的新增范围从 e653eea 比较。没有自动合并 PR、连接设备或发布运行服务。
