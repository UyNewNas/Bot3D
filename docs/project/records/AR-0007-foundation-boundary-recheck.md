# AR-0007：工程基础依赖边界修复复验

| 日期 | 范围 | 基线 | 产品验收 |
| --- | --- | --- | --- |
| 2026-11-23 | I01 · DEV-M1-02 · DEF-0002 修复与 T26 复验 | Linux x86_64、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | PENDING |

## 版本与修复范围

基线提交 `319fed05a2d319bc6dc1865963670585fdc27cf9` 加本轮未提交工作树。执行角色为开发助手，最终代码复核由独立助手完成，现实验收角色未指定。Python、uv、运行与开发依赖、时钟 API 均沿用既定基线。没有连接设备或加入新的产品功能。

修复 [AR-0006](AR-0006-foundation-boundary-review.md) 的 DEF-0002：核心依赖检查拒绝 xmlrpc / wsgiref HTTP 传输；纯领域另外拒绝线程、事件循环、执行器与进程依赖，应用协调层保留并发实现选择。新增 16 个 pytest 用例及检查器自测，覆盖类型专用和函数内导入。修复前 14 个违规反例失败、2 个合法应用正例通过；修复后 16 个全部通过。

## 验证结果

| 切片 / 检查 | 状态 | 实际证据 |
| --- | --- | --- |
| T26/package | PASS | 独立 marker 运行 4 passed；sdist 与由其构建的 wheel 成功；独立空环境仅安装 bot3d-kernel 并通过离线导入与时钟探测 |
| T26/imports | PASS | 独立 marker 运行 48 passed；32 项检查器自测和 5 个核心模块扫描通过 |
| T26/ports-clock | PASS | 独立 marker 运行 30 passed，时钟行为未修改 |
| 全量 pytest | PASS | 82 passed，退出 0；原 66 项加本轮 16 项 |
| 依赖锁 | PASS | uv lock --check --offline 退出 0；锁文件未改动 |
| 文档与运行时设计 | PASS | 文档检查器 43 项自测及 23 篇 Markdown、61 个表、138 个本地链接的追踪检查通过；运行时设计 25 项自测及 44 个 DOC 用例通过 |
| 最终独立代码复核 | PASS | 独立审查实现、反例、验证日志和分层范围；没有需要修复的代码或证据问题；不代替产品验收 |

## 复现命令

在仓库根目录，使用基线要求的 CPython 3.12.11 / uv 0.10.9。测试使用已安装的非编辑包与隔离解释器；不把源码目录注入消费者路径。

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

缺陷反例可单独复验：

```bash
uv run --no-sync python -I -m pytest tests/test_dependency_boundaries.py -k 'stdlib_http_transports or concurrency' --tb=short -q
```

上述安装、锁检查、测试、构建、独立消费者和 DOC 命令实际退出码均为 0。最后另运行 git diff --check，退出 0。运行时设计的 44 个用例分为 T31 的 26 个与 T34 的 18 个，只算 DOC，不计为产品竞态 / 恢复测试。原始输出、命令与输入文件校验清单按本 AR 编号留存。

## AC 核对与剩余边界

AC-001 的最小工程、安装与依赖边界切片及 AC-007 的时钟基础切片通过。检查器仍是已知依赖规则的回归检查，不是恶意 Python 沙盒，也不是所有标准库传递依赖的完整证明。

原 Windows 执行证据保留在 [AR-0005](AR-0005-python-foundation-recheck.md)，本轮记录为 Linux 补充复验；本轮没有重跑 Windows。DEV-M1-02 保持 DONE，DEV-M1-03 为 TODO，I01 为 ACTIVE。G-I01 / G-M1 产品验收 PENDING；T28 / T29 / T46 的七个后续切片及 T31 / T34 产品实现测试均未运行。

DEF-0002 经代码、测试、文档和独立复核关闭。DEV-M1-02 的本轮收尾修正完成，仍等待 Git 提交 / 推送的单独授权。本轮没有 Git 提交、推送或外部发布。
