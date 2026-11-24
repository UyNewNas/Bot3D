# AR-0017：控制权首轮复验与时钟故障结果复核

| 日期 | 范围 | 环境 | 技术结果 | 产品验收 |
| --- | --- | --- | --- | --- |
| 2026-11-23 | I02 · DEV-M1-05 · 控制权与工程回归 | Linux x86_64、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | 首轮测试 / 安装 PASS；独立复核 FAIL | PENDING |

## 范围

基线为 ffae464；首轮代码候选为 `8c258a14f66215f8cd86889ea44a1fc7b89091e0`，文档为同轮工作树。开始条件与实现前证据见 [AR-0016](AR-0016-control-authority-start.md)。接口与行为由[控制权设计](../../design/09-control-authority-and-activation.md)约束。开发助手实现，独立助手复核，产品验收角色未指定。

## 首轮实际执行

| 检查 | 状态 | 实际结果 |
| --- | --- | --- |
| 非编辑安装与全量 pytest | PASS | 377 passed；原 303 项与新增 74 项，退出 0 |
| T01/leases | PASS | 11 passed：设备单写、会话、租约身份及有界线程竞争 |
| T07/authority-loss | PASS | 11 passed：释放、到期、会话失权、原绑定效果与聚合执行标记 |
| T30/activation | PASS | 35 passed：前置策略、显式确认、健康运动和上下文退役 |
| T42/lease-clock | PASS | 17 passed：精确到期、保护钟隔离及故障撤权 |
| 独立包 / 导入子进程 | PASS | 52 passed；保留三种消费环境各自的安装 / 边界断言，共用 API 演练片段 |
| 依赖边界 | PASS | 13 核心模块，检查器 32 项自测 |
| 安装与源码一致 | PASS | 16 个 framework Python 文件逐字节一致 |
| sdist→wheel / 空消费者 | PASS | 离线构建，仓库外空环境仅安装本分发；时间、几何、只读查询、租约 / 激活 / 到期全部通过 |
| 工件内容 | PASS | sdist 和 wheel 的 16 个 Python 文件与源码一致，README 与 UTF-8 元数据一致，运行依赖为零 |
| 文档示例 | PASS | 两个 README 例子和控制权例子均在仓库外以隔离解释器运行，退出 0、无 stderr、输出相符 |
| 锁 / DOC 工具 | PASS | 锁检查通过；文档工具 43 自测，运行时工具 25 自测与 44 设计场景；均不代表产品 T31 / T34 通过 |

日志按 `AR-0017/task-1-*`、`preflight-*` 和 `review-*` 保留。临时工件核对脚本首次使用邮件字节解析器读取中文正文时断言失败；`artifact-diagnostic.json` 保留了替换字符与原始 UTF-8 正文字节相符的诊断。改为显式 UTF-8 解码后核对通过，没有修改包或 README 来适应读取错误。

## 独立复核失败

DEF-0009：`AuthorityResult` 的公开构造器允许携带另一绑定的 CLOCK_FAULT 事件，同时当前快照仍有 owner、为 ARMED 且 clock_faulted=False。独立安装包反例输出为 `accepted True arming ARMED clock_faulted False loss CLOCK_FAULT`。这违反管理器全局时钟故障应锁定并撤权的结果语义。

正常管理器路径会先设置时钟故障，再撤销所有租约，未复现运行转换漏撤权。缺口在公开普通值的跨字段约束：无论同绑定还是跨绑定，只要结果含 CLOCK_FAULT，就必须要求快照 clock_faulted=True；已有快照约束继而禁止 owner / ARMED。需补构造器拒绝测试，并保留合法 FORBIDDEN + CLOCK_FAULT 效果交接。

该次失败保留，不把此前 377 项通过当成缺陷已关闭。修正后的 RED / GREEN、独立复核与全量集成证据记入 [AR-0018](AR-0018-control-authority-invariant-final.md)。DEV-M1-05 在本记录时仍 DOING，I02 ACTIVE，产品验收 PENDING。
