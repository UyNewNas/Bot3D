# AR-0009：基础类型实现与独立复核

| 日期 | 范围 | 环境 | 技术结果 | 产品验收 |
| --- | --- | --- | --- | --- |
| 2026-11-23 | I01 · DEV-M1-03 · T28 与工程回归 | Linux x86_64、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | FAIL：独立复核发现可表示结果的中间求和溢出 | PENDING |

## 版本与范围

基线提交 `319fed05a2d319bc6dc1865963670585fdc27cf9` 加本轮工作树，保留 [AR-0007](AR-0007-foundation-boundary-recheck.md) 已验证的工程修正。开始条件及实现前证据见 [AR-0008](AR-0008-domain-foundation-start.md)。本记录保留首轮实现结果和独立复核发现，修正结果另记 [AR-0010](AR-0010-domain-foundation-final.md)。

按[基础类型设计](../../design/07-domain-types-and-geometry.md)复验不可变标识、SI 换算、有限值、四元数、带帧方向的刚体变换和带工具目标；对已安装包、依赖边界、文档和独立 wheel 消费者回归。用户追加要求的 README 项目主页重写与本轮代码共同提交。

执行角色为开发助手，代码与数学核对由独立助手参与，现实验收角色未指定。

## 实际执行

| 检查 | 退出码 / 结果 | 实际证据 |
| --- | --- | --- |
| 非编辑同步安装 | 0 / PASS | uv sync --locked --no-editable --reinstall-package bot3d-kernel --link-mode copy --default-index https://pypi.org/simple |
| 全量 pytest | 0 / PASS | 167 passed；原 82 项及新增 T28 的 85 项 |
| T28 独立切片 | 均为 0 / PASS | values 45、basis 18、quaternion 22 passed |
| 核心依赖检查 | 均为 0 / PASS | 8 个核心模块扫描，32 项检查器自测 |
| sdist→wheel 与空消费者 | 均为 0 / PASS | 构建后离线安装，仅存在 bot3d-kernel 分发；新目标 / 变换探测及原时钟探测通过 |
| README 示例 | 0 / PASS | 在仓库外使用已安装包，输出 cell/world: (1.00, 2.25, 3.00) m |
| 独立数学复核 | 1 / FAIL | 下列沿旋转轴的大有限向量应保持不变，却触发中间求和溢出；开发助手独立复现 |

复核输入及手算预期：四元数的向量部为 (0.25, 0.25, 0.25)，旋转轴平行于 (1, 1, 1)。沿该轴的向量应保持不变，三个输出分量均可以有限 float 表示。

```python
from math import sqrt
from sys import float_info
from framework.domain.geometry import Quaternion
from framework.domain.values import Vector3

q = Quaternion(0.25, 0.25, 0.25, sqrt(13) / 4)
c = 0.875 * float_info.max
q.rotate(Vector3(c, c, c))  # 预期分量均为 c
```

实际结果为 ValueError，原因是 math.fsum 在一行中先累加同号项时产生 intermediate overflow。该行后续的反号项会抵消超出部分；这是单次旋转内部可避免的溢出，并非最终结果超出表示范围。不能把初始 167 项测试通过视为此边界已通过。

## 缺陷与修正要求

DEF-0003 的缺失 API 已由首轮实现补齐。DEF-0004：旋转数值运算误拒可表示的有限结果，严重性为阻止 DEV-M1-03 交付。独立复核定位到中间求和溢出；修正期间还发现同类问题的另一原因：旋转矩阵系数舍入超过 1，使有限最大值的乘积溢出。

第二个独立输入为 a=0.001、b=sqrt(0.5-a*a)、q=(a,a,b,b)，作用于 (float_info.max,0,0)。按 xyzw 公式，第一列为 (0,1,0)，输出应为 (0,float_info.max,0)；原计算的中间系数却比 1 大一个浮点间距，最终报错。两个反例分别保留实现前的失败输出。

需新增轴不变性与系数边界回归，再修正数值求和和系数计算；保留真正无法表示的输出报错、常规精度与全部 T28 / T26 回归。修正不改变公共 API 或 I01 固定基准，最终在 AR-0010 复验，本次 FAIL 不回写。

## 验收边界

三个 T28 切片为 UNIT。这里只覆盖 AC-002 的标识、AC-004 的基础目标 / 数值和 AC-016 的坐标数学；配置策略、变换来源及标定有效性、设备运行与 XR 跟踪另由后续任务验证。I01 继续 ACTIVE，产品验收 PENDING。
