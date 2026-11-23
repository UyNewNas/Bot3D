# Bot3D

**面向机器人仿真、真机与 XR 交互的任务协调框架。** Bot3D 以机器人能力、任务目标和状态反馈为应用接口，目标是让同一套任务流程可以在不同后端上复用。设备之间的差异由适配器、机器人模型、配置和标定处理。

[技术架构](#技术架构) · [实现方式](#实现方式) · [快速上手](#快速上手) · [开发路线](#开发路线) · [文档入口](docs/README.md)

## 项目目标

以固定基座机械臂为例，桌面应用和 XR 前端可以用同一个目标表达「让工具到达指定坐标系下的位姿」。切换到另一后端时，应用保留相同的任务逻辑，框架根据当前绑定的设备、模型和场景重新检查能力并规划。前端分别显示目标、计划和后端反馈，让操作者看清机器人实际到达的位置。

- **按能力表达任务。** 末端位姿、夹爪等能力有各自的参数、约束和可用条件。上层可以据此选择可执行的任务，并读到能力不可用的原因。
- **显式选择仿真或真机。** 每台逻辑机器人绑定一个执行后端，应用能看到当前是 SIM 还是 REAL，以及对应的设备身份。执行和反馈都归属该绑定。
- **让设备接入集中在边界。** 内核使用普通 Python 值与端口，适配层负责映射 ROS 消息、厂商接口、引擎坐标和单位。

首条验证路径选用单机械臂的离散末端位姿任务，覆盖目标预览、规划、执行反馈和停止。[项目范围与设计原则](docs/design/01-principles-and-scope.md)

## 技术架构

Bot3D 采用分层设计。Python 内核保存跨后端通用的领域语义，规划中的模块化单体协调会话、控制权和命令生命周期，外部适配器连接规划器、仿真器和设备。电机闭环由设备侧驱动和控制器处理。

```mermaid
flowchart TB
    Client["桌面应用 / XR（规划）"] -.-> Gateway["HTTP / WebSocket 网关（规划）"]
    Gateway -.-> Coordinator["应用协调（规划）"]
    Coordinator -.-> Domain["领域层 · 标识、几何、时间"]
    Coordinator -.-> RobotPorts["规划与执行端口（规划）"]
    Coordinator -.-> Registry["应用层 · 只读 Registry"]
    Coordinator -.-> ClockPort["应用层 · 单调时钟端口"]
    Registry --> ReadPort["只读后端端口"]
    ReadMock["只读 SIM mock"] --> ReadPort
    ReadPort --> Domain
    RobotAdapters["ROS 2 / MoveIt 2 / Gazebo（规划）"] -.-> RobotPorts
    RobotPorts -.-> Domain
    ClockAdapters["系统 / 人工时钟适配器"] --> ClockPort
    ClockPort --> Domain
```

实线连接现有模块，虚线表示规划中的依赖。各层通过领域值和端口交互，适配器依赖内核。首条集成路径优先考虑 ROS 2、MoveIt 2 和 Gazebo，XR 前端候选为 Unity + OpenXR。[完整架构、组件职责与数据路径](docs/design/02-system-architecture.md)

### 末端目标如何执行

1. **预览与提交。** 前端将输入转成指定坐标系下的工具位姿，经确认后提交任务，携带设备绑定和场景版本。
2. **检查与规划。** 协调层检查能力、控制权和上下文，规划器按当前模型与场景生成轨迹。
3. **下发与反馈。** 协调层复核执行前提并经唯一执行路径下发。后端报告实际状态，前端据此更新显示。

这是首条集成路径的设计流程。MoveIt 2 负责规划，执行适配器负责下发轨迹。[命令、状态与适配器契约](docs/design/03-contracts-and-adapters.md)

## 实现方式

当前仓库提供可从源码安装的 Python 内核。运行只用标准库，构建和测试的开发依赖分别由项目元数据和锁文件固定。

| 模块 | 当前实现 |
| --- | --- |
| `framework.domain` | 不可变标识、SI 值、四元数 / 刚体变换、位姿目标与单调时刻；纯能力组合、能力版本和只读身份 / 观测值。 |
| `framework.application` | `RobotRegistry` 提供注册、发现、描述和状态查询；`ReadOnlyBackend` 只提供读操作，`MonotonicClock` 提供带时钟域的读数。 |
| `framework.adapters` | 系统时钟、显式推进的人工时钟和静态只读 SIM mock，供独立测试与应用接入验证使用。 |

位姿目标以米表示位置，方向采用右手主动旋转与 `xyzw` 四元数。变换带源坐标系和目标坐标系，组合变换或转换目标时会检查坐标系是否匹配。数值构造拒绝非有限分量，单位换算在边界显式进行。[基础类型与坐标数学](docs/design/07-domain-types-and-geometry.md)

有效能力由规划、模型、坐标、策略和执行支持共同计算。只读 Registry 始终保留缺少执行支持的原因；重复查询保持能力版本，配置、模式或可用性语义变化时递增。机器人与设备身份分开，多个只读镜像可以共享一个设备。[只读 Registry 与能力模型](docs/design/08-readonly-registry-and-capabilities.md)

## 快速上手

使用 **CPython 3.12.11** 和 **uv 0.10.9**。分发名称为 `bot3d-kernel`，Python 导入名称为 `framework`。

```bash
git clone https://github.com/UyNewNas/Bot3D.git
cd Bot3D
uv sync --locked --no-editable --reinstall-package bot3d-kernel --link-mode copy --default-index https://pypi.org/simple
```

同步命令将构建出的包安装到项目虚拟环境。修改源码后，重新同步即可刷新安装包。[环境与构建细节](docs/design/06-python-foundation.md)

### 将末端目标从基座坐标系转换到世界坐标系

以下例子将工具目标设在基座 X 轴方向的 250 mm 处。基座相对世界坐标系绕 Z 轴旋转 90°，原点在世界坐标 `(1, 2, 3)` 米处。

```python
from math import sqrt

from framework.domain.geometry import Quaternion, RigidTransform
from framework.domain.targets import PoseGoal
from framework.domain.values import FrameId, RobotId, ToolId, Vector3, mm_to_m

base = FrameId("arm-fixture/base")
world = FrameId("cell/world")
goal = PoseGoal(
    robot_id=RobotId("arm-fixture"),
    frame_id=base,
    tool_id=ToolId("tool0"),
    position_m=Vector3(mm_to_m(250), 0, 0),
    orientation_xyzw=Quaternion(0, 0, 0, 1),
)

sqrt_half = sqrt(0.5)
world_from_base = RigidTransform(
    target_frame=world,
    source_frame=base,
    translation_m=Vector3(1, 2, 3),
    rotation=Quaternion(0, 0, sqrt_half, sqrt_half),
)

world_goal = goal.transformed(world_from_base)
x, y, z = world_goal.position_m.as_tuple()
print(f"{world_goal.frame_id.value}: ({x:.2f}, {y:.2f}, {z:.2f}) m")
# cell/world: (1.00, 2.25, 3.00) m
```

将示例保存为 `pose_example.py`，在仓库根目录运行 `uv run --no-sync python -I pose_example.py`。转换会更新目标的位置、方向和坐标系，保留机器人与工具标识。

### 发现只读模拟机器人

下面注册一个静态 SIM 样例，读取设备身份、能力和未知反馈。所有输入都是人工 fixture，运行时只调用读接口。

```python
from framework.adapters.mock_robot import ReadOnlyMockBackend
from framework.application.registry import RobotRegistry
from framework.domain.capabilities import CapabilityInputs
from framework.domain.discovery import (
    BackendDescription, BackendIdentity, BackendKind, BackendState,
    MotionState, ReadOnlyObservation,
)
from framework.domain.values import DeviceId, RobotId

identity = BackendIdentity(
    DeviceId("mock-device-a"), "mock-backend-a", BackendKind.SIM, "fixture-epoch-a",
)
inputs = CapabilityInputs(
    planning=True, model=True, frames=True, policy=True, execution=False,
    configuration_revision="fixture-config-1", mode=None,
)
backend = ReadOnlyMockBackend(
    BackendDescription(identity, "Fixture arm", inputs),
    BackendState(identity, ReadOnlyObservation(None, MotionState.UNKNOWN, None, None)),
)
registry = RobotRegistry()
robot = RobotId("arm-fixture")
description = registry.register(robot, backend)
state = registry.read_state(robot)

print(description.binding.backend.device_id.value)  # mock-device-a
print(description.capabilities.pose_goal.available)  # False
print(state.observation.motion_state.value)  # UNKNOWN
```

保存为 `readonly_example.py` 后，运行 `uv run --no-sync python -I readonly_example.py`。未知关节数据、控制模式和急停观测保留为 `None`；只读对象没有运动、停止或仿真控制方法。

### 运行测试

```bash
uv run --no-sync python -I -m pytest
uv run --no-sync python -I tools/check_import_boundaries.py
```

测试在隔离解释器中检查已安装的内核，覆盖标识、坐标数学、时钟域、能力组合 / 版本、身份一致性和只读约束。依赖检查约束核心包的导入边界。

## 开发路线

当前已提供内核基础、能力组合、只读绑定与模拟状态查询。接下来进入控制租约、状态投影、命令记录和 mock 协调链的实现，再验证执行、停止与恢复。

| 阶段 | 计划验证的能力 |
| --- | --- |
| Python 内核与 mock | 用可控时钟和模拟后端验证发现、控制租约、命令生命周期、停止与恢复。 |
| ROS 2 与 Gazebo | 用 MoveIt 2 规划、单一路径执行轨迹，读取仿真反馈并验证停止。 |
| XR 与仿真 | 通过 HTTP / WebSocket 接入桌面与 Unity + OpenXR，复用目标契约，展示预览、计划和反馈。 |
| 真机与第二后端 | 按设备准入流程验证同一任务在仿真与真机中的表现，并检查迁移到第二后端时的适配范围。 |

[当前迭代](docs/project/iterations/I01-M1-foundation.md) · [开发台账](docs/project/backlog.md) · [实施与验证路线](docs/design/04-delivery-and-validation.md)

## 文档导航

| 想了解 | 从这里开始 |
| --- | --- |
| 项目边界和技术选型 | [设计原则](docs/design/01-principles-and-scope.md) · [技术调研](docs/research/technology-survey.md) |
| 开发应用或适配器 | [领域契约](docs/design/03-contracts-and-adapters.md) · [坐标数学](docs/design/07-domain-types-and-geometry.md) |
| 命令协调、停止和恢复的设计 | [运行时协调](docs/design/05-runtime-coordination.md) |
| 各迭代的测试与交付进度 | [项目跟踪](docs/project/README.md) |
