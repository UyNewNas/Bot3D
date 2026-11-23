# AR-0004：最小 Python 工程与时钟端口

| 日期 | 范围 | 基线 | 产品验收 |
| --- | --- | --- | --- |
| 2026-11-20 | I01 · DEV-M1-02 · 静态与 DOC 检查 | CPython 3.12.11、uv 0.10.9 | PENDING |

本轮交付最小 Python 包、领域时间值、应用时钟端口、系统钟与可控人工钟，并固定开发依赖与构建配置。依赖锁一致性检查通过。离线缓存缺少所需依赖，包安装与构建未完成，DEV-M1-02 当时为 BLOCKED。

## 验证结果

| 切片 | 状态 | 本轮证据 |
| --- | --- | --- |
| T26/package | BLOCKED | 15 份 Python 源码通过解析，配置与锁文件通过核对。安装包测试和空环境 wheel 验证未运行 |
| T26/imports | BLOCKED | 依赖检查器的 21 项自测通过，扫描的 5 个核心模块符合依赖方向。安装包的隔离导入测试未运行 |
| T26/ports-clock | BLOCKED | 时钟测试已定义，pytest 未运行 |

文档检查器的 43 项自测和文档追踪检查通过。运行时设计模型的 25 项自测与 44 个设计用例通过，其中 T31 有 26 个，T34 有 18 个。T31 和 T34 的产品测试未运行。

## 复现命令

从仓库根目录使用选定的解释器运行这些静态与 DOC 检查。

```bash
uv lock --check --offline
python -I tools/check_import_boundaries.py --self-test
python -I tools/check_import_boundaries.py
python -I tools/check_project_docs.py --self-test
python -I tools/check_project_docs.py
python -I tools/check_runtime_design.py --self-test
python -I tools/check_runtime_design.py
```

安装、构建和三个 T26 切片的后续验证见 [AR-0005](AR-0005-python-foundation-recheck.md)。
