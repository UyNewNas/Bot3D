# AR-0018：控制权结果约束修正与最终复验

| 日期 | 范围 | 环境 | 技术结果 | 产品验收 |
| --- | --- | --- | --- | --- |
| 2026-11-23 | I02 · DEV-M1-05 · 结果约束与工程回归 | Linux x86_64、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | UNIT / MOCK、安装 PASS；DOC 汇总 FAIL | PENDING |

## 范围

首轮候选 8c258a1 的测试通过和公开构造器反例保留在 [AR-0017](AR-0017-control-authority-final.md)。修正候选为 `a671f183872a092863e0bb36412e0458e32b6fa2`，最终文档由包含本记录的提交定位。原始日志与相关源码 / 工件的 SHA-256 清单按 AR 编号保留。

本轮只增加 `AuthorityResult` 对 CLOCK_FAULT 与快照故障状态的一致性校验，以及同绑定 / 跨绑定两个反例回归。管理器转换没有改变。执行角色为开发助手，独立助手确认该问题已解决、修正未引入新问题；产品验收角色未指定。

## 实际执行

| 切片 / 检查 | 状态 | 实际证据 |
| --- | --- | --- |
| DEF-0009 回归 RED | FAIL（保留） | 修正前新增两例均 DID NOT RAISE ValueError；2 failed、11 deselected，见 AR-0017/task-1-review-fix-red.log |
| 非编辑安装与针对性 GREEN | PASS | 离线重新安装退出 0；clock / loss / activation 三个文件 65 passed |
| 独立针对性复核 | PASS | 同绑定和跨绑定 CLOCK_FAULT 均要求 faulted 快照；合法 FORBIDDEN + effects 仍成立，无新问题 |
| 全量 pytest | PASS | 379 passed，退出 0；原 303 项加本轮 76 项，十四个技术切片均包含在全量集合中 |
| T01/leases | PASS | 11 passed；设备可写唯一、授权登记、租约身份、线程竞争和续租 / 释放两种顺序 |
| T07/authority-loss | PASS | 13 passed；原绑定效果、拒绝仍交接、会话撤销、聚合执行标记及新增结果一致性 |
| T30/activation | PASS | 35 passed；显式激活、逐项前提、健康自身运动续租、上下文退役与拒绝优先级 |
| T42/lease-clock | PASS | 17 passed；保护钟期限、精确到期、全局故障与时钟无关保护入口 |
| 依赖边界 | PASS | 13 个核心模块扫描通过；未修改的检查器 32 项自测见 AR-0017 |
| 构建 / 空 wheel 消费者 | PASS | 修正后重新离线构建 sdist→wheel；仓库外空环境仅安装本分发，几何、只读与控制权演练通过 |
| 工件一致性 | PASS | sdist 与 wheel 的全部 16 个 framework Python 文件逐字节匹配源码；UTF-8 元数据和 sdist README 匹配当前主页，无运行依赖 |
| 文档三个示例 | PASS | 两个 README 示例与控制权示例均在仓库外隔离运行，退出 0、无 stderr、输出完全匹配 |
| 版本 / 锁与 DOC 工具 | PASS | Python / uv / pytest 版本与 uv.lock 未改；锁、43 项文档自测、25 项运行时自测与 44 个 DOC 场景输出保留在 AR-0017 |
| DOC 汇总 | FAIL | 台账标题额外声明了 0 项 DOING；检查器要求状态计数字典与实际非零状态完全相同，报 1 项 status-count 问题 |
| 差异格式检查 | PASS | git diff --check 退出 0，无输出 |

原有十个切片继续随全量回归：T26 为 package / imports / ports-clock，T28 为 values / basis / quaternion，T29 为 compose / revision，T46 为 discovery / readonly。具体基础证据在先前 AR 保留；本轮不把设计级 T31 / T34 运行当成执行或停车实现通过。

原始输出为本地 `AR-0018/task-1-review-fix-*`、`final-*`；没有覆盖 AR-0016 / AR-0017 的失败。完整复现命令如下：

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

## 交付与边界

DEF-0008 的新增 API 缺口、DEF-0009 的公开结果矛盾由实现、回归与独立针对性复核关闭。DEV-M1-05 为 DONE，REQ-005 / REQ-006 继续 DEVELOPING。I02 为 ACTIVE，G-I02 与产品验收 PENDING；I01 的历史验收状态不变。

当前交付是单进程、内存控制权与可信输入策略。会话认证、当前状态投影、聚合未结原因的证据与审计由后续组装提供；本轮不发送 STOP，不做设备 fencing，不证明实际停车，不自动换 epoch，也不提供可延后使用的最终下发票据。

DEF-0010：开发台账标题写入了零项状态，不符合现有 DOC 检查器的统计格式。实际任务状态和合计没有错误。修正为沿用既有非零状态标题，不修改检查器规则、不改变任务状态；这次 DOC 失败保留，文档复验见 [AR-0019](AR-0019-control-authority-docs-final.md)。

下一工作包为 DEV-M1-06：规范化命令摘要、JournalPort 与内存替身；其后按 I02 依赖接入状态投影与 mock 执行 / 停止链。最终功能分支发布前还需完成整分支技术复核，产品验收不由开发助手代签。
