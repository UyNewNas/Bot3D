# AR-0008：基础类型与坐标数学启动

| 日期 | 范围 | 环境 | 技术结果 | 产品验收 |
| --- | --- | --- | --- | --- |
| 2026-11-23 | I01 · DEV-M1-03 · T28/values、basis、quaternion | Linux x86_64、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | FAIL：实现前 T28 与旧 wheel 均未提供所需 API | PENDING |

## 开始条件

基线为 GitHub 提交 `319fed05a2d319bc6dc1865963670585fdc27cf9`，加 [AR-0007](AR-0007-foundation-boundary-recheck.md) 已完成、尚未提交的 DEV-M1-02 修正。已重新核对远端没有后续提交或 PR。执行角色为开发助手及受限代码子任务执行者；需求与数学样例由独立助手核对；现实验收角色未指定。

本轮继续用户指定的 DEV-M1-03。按[基础类型设计](../../design/07-domain-types-and-geometry.md)实现普通领域值、显式单位换算、四元数、带方向帧标签的数学变换及带工具目标，固定 I01 的三个 T28 切片。不实现 DEV-M1-04 或控制链。后续用户追加要求：将 README 改为项目主页，并与本轮代码一同提交。

## 执行计划

1. 保留已有工作树快照与哈希，复跑原 82 项测试作为开始基线。
2. 新增独立预期测试并记录实现前的 RED 输出；无实现不得标 PASS。
3. 实现并在非编辑安装上验证，运行依赖边界和独立 wheel 消费者。
4. 失败保留本记录，修复成功后另建下一 AR；据实际结果更新台账。

## 实际执行

开始基线在锁定环境、非编辑安装及隔离解释器下运行全量 pytest：82 passed，退出 0。初始三个 T28 切片为 NOT_RUN。

在写入三个领域模块之前，先增加 T28 测试、marker 和独立安装探测。测试以显式断言报告 API 缺失，保持正常收集，不用 skip 掩盖实现缺口：

| 命令 / 检查 | 退出码 | 实际结果 |
| --- | --- | --- |
| uv run --no-sync python -I -m pytest | 0 | 新增 T28 测试前的基线：82 passed |
| uv run --no-sync python -I -m pytest -m 't28_values or t28_basis or t28_quaternion' --tb=line | 1 | 84 failed、82 deselected；四个测试文件正常收集，失败为已安装包缺少 values / geometry / targets |
| 同一 T28 命令，增加大有限向量的四分之一周旋转反例后 | 1 | 85 failed、82 deselected；仍在三个产品模块写入之前执行，无收集错误或跳过 |
| uv run --no-sync python -I tools/check_wheel_install.py | 1 | 新探测读取已有旧 wheel；空消费者无法导入 framework.domain.geometry，明确失败 |

首次 84 项按 T28/values 45 项、T28/basis 18 项、T28/quaternion 21 项划分；第二次将四元数切片补至 22 项。期望数字按 I01 与独立数学推导固定，包括非交换组合、逆变换、范数两端与相邻浮点值；实现后的结果另记 [AR-0009](AR-0009-domain-foundation-recheck.md)，两次 FAIL 均保留。第二次运行误用了首次日志路径，首次完整原始日志未保留，只能追溯原工具输出中的退出码、断言和结果摘要；第二次完整原始日志及旧 wheel 失败日志已分别留存，没有重建或冒充首次原始输出。

文档编写中的一次中间检查指出计划引用的下一次记录尚未建档。随后按验收模板建立 [AR-0009](AR-0009-domain-foundation-recheck.md) 的 NOT_RUN 占位记录及索引；它在实际执行前不作为通过证据。

## 实现缺口与复验

DEF-0003：DEV-M1-03 计划内基础 API 尚未实现。期望值对象、四元数、变换与目标能够从非编辑安装包和独立 wheel 使用，实际三个模块缺失，阻止本工作包交付。此为测试先行阶段的预期缺口，原有 82 项测试开始基线通过；由 DEV-M1-03 实现并在 AR-0009 复验，不回写本次失败。

## 验收边界

只验证 AC-002 的标识类型、AC-004 的基础目标 / 数值、AC-016 的纯数学切片。工具配置 / 场景 / 碰撞 / 速度与容差策略、变换来源 / 时间 / 标定有效性和真实反馈 UNKNOWN 投影仍待后续任务。I01 保持 ACTIVE，产品验收 PENDING。
