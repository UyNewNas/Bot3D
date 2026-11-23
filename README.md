# Bot3D 内核基础

当前只建立 DEV-M1-02 的最小可安装 Python 包、时钟领域值 / 应用端口及单元测试基础。没有 Registry、目标 / 四元数类型、运动协调器、ROS / SDK 连接或设备控制入口。架构与跟踪从[文档入口](docs/README.md)进入。

**当前状态：DEV-M1-02 已完成。** 在 Windows 11／CPython 3.12.11 上完成非编辑安装、三个 T26 切片和独立 wheel 消费者验证。

## 开发环境

- 本轮复现：CPython 3.12.11、uv 0.10.9；产品 Python minor 选择 3.12，默认系统 3.13 不作为替代。
- 运行依赖为空；pytest 与构建工具固定在 [pyproject.toml](pyproject.toml)，完整开发依赖解析见 [uv.lock](uv.lock)。
- 使用项目虚拟环境，不修改系统解释器；本轮 patch 是复现版本，不是最新安全版本或生产 / REAL 准入声明。版本决策、限制和证据见[工程基线](docs/design/06-python-foundation.md)。

在仓库根目录运行：

```bash
uv sync --locked --no-editable --reinstall-package bot3d-kernel --link-mode copy --default-index https://pypi.org/simple
uv run --no-sync python -I -m pytest
uv run --no-sync python -I tools/check_import_boundaries.py
uv build --no-sources --link-mode copy --default-index https://pypi.org/simple
uv run --no-sync python -I tools/check_wheel_install.py
```

`--no-editable` 安装构建出的包，`--reinstall-package bot3d-kernel` 在源码修改后刷新并重装本地分发，测试使用隔离解释器 `-I`。`--link-mode copy` 用于本轮 Windows 环境。解释器与开发、构建依赖均已缓存时，sync 和 build 可加 `--offline`。

## 最小 API

```python
from framework.adapters.clocks import ManualMonotonicClock
from framework.application.ports import MonotonicClock
from framework.domain.time import MonotonicInstant

clock = ManualMonotonicClock(clock_id="test-protection")
port: MonotonicClock = clock
before: MonotonicInstant = port.now()
clock.advance_ns(10)
assert port.now().elapsed_ns_since(before) == 10
```

人工钟仅用于测试 / mock 的显式依赖注入，不是真实保护钟。真实时钟使用 `SystemMonotonicClock`；每个运行实例共享明确的时钟对象，不在每个请求上新建时钟。不同 clock_id 不可直接相减；没有实现租约 / 超时策略，时钟测试不等于 T04 / T16 / T42 已通过。

## 检查与证据

T26/package、T26/imports 和 T26/ports-clock 的复现命令与结果见 [AR-0005](docs/project/records/AR-0005-python-foundation-recheck.md)。I01 还有七个切片待执行，产品验收 PENDING。

已有设计资料可另外检查：

```bash
uv run --no-sync python -I tools/check_project_docs.py --self-test
uv run --no-sync python -I tools/check_project_docs.py
uv run --no-sync python -I tools/check_runtime_design.py --self-test
uv run --no-sync python -I tools/check_runtime_design.py
```

设计模型只算 DOC，不能代替运行时 / 停止 / 恢复产品测试。没有硬实时、持久性、设备 fencing 或停车保证；REAL 未授权。不提供通过强杀进程停车的方法。
