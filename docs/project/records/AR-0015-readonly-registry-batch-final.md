# AR-0015：只读发现批量版本修正与最终复验

| 日期 | 范围 | 环境 | 技术结果 | 产品验收 |
| --- | --- | --- | --- | --- |
| 2026-11-23 | I01 · DEV-M1-04 · 批量发现与工程回归 | Linux x86_64、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | UNIT / MOCK、安装与 DOC PASS | PENDING |

## 版本、修正与范围

在候选 `63d463739e25314991dc3148f55cb1cd8b861e33` 的基础上修正失败批量发现的版本提交；该候选基于已合并 master 的 b084218。实现前缺口、数据子类和批量版本问题分别保留在 [AR-0012](AR-0012-readonly-registry-start.md)、[AR-0013](AR-0013-readonly-registry-review.md)、[AR-0014](AR-0014-readonly-registry-final.md)。当前工作树由包含本记录的提交定位，原始输出与输入校验清单按 AR 编号留存。

执行角色为开发助手；独立助手完成整分支复核并提出批量发现反例，修正经过针对性复核。现实验收角色未指定。

本次只修改 Registry 的批量发现实现和对应测试：按逻辑 ID 顺序对每个绑定读取一次，使用不提交版本的描述路径建立完整结果元组，全部成功后才保存每个绑定的新能力快照。任何读取抛错时都保留原版本。该提交规则是同步内存语义，不承诺多个后端的物理快照一致。

## 实际执行

| 切片 / 检查 | 状态 | 实际证据 |
| --- | --- | --- |
| DEF-0007 回归 RED | FAIL（已保留） | 旧安装的新增双绑定测试失败，显示 revision 3 而非 1；输出为 AR-0014/task-1-final-fix-red.log |
| 非编辑安装及针对性 GREEN | PASS | 固定版本离线重装退出 0；双绑定测试 1 passed，失败后恢复输入保持 revision 1，成功重试递增一次 |
| 独立反例复验 | PASS | 原整分支探测脚本退出 0；失败批次不消费已发布版本 |
| T46/discovery | PASS | 36 passed；包含按 ID 排序、每个后端一次读取、失败批次与成功重试 |
| 全量 pytest | PASS | 303 passed，退出 0；原 170 项加本轮 133 项，十个技术切片均在全量集合中 |
| 其余九个切片 | PASS | T26 为 4 / 48 / 30，T28 为 45 / 18 / 25，T29 为 35 / 17，T46/readonly 为 45；独立 marker 输出保留在 AR-0014，本次全量再次回归 |
| 依赖边界 | PASS | 11 个核心模块扫描通过；检查器未修改，32 项自测证据保留在 AR-0013 |
| 构建 / 独立 wheel 消费者 | PASS | 重新离线构建 sdist→wheel；空环境仅安装 bot3d-kernel，时间、几何及只读查询通过 |
| 工件一致性 | PASS | 新 wheel 全部 framework Python 文件逐字节匹配源码；元数据包含当前 README，无运行依赖 |
| README 两个示例 | PASS | 仓库外隔离解释器均退出 0，无 stderr；输出与 AR-0014 一致 |
| 版本与锁 | PASS | 原 API、Python / uv / pytest 固定版本、uv.lock 与运行零依赖不变；锁检查输出保留在 AR-0014 |
| 未改变的 DOC 工具 | PASS | 文档自测 43；运行时自测 25、场景 44（T31=26、T34=18）；输出保留在 AR-0013，仅是 DOC |
| DOC 汇总与差异检查 | PASS | 35 篇 Markdown、82 个表、234 个本地链接、3 个严格 JSON 块；编号、58 条依赖与台账一致；git diff --check 退出 0 |

修正相关输出独立保存在本地 `AR-0015/task-1-final-fix-*` 与 `AR-0015/final-*`，没有覆盖旧失败。完整十个 marker、锁与 DOC 工具的复现命令见 [AR-0014](AR-0014-readonly-registry-final.md)；本次代码变化的复验为：

```bash
uv sync --locked --no-editable --reinstall-package bot3d-kernel --offline --link-mode copy --default-index https://pypi.org/simple
uv run --no-sync python -I -m pytest -q tests/test_registry_discovery.py::test_failed_discovery_preserves_revisions_until_successful_retry
uv run --no-sync python -I -m pytest -m t46_discovery
uv run --no-sync python -I -m pytest
uv run --no-sync python -I tools/check_import_boundaries.py
uv build --no-sources --offline --link-mode copy --default-index https://pypi.org/simple
uv run --no-sync python -I tools/check_wheel_install.py
uv run --no-sync python -I tools/check_project_docs.py
git diff --check
```

## 验收边界与下一轮

DEF-0005 / DEF-0006 的基本 API 和具体数据边界证据继续有效，DEF-0007 的失败批量版本问题由本次修正、原反例与回归关闭。DEV-M1-04 为 DONE；I01 四个工作包、十个 UNIT / MOCK 技术切片齐备，进入 IN_ACCEPTANCE。G-I01 产品验收仍为 PENDING，G-M1 未关闭；跨阶段需求继续 DEVELOPING。

当前交付是 Linux、单拥有者同步、内存 Registry 和静态只读 SIM mock。运行时 epoch 轮转、完整 StateProjection、并发 / 持久化以及实际 SIM / XR / REAL 和 Windows 复验仍须后续证据；不把这些缺失默认为通过。下一轮先锁定 I02 范围，再从 DEV-M1-05 的控制租约与显式激活推进。
