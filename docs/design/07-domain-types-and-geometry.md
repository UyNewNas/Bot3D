# 基础类型、目标与坐标数学

- 日期：2026-11-23
- 工作包：DEV-M1-03；[I01](../project/iterations/I01-M1-foundation.md) 的 T28/values、T28/basis、T28/quaternion
- 依据：[领域契约第 2、4、5 节](03-contracts-and-adapters.md)、[追踪矩阵](../project/requirements.md)
- 设计范围：不可变领域值和纯数学；实现与测试结果以当次 AR 为准。

## 1. 实现选择与边界

沿用 CPython 3.12.11、uv 0.10.9 与零运行第三方依赖。值对象与数学使用标准库 dataclasses / math；极端数值范围的旋转使用 fractions 精确运算，没有引入数值 SDK 或 ROS 消息。字符串和数组仅在显式构造边界接收，领域聚合使用具体值类型，避免把 robot、device、frame 或工具互相误传。

本轮新增 values、geometry、targets 三个领域模块。分层保持向内，不增加 Registry、控制器或执行端口。PoseGoal 是内部已校验的目标值，不改变现有命令信封中的 robot_id、context.tool_id 和 parameters.goal 的 JSON 位置。

## 2. 标识、有限数与单位

- RobotId、DeviceId、FrameId、ToolId 均为冻结、带 slots 的值对象，字段 value 为非空字符串；拒绝空白字符，不静默 strip 或改写身份。不同标识类型不相等，聚合字段拒绝错误的标识类型。
- FrameId 至少包含两个由 / 分隔的非空片段；不接受前后斜杠、重复斜杠及 . / .. 片段。允许 cell/world、arm-fixture/base 和更深层级；不要求 frame 前缀等于 robot，因为共享世界帧合法。
- 数值输入只接受内置 int / float，拒绝 bool、字符串、None、NaN、正负无穷与不能表示为有限 float 的整数。值保存为 float。位置、方向和中间结果不静默填零或截断。
- Vector3(x, y, z) 保存三个有限坐标；from_xyz 仅接收长度为 3 的 list / tuple，复制为不可变分量；as_tuple 返回 xyz 元组。Vector3 是数学向量，具体单位由 position_m / translation_m 字段或方向运算明确。
- mm_to_m、m_to_mm、deg_to_rad、rad_to_deg 是显式边界换算，输入与结果均检查有限性。领域目标位置使用 m，角度换算结果使用 rad；不根据数值大小猜测单位。

None 表示缺失的输入时不能构造目标或向量，不产生默认原点、单位姿态或“安全”状态。实际反馈的 UNKNOWN / 质量投影由后续开发任务实现。

## 3. 四元数

Quaternion(x, y, z, w) 使用右手主动旋转和 xyzw 顺序；from_xyzw 仅接收长度为 4 的 list / tuple，as_tuple 返回 xyzw 元组。对象冻结，输入必须有限。

使用 math.hypot 计算范数，拒绝零范数及不在闭区间 [1.0 - 1e-6, 1.0 + 1e-6] 内的输入。直接比较两个端点，避免 abs(norm - 1) 的减法舍入误拒下界。仅在已经通过容差检查后归一化，以免近单位输入在旋转中产生缩放；明显非单位输入不会自动修复。

- rotate(Vector3) 返回旋转后的向量，不引入平移。
- inverse() 返回逆旋转。
- compose(other) 表示 self * other，先应用 other，再应用 self。
- q 和 -q 的旋转等价；值对象的分量相等 / 哈希仍按原始符号区分，不以近似旋转相等代替结构相等。

所有计算结果需保持有限；发生数值溢出时显式报错，不输出无穷、NaN 或默认零。有限向量不因其欧氏长度可能溢出而在构造时被拒绝。

普通向量使用 binary64 与 math.fsum。任一分量的绝对值超过最大有限 float 的四分之一时，从已存储的四元数和向量分量构造精确 Fraction，按齐次旋转矩阵与精确范数平方求值；先检查结果范围，再转换成 float。这样极端范围不会因中间和、系数或乘积舍入误拒可表示结果，也不将真正越界的结果截断回最大值。复核反例与修正见 [AR-0009](../project/records/AR-0009-domain-foundation-recheck.md)、[AR-0010](../project/records/AR-0010-domain-foundation-final.md)及 [AR-0011](../project/records/AR-0011-domain-foundation-final.md)。

## 4. T_A_B 与带工具目标

RigidTransform(target_frame, source_frame, translation_m, rotation) 表示 T_A_B：source_frame 是 B，target_frame 是 A，点满足 p_A = R_A_B p_B + t_A_B。

- apply_point(Vector3) 旋转并平移；apply_direction(Vector3) 仅旋转。
- apply_orientation(Quaternion) 返回 rotation.compose(orientation)。
- inverse() 返回 T_B_A，平移为 -R_A_B 的逆作用于 t_A_B。
- compose(other) 实现 T_A_B.compose(T_B_C) = T_A_C。必须满足 self.source_frame == other.target_frame；错帧抛出 FrameMismatch（ValueError 的子类）。

PoseGoal(robot_id, frame_id, tool_id, position_m, orientation_xyzw) 的全部字段必填且具有上述具体类型。transformed(transform) 要求当前 frame 等于变换 source_frame，保留 robot 与 tool，返回目标帧中的新目标；原值保持不变。错误字段类型抛 TypeError，非法数值 / 尺寸 / 范数抛 ValueError，错帧运算抛 FrameMismatch。

这里的 RigidTransform 仅是带方向标签的数学值，不代表一个已经校验过来源、标定版本、时间或有效性的场景变换。那些元数据与运行时有效性属于 DEV-M1-13 / T43；工具配置、工作空间、碰撞、速度与容差策略属于后续应用验证。基础类型构造成功不授予执行资格。

## 5. 独立验收数据

使用 [I01 固定数据](../project/iterations/I01-M1-foundation.md)，浮点比较 abs=1e-9、rel=0，期望值不由被测函数产生。

| 切片 | 输入 | 手算预期 |
| --- | --- | --- |
| T28/values | arm-fixture、mock-device-a、cell/world、arm-fixture/base、tool0 | 类型与作用域正确；未知、空 ID、裸 frame、错维、非有限数拒绝 |
| T28/values | 1000 mm、1 m、180 deg、π rad | 1 m、1000 mm、π rad、180 deg |
| T28/basis | Rz(+π/2)，平移 (1,2,3) | B 原点→(1,2,3)，点 (1,0,0)→(1,3,3) |
| T28/basis | 相同变换的方向 x、y、z | (0,1,0)、(-1,0,0)、(0,0,1)；方向不加平移 |
| T28/basis | 上述变换的逆 | 逆平移 (-2,1,-3)；还原原点和 (1,0,0) |
| T28/quaternion | qx、qy 分别绕 x、y 正向旋转 π/2 | qx.compose(qy)=(0.5,0.5,0.5,0.5)，将 (x,y,z) 映到 (z,x,y)；反序映到 (y,-z,-x) |
| T28/basis | T_A_B=(Rx,(1,2,3))，T_B_C=(Ry,(4,5,6)) | 合成平移 (5,-4,8)，点 (1,2,3)→(8,-3,10)，逆平移 (4,-8,-5) |
| T28/quaternion | w 位于范数闭区间两端及 nextafter 内外相邻值 | 两端及内侧接受，外侧拒绝；零范数 / 明显非单位拒绝 |
| T28/quaternion | q、-q；容差内的 (0.50000025,)*4 | q/-q 旋转相同；容差内归一化后无缩放 |

三个 T28 切片只算 UNIT。G-I01 尚需 DEV-M1-04 的 T29 / T46；本轮不关闭产品闸门。
