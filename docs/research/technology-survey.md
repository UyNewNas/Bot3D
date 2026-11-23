# 虚实机器人可迁移框架：技术资料调研

- 归档日期：2026-11-19
- 状态：资料整理，尚未进行硬件、仿真器或头显联调
- 范围：机器人接口、中间件、仿真、VR/XR、模型与场景互通
- 来源：本次调研收集的官方文档、标准组织文档和厂商维护仓库

本文是选型资料，不是已验证的兼容性清单。文档中的 latest、默认分支和支持范围可能变化；实现时必须固定实际版本、提交号、固件和授权信息。工程建议见[设计思想](../design/01-principles-and-scope.md)，方案见[技术架构](../design/02-system-architecture.md)。

## 1. 可迁移目标

| 目标 | 可复用内容 | 不能自动成立的事情 |
| --- | --- | --- |
| 同一机器人，仿真与真机切换 | 任务接口、状态模型、部分规划配置 | 动力学、延迟、控制模式和安全行为完全一致 |
| 不同机器人之间迁移 | 能力语义、任务、约束、部分技能 | 相同关节角、轨迹或力矩可直接复用 |
| 不同仿真器之间迁移 | 领域接口、资产源、测试场景 | 导入后物理语义和数值行为完全一致 |
| 不同 XR 设备之间迁移 | OpenXR 基础交互、应用逻辑 | 所有手势、眼动和透视扩展跨设备可用 |
| 现实场景与虚拟场景连接 | 标定、对象标识、机器人与场景状态 | 视觉重建结果天然具备碰撞和物理参数 |

Real2Sim、Sim2Real、数字孪生和遥操作应分别设计和验收。

## 2. 代表性硬件与接口

| 类别 / 代表 | 接口与配套软件 | 限制与核实重点 | 官方资料 |
| --- | --- | --- | --- |
| 协作机械臂：UR | ROS 2 Driver、C++ 库、RTDE、URScript | RTDE 数据交换不等于完整运动控制；还涉及驱动和机器人端程序。频率依控制器和版本而定 | [驱动](https://github.com/UniversalRobots/Universal_Robots_ROS2_Driver)、[RTDE](https://docs.universal-robots.com/tutorials/communication-protocol-tutorials/rtde-guide.html) |
| 研究机械臂：Franka | libfranka、FCI、franka_ros2 | 核对代际、FCI、版本、选件、实时主机要求 | [开发资源](https://franka.de/develop)、[ROS 2](https://github.com/frankarobotics/franka_ros2) |
| 协作机械臂：xArm | C++ / Python SDK、xarm_ros2、MoveIt、Gazebo | ROS 包使用 C++ SDK 子模块；Python SDK 是另一条接口。核对分支和固件 | [ROS 2](https://github.com/xArm-Developer/xarm_ros2)、[Python](https://github.com/xArm-Developer/xArm-Python-SDK/blob/master/README.md) |
| 工业机械臂：ABB | RobotStudio、RAPID、RWS、EGM | RWS 偏控制器数据访问，EGM 是外部运动引导；按控制器、RobotWare 和选件复核手册，不沿用未确认版本的 PDF 直链 | [RWS](https://developercenter.robotstudio.com/api/rwsApi/index.html)、[官方资料库](https://library.abb.com/) |
| 工业机械臂：KUKA | WorkVisual、RSI | 核对控制器、版本和授权；不能把 RSI、FRI 等不同接口混同 | [RSI](https://www.kuka.com/en-ca/products/robotics-systems/software/hub-technologies/kuka_robotsensorinterface) |
| 四足 / 人形：Unitree | unitree_sdk2、CycloneDDS、unitree_ros2 | Go2、B2、G1、H1 等消息和程序因型号而异；能读状态不等于有低层控制权限 | [ROS 2](https://github.com/unitreerobotics/unitree_ros2) |
| 商用四足：Spot | SDK、gRPC / Protobuf、状态与运动服务 | 涉及认证、时间同步、Lease 和 E-stop；高层命令不等于任意电机控制 | [开发文档](https://dev.bostondynamics.com/)、[服务](https://dev.bostondynamics.com/docs/concepts/robot_services.html) |
| 移动机器人：Clearpath | ROS 2、速度命令、里程计、传感器消息 | 注意命名空间和发行版；部分 Humble 接口使用 Twist，Jazzy 使用 TwistStamped | [API](https://docs.clearpathrobotics.com/docs/ros/api/platform_api/)、[Humble](https://docs.clearpathrobotics.com/docs/ros2humble/ros/api/platform_api/) |
| 无人机：PX4 | MAVLink、MAVSDK、ROS 2 通信 | 保留飞控模式、约束和失联机制；任务 SDK 不是电机闭环 | [MAVSDK](https://docs.px4.io/main/en/robotics/mavsdk)、[ROS 2](https://docs.px4.io/main/en/ros/ros2_comm) |
| 执行器：DYNAMIXEL | SDK、Protocol 1.0 / 2.0、型号相关的 TTL 或 RS485 | 电气接口、指令包协议、控制表和串口参数需分别核对 | [SDK](https://emanual.robotis.com/docs/en/software/dynamixel/dynamixel_sdk/overview/)、[Protocol 2.0](https://docs.robotis.com/docs/dxl/protocol/protocol2/) |

DJI 等商业无人机还需区分 SDK 授权边界：[Payload SDK](https://developer.dji.com/doc/payload-sdk-api-reference/en/) 面向载荷，不等于任意飞控访问。

### 硬件接入卡

每种硬件必须记录：型号与固件；SDK 版本和许可证；可读状态；可写控制；坐标、关节顺序、单位、工具、限位；控制权、超时、失联、停止反馈与实体急停；OS / ROS / 网络 / 仿真模型及实测组合。“有 SDK”不说明以上能力全部开放。

## 3. 中间件与协议层次

| 层次 | 技术 | 用途与边界 |
| --- | --- | --- |
| 机器人组件协作 | ROS 2 消息、服务、Action | 连接驱动、规划、感知和应用，不自动保证端到端硬实时 |
| 控制器 / 硬件抽象 | ros2_control | 硬件插件、读 / 更新 / 写周期；接口兼容不代表动力学自动一致 |
| 厂商接口 | FCI、EGM、RSI、RTDE、SDK | 功能层次不同，分别核对状态、运动能力和实时要求 |
| 总线与链路 | EtherCAT、CAN / CAN FD、CANopen、串口协议 | CAN、CANopen、RS485 并非同一层次的可替换名词 |
| 前端桥接 | rosbridge、WebSocket、ROS-TCP | 用于网页、Unity 或跨语言应用，不承担普通网络上的电机闭环 |
| 工业信息 | OPC UA Robotics | Part 1 侧重资产、配置、运行状态等垂直集成，不是统一实时运动接口 |
| 车队管理 | VDA 5050 | MQTT / JSON 的车队任务交互，不是关节控制协议 |

资料：[ros2_control](https://control.ros.org/jazzy/doc/getting_started/getting_started.html)、[硬件组件](https://control.ros.org/jazzy/doc/ros2_control/hardware_interface/doc/hardware_components_userdoc.html)、[rosbridge](https://github.com/RobotWebTools/rosbridge_suite/blob/ros2/README.md)、[协议](https://github.com/RobotWebTools/rosbridge_suite/blob/ros2/ROSBRIDGE_PROTOCOL.md)、[OPC UA Robotics 范围](https://reference.opcfoundation.org/specs/OPC-40010-1/1)、[VDA 5050](https://github.com/VDA5050/VDA5050)。

## 4. 仿真软件

| 软件 | 适用方向 | 接口与注意事项 | 官方资料 |
| --- | --- | --- | --- |
| Gazebo | ROS 系统联调、传感器、导航和控制验证 | ros_gz、gz_ros2_control；Jazzy + Harmonic 是有文档的组合，不表示始终最新 | [ROS 配套](https://gazebosim.org/docs/harmonic/ros_installation/)、[控制集成](https://control.ros.org/jazzy/doc/gz_ros2_control/doc/index.html) |
| Isaac Sim | 视觉 / 传感器仿真、合成数据、数字孪生 | OpenUSD、ROS 2、多种资产导入；先核对 GPU、驱动、系统和授权，不给出未经核实的最低配置 | [文档](https://docs.isaacsim.omniverse.nvidia.com/latest/) |
| MuJoCo | 动力学、接触、控制和机器人学习 | MJCF、URDF 加载、C API；不是完整 VR 内容平台 | [概览](https://mujoco.readthedocs.io/en/stable/overview.html)、[建模](https://mujoco.readthedocs.io/en/stable/modeling.html) |
| Webots | 通用原型、教学和系统验证 | 跨平台，提供 ROS 2 集成 | [项目](https://github.com/cyberbotics/webots)、[ROS 2](https://github.com/cyberbotics/webots_ros2) |
| CoppeliaSim | 机械臂、机构、工作站、脚本仿真 | ZeroMQ API 和 simROS2 是不同路径；支持步进协同，旧 Remote API 已弃用 | [ZeroMQ](https://manual.coppeliarobotics.com/en/zmqRemoteApiOverview.htm)、[ROS 2](https://manual.coppeliarobotics.com/en/ros2Interface.htm) |

Isaac Sim 是仿真平台，Isaac Lab 面向机器人学习工作流，Isaac ROS 是机器人软件组件生态，三者不能混称。

Gazebo Classic 于 2025-01-29 结束生命周期，新项目不应混用 Classic 与现代 Gazebo 教程。资料：[Classic](https://classic.gazebosim.org/)、[迁移](https://gazebosim.org/docs/harmonic/gazebo_classic_migration/)。

## 5. VR / XR 软件

| 技术 | 类型 | 用途与边界 | 官方资料 |
| --- | --- | --- | --- |
| OpenXR | XR API 标准 | 统一基础设备与动作，不是引擎或机器人框架；扩展依赖设备和运行时 | [Khronos](https://www.khronos.org/openxr/)、[规范](https://registry.khronos.org/OpenXR/) |
| Unity | 交互引擎 | OpenXR Plugin、Input System、XR Interaction Toolkit 用于选择、抓取和空间 UI | [XR 包](https://docs.unity3d.com/cn/2022.3/Manual/xr-support-packages.html)、[交互工具](https://docs.unity3d.com/ja/current/Manual/com.unity.xr.interaction.toolkit.html) |
| Unreal Engine | 交互 / 渲染引擎 | OpenXR；机器人通信仍需桥接，不能视为内置通用机器人驱动 | [OpenXR](https://dev.epicgames.com/documentation/unreal-engine/openxr-prerequisites-in-unreal-engine) |
| Godot | 开源交互引擎 | OpenXR、XR Tools；本次资料未确认完整现成的机器人集成方案 | [XR](https://docs.godotengine.org/en/stable/tutorials/xr/setting_up_xr.html)、[XR Tools](https://docs.godotengine.org/en/4.4/tutorials/xr/introducing_xr_tools.html) |
| SteamVR / 厂商 Runtime | 运行时 | 在应用与具体设备间运行接入，不同于引擎和 API 标准 | [Steamworks 检索入口](https://partner.steamgames.com/doc?q=steam+vr+openxr&start=1) |

### Unity 与 ROS 的桥接

- [ROS-TCP-Connector](https://github.com/Unity-Technologies/ROS-TCP-Connector)：Unity 消息收发、C# 消息生成、可视化和坐标转换辅助。
- [ROS-TCP-Endpoint](https://github.com/Unity-Technologies/ROS-TCP-Endpoint)：ROS 侧端点。
- README 的兼容标识含较早 ROS 发行版。不证明其停止维护，也不证明与当前 Unity / ROS 2 即插即用。
- 采用前独立验证版本、序列化、坐标、断线恢复和吞吐。

## 6. 模型、场景与规划

| 技术 | 主要职责 | 注意事项 / 资料 |
| --- | --- | --- |
| URDF / Xacro | 机器人结构、关节及配置源 | 不是完整场景与执行器行为统一规范；ros2_control 配置也可嵌入 URDF |
| SDF | 仿真模型、世界、传感器、物理参数 | [SDFormat](https://sdformat.org/) |
| OpenUSD / UsdPhysics | 场景组织、资产组合、刚体、碰撞与关节 | 标准 schema 与物理引擎扩展分别管理；[UsdPhysics](https://openusd.org/release/api/usd_physics_page_front.html) |
| MJCF | MuJoCo 模型配置 | [建模](https://mujoco.readthedocs.io/en/stable/modeling.html) |
| MoveIt 2 | 运动规划、运动学、规划场景与执行集成 | [文档](https://moveit.picknik.ai/main/index.html)；碰撞检查不代替实体安全系统 |

视觉资产不能自动提供正确的碰撞体、惯量、摩擦、执行器模型和传感器标定。跨格式转换应记录损失、默认值和补充项，不承诺无损互通。

## 7. 初步建议与未决项

推荐方向，不是已完成实现：

1. 用能力和任务语义组织接口，ROS 2 作为首个集成运行时。
2. 先验证同一机器人虚实切换，再验证跨机器人任务复用。
3. 工程仿真优先考察 Gazebo；视觉数据需求明确后再评估 Isaac Sim。
4. XR 优先考察 Unity + OpenXR，桥接独立选型和验证。
5. 首版只维护一条完整执行链，不同时引入多个引擎和仿真器。

尚未完成或不能直接推断：

- 未选真实机器人、头显、GPU、部署环境、控制频率或预算。
- 未验证硬件控制权限、失联停车、实体急停和许可条件。
- 未验证当前 Unity、ROS-TCP、ROS 2 的具体兼容组合。
- 未验证不同物理引擎的参数等价性。
- 未得到覆盖所有 KUKA 产品的 FRI / RSI 适用矩阵。
- Nav2 可作为后续移动导航候选；不包含其具体版本与驱动联调结论。
- ROS 中间件说明页、REP 103 原站访问曾受限；失败抓取不算来源验证。设计文档中的坐标规则是项目拟采用的显式契约。

## 8. 实现阶段的来源管理

每个采用的组件应保存：官方来源、版本 / 提交号、许可证、适用硬件、实测环境、测试日期、已知缺陷和退出方案。滚动文档应补固定版本链接。在完成测试前，不写“已兼容”“已验证安全”或“已实现 Sim2Real”。
