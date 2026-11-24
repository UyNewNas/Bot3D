# 虚实机器人框架文档

- 更新日期：2026-11-24
- 当前阶段：v0.1 设计与需求—开发—测试—验收跟踪基线
- 当前交付：可安装 Python 内核、坐标数学、能力组合 / 只读 Registry、控制租约与显式激活、命令摘要与内存 Journal，以及状态投影、时间质量和静止证据；本轮启动见 [AR-0023](project/records/AR-0023-state-projection-start.md)，最终验证见 [AR-0024](project/records/AR-0024-state-projection-final.md)

## 文档索引与阅读顺序

| 顺序 | 文档 | 解决的问题 |
| --- | --- | --- |
| 1 | [软件思想与范围](design/01-principles-and-scope.md) | 框架是什么、什么可以迁移、首版做什么 / 不做什么 |
| 2 | [软件技术架构（含总览图）](design/02-system-architecture.md) | 架构图、分层、模块、执行链、技术候选、资产、部署与失效处理 |
| 3 | [领域契约与适配器](design/03-contracts-and-adapters.md) | 能力、命令、状态、坐标、时钟、控制权与适配要求 |
| 4 | [实施路线与验证](design/04-delivery-and-validation.md) | 从 mock 到仿真 / XR / 真机的阶段、测试与迁移证据 |
| 专题 | [运行时协调详细设计](design/05-runtime-coordination.md) | 状态转换、最终裁决、停止闭合、崩溃对账与设计级场景 |
| 专题 | [Python 工程与时钟基线](design/06-python-foundation.md) | 版本 / 依赖锁、领域值 / 端口及安装、测试步骤 |
| 专题 | [基础类型、目标与坐标数学](design/07-domain-types-and-geometry.md) | 标识、SI 单位、有限数、四元数、刚体变换及独立数学基准 |
| 专题 | [只读 Registry 与有效能力](design/08-readonly-registry-and-capabilities.md) | 机器人 / 设备身份、只读发现、能力组合与版本、未知观测 |
| 专题 | [控制权与显式激活](design/09-control-authority-and-activation.md) | 会话租约、单写、前置策略、到期与失权、上下文退役和未结执行门禁 |
| 专题 | [命令摘要与内存 Journal](design/10-command-journal-and-idempotency.md) | 规范化执行语义、同键重试 / 冲突、原绑定、追加事实与故障 / 保留边界 |
| 专题 | [状态投影、时间质量与静止证据](design/11-state-projection.md) | 目标 / 计划 / 实际分离、双年龄、时钟映射、反馈顺序、FK 来源与静止窗口 |
| 5 | [项目闭环跟踪](project/README.md) | 需求 / AC、开发台账、测试计划、闸门、迭代与实际记录 |
| 参考 | [技术资料调研](research/technology-survey.md) | 机器人 SDK / 协议、中间件、仿真、VR / XR 和官方资料 |

按角色阅读：应用 / XR 开发者先读 1、3；框架与适配器开发者读 1—4；硬件选型先查调研与适配器交付卡；开发、测试和验收从 5 进入。

## 当前设计基线

- 统一能力、任务和状态语义，不统一所有机器人底层控制协议。
- 领域内核不依赖 ROS、引擎或厂商 SDK；首条机器人路径优先集成 ROS 2。
- 首个仿真候选 Gazebo，首个 XR 候选 Unity + OpenXR；具体版本组合需验证。
- 非实时协调服务采用模块化单体候选，设备闭环保留在驱动 / 控制器侧。
- 每台逻辑机器人一个有效运动控制者；SIM / REAL 和真实设备身份始终显式。
- 先做固定基座单机械臂的离散目标闭环，再验证同机器人虚实切换和第二后端；不是限定框架只能支持机械臂。
- 自动场景重建、跨形态策略迁移、连续遥操作和力反馈不属于首条实现路径。

这些是可修订的工作假设，不是用户已最终确认的采购 / 部署方案。

## 怎样理解文档中的结论

1. **调研事实**：来自所列官方资料；滚动文档和仓库分支会变化，采用前须固定版本、许可和设备范围。
2. **设计决策**：本项目拟采用的分层与约束，尚未由实现和运行数据证明。
3. **验证结果**：需要测试记录或现场证据。目前没有机器人、仿真器或头显联调结果，JSON 示例也不是设备实测数据。

上层代码可复用不意味着旧命令可重放到真机；模型可导入不意味着物理参数正确；软件 STOP 不等于实体急停。现实设备启用必须经过另行授权、身份 / 标定核验和本地保护验收。

## 下一步

[I01：内核基础与只读发现](project/iterations/I01-M1-foundation.md) 为 IN_ACCEPTANCE，十个技术切片已通过，产品验收 PENDING。[I02：控制权、状态投影与 mock 执行 / 停止](project/iterations/I02-M1-control-loop.md) 为 ACTIVE，DEV-M1-05 / 06 / 12 已完成；下一工作包为 DEV-M1-07 可控规划 / 执行 mock。本轮记录见[项目入口](project/README.md)。状态投影提供 T06 / T10 / T42 的状态证据切片，完整执行 / STOP 联调与 T27 完成判断仍待实现，持久化 / 恢复留 I03。
