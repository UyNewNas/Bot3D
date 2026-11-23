# AR-0005：Python 工程基础复验

| 日期 | 范围 | 基线 | 产品验收 |
| --- | --- | --- | --- |
| 2026-11-23 | I01 · DEV-M1-02 · UNIT 与 DOC 复验 | Windows、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | PENDING |

本轮完成锁定依赖准备与非编辑安装，并构建了 bot3d-kernel 0.1.0 的 sdist 和 wheel。由 sdist 构建的 wheel 在独立空环境中离线安装、导入并通过基础时钟检查。此前依赖准备阻塞见 [AR-0004](AR-0004-python-foundation.md)。

## 验证结果

| 切片 | 状态 | 本轮证据 |
| --- | --- | --- |
| T26/package | PASS | 4 项 pytest 测试通过，覆盖版本、零运行依赖、非编辑安装与隔离导入。独立空环境的 wheel 安装与导入通过 |
| T26/imports | PASS | 32 项 pytest 测试通过，覆盖依赖策略正反例和已安装核心模块的隔离导入。另有 21 项检查器自测通过，5 个核心模块通过依赖方向扫描 |
| T26/ports-clock | PASS | 30 项 pytest 测试通过，覆盖领域值、时钟端口、人工推进、时钟域隔离和系统单调读数 |

全量 pytest 为 66 项通过。锁一致性检查、文档检查器的 43 项自测和文档追踪检查通过。运行时设计模型的 25 项自测与 44 个设计用例通过，其中 T31 有 26 个，T34 有 18 个。

## 复现命令

在仓库根目录运行。

```bash
uv sync --locked --no-editable --reinstall-package bot3d-kernel --link-mode copy --default-index https://pypi.org/simple
uv lock --check --offline --default-index https://pypi.org/simple
uv run --no-sync python -I -m pytest
uv run --no-sync python -I -m pytest -m t26_package
uv run --no-sync python -I -m pytest -m t26_imports
uv run --no-sync python -I -m pytest -m t26_ports_clock
uv run --no-sync python -I tools/check_import_boundaries.py --self-test
uv run --no-sync python -I tools/check_import_boundaries.py
uv build --no-sources --link-mode copy --default-index https://pypi.org/simple
uv run --no-sync python -I tools/check_wheel_install.py
uv run --no-sync python -I tools/check_runtime_design.py --self-test
uv run --no-sync python -I tools/check_runtime_design.py
uv run --no-sync python -I tools/check_project_docs.py --self-test
uv run --no-sync python -I tools/check_project_docs.py
```

## 验收边界

AC-001 的工程基础切片和 AC-007 的时钟基础切片通过。REQ-001 和 REQ-007 恢复 DEVELOPING。T04、T05、T16、T42 以及 T31、T34 的产品测试均为 NOT_RUN。

DEV-M1-02 为 DONE，I01 为 ACTIVE，DEV-M1-03 为 TODO。T28、T29、T46 的七个 I01 切片仍待执行。G-I01 与 G-M1 的产品验收为 PENDING。
