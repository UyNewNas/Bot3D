# AR-0020：控制权公开结果修正与最终交付

| 日期 | 范围 | 环境 | 技术结果 | 产品验收 |
| --- | --- | --- | --- | --- |
| 2026-11-23 | I02 · DEV-M1-05 · 结果一致性与交付回归 | Linux x86_64、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | UNIT / MOCK、安装、DOC 与技术复核 PASS | PENDING |

## 范围

在候选 `78292d7b078a7f1ebf07492d5af5cf95647489c6` 基础上集中修正公开结果一致性。首轮与整分支失败分别保留在 [AR-0017](AR-0017-control-authority-final.md)、[AR-0019](AR-0019-control-authority-docs-final.md)；最终源码与文档由包含本记录的提交定位，源码 / 工件 SHA-256 清单按 AR 编号保留。开发助手实现与验证，独立助手负责整分支和针对性复核，产品验收角色未指定。

修正涉及 `AuthorityResult` 与四个回归用例：同绑定 CONTEXT_CHANGED 失权事件、对应永久状态拒绝均要求正确快照标志，历史代数也不能撤销退役；返回租约的 ID 不得同时出现在失权效果中。合法的退役 / 故障拒绝、FORBIDDEN + CLOCK_FAULT，以及不同新 token 搭配旧失权效果继续允许。管理器转换、API、版本与运行依赖未改。

## 实际执行

| 切片 / 检查 | 状态 | 实际证据 |
| --- | --- | --- |
| DEF-0011 / DEF-0012 回归 RED | FAIL（保留） | 修正前 4 failed、13 deselected，均 DID NOT RAISE ValueError；合法对照先通过，见 AR-0019/task-1-final-fix-red.log |
| 非编辑安装 / 针对性 GREEN | PASS | 固定版本离线重装退出 0，clock / loss / activation 三文件 69 passed |
| 全量 pytest | PASS | 383 passed，退出 0；原 303 项加本轮 80 项，十四个技术切片完整回归 |
| T01/leases | PASS | 11 passed，设备单写、会话授权、租约身份与线程竞争 |
| T07/authority-loss | PASS | 17 passed，失权交接、聚合未结执行与公开结果一致性 |
| T30/activation | PASS | 35 passed，前置策略、明确确认、健康运动及上下文退役 |
| T42/lease-clock | PASS | 17 passed，精确到期、保护钟隔离与全局时钟故障 |
| 依赖边界 | PASS | 13 个核心模块；检查器未改，32 项自测沿用 AR-0017 |
| sdist→wheel / 独立消费者 | PASS | 修正后重新离线构建；空 venv 仅安装本分发，时间、几何、只读与控制权演练全部通过 |
| 源码 / 安装 / 工件一致性 | PASS | 已安装包、sdist、wheel 的全部 16 个 framework Python 文件逐字节匹配源码；README 与 UTF-8 元数据一致，运行依赖为零 |
| 文档示例 | PASS | 两个 README 示例和控制权示例在仓库外隔离运行，输出完全匹配，退出 0、无 stderr |
| 版本 / 锁与既有 DOC 工具 | PASS（沿用） | 版本与 uv.lock 未变；AR-0017 的锁检查、43 文档自测、25 运行时自测和 44 DOC 场景证据继续有效 |
| DOC 汇总 / 差异格式 | PASS | 43 篇 Markdown、96 个表、280 个本地链接、3 个严格 JSON 块、58 条开发依赖与两轮迭代状态一致；git diff --check 退出 0 |
| 集中修正的针对性复核 | PASS | 独立复核 78292d7..69a826e，DEF-0011 / DEF-0012 均 ADDRESSED；修正无新增 Critical / Important 问题，无未决项 |

原始输出独立保存在本地 `AR-0020/task-1-final-fix-*` 与 `final-*`，不覆盖旧失败。复现命令：

```bash
uv sync --locked --no-editable --reinstall-package bot3d-kernel --offline --link-mode copy --default-index https://pypi.org/simple
uv run --no-sync python -I -m pytest -q
uv run --no-sync python -I -m pytest -q -m t01_leases
uv run --no-sync python -I -m pytest -q -m t07_authority_loss
uv run --no-sync python -I -m pytest -q -m t30_activation
uv run --no-sync python -I -m pytest -q -m t42_lease_clock
uv run --no-sync python -I tools/check_import_boundaries.py
uv build --no-sources --offline --link-mode copy --default-index https://pypi.org/simple
uv run --no-sync python -I tools/check_wheel_install.py
uv run --no-sync python -I tools/check_project_docs.py
git diff --check
```

## 交付与后续

DEF-0011 / DEF-0012 由负例、合法对照、全量回归与独立针对性复核关闭，整分支技术出口齐备。DEV-M1-05 为 DONE，交付内存单写租约、显式激活、连续前置策略、失权事件与聚合未结执行门禁。README 保持项目主页结构，补齐实际控制权模块与可运行例子；I02 六个工作包、依赖与最低主题已建立，本轮只交付 05。

REQ-005 / REQ-006 保持 DEVELOPING，I02 ACTIVE、I01 IN_ACCEPTANCE，产品验收 PENDING。后续由 DEV-M1-06 实现规范化命令摘要、JournalPort 与内存替身，再按依赖推进状态投影和 mock 执行 / 停止闭环。

可信会话认证、当前投影与停车资格、全部未结原因的审计处置、物理 STOP / 最终下发、跨进程 / 重启与新 epoch 生命周期，以及 SIM / XR / REAL 联调分别留对应工作包；本轮不把应用许可或 UNIT / MOCK 结果当作这些集成已完成的证据。
