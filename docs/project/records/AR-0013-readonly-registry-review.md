# AR-0013：只读 Registry 实现与边界复核

| 日期 | 范围 | 环境 | 技术结果 | 产品验收 |
| --- | --- | --- | --- | --- |
| 2026-11-23 | I01 · DEV-M1-04 · T29 / T46、工程与独立复核 | Linux x86_64、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | 基础回归 PASS；子类边界复核 FAIL | PENDING |

## 版本与范围

基线为 `b084218d82caa20e13d5e2ef3055f69046785547` 加本轮首次实现工作树。开始条件及实现前失败见 [AR-0012](AR-0012-readonly-registry-start.md)，接口与范围见[只读 Registry 设计](../../design/08-readonly-registry-and-capabilities.md)。执行角色为开发助手，独立助手参与代码与契约复核，现实验收角色未指定。

## 实际执行

| 检查 | 结果 |
| --- | --- |
| 非编辑安装、依赖锁 | PASS；固定版本安装与离线锁检查退出 0，uv.lock 未变化 |
| 首次 GREEN / 全量 | 106 passed、170 deselected；全量 276 passed |
| T29 / T46 独立切片 | compose 31、revision 15、discovery 34、readonly 26 全部通过 |
| T26 / T28 回归 | package 4、imports 48、ports-clock 30；values 45、basis 18、quaternion 25 全部通过 |
| 依赖边界 | 11 个核心模块扫描与 32 项检查器自测通过 |
| sdist→wheel、仓库外空消费者 | PASS；离线安装仅有本工程，几何、时钟和只读 Registry 探测通过 |
| README 两个示例 | PASS；仓库外隔离解释器分别输出 cell/world: (1.00, 2.25, 3.00) m 和 mock-device-a / False / UNKNOWN |
| DOC 工具自测 / 运行时设计 | 文档自测 43；运行时自测 25、设计场景 44（T31=26、T34=18）通过；仅算 DOC |
| 独立代码复核 | FAIL；两个针对子类的独立探测确认只读边界可被破坏，见 DEF-0006 |
| 子类回归的实现前运行 | FAIL；26 个新增断言均报告未抛出预期 TypeError，覆盖后端聚合值、嵌套能力 / 身份 / 观测和文本子类 |

开发与复验原始输出独立保存在本地 `AR-0013/task-1-*`、`AR-0013/final-*`。独立反例的脚本及实际输出为 `AR-0013/review-subtypes.py` 和 `AR-0013/review-subtypes.log`；修正前新增回归的失败保存在 `AR-0013/task-1-fix-1-red.log`。原有通过只覆盖基础对象，不能覆盖本次反例或把本次技术结果改成 PASS。

## DEF-0006：数据子类可以破坏只读边界

首次实现使用 isinstance 接受后端提供的数据子类，并用 dataclasses.replace 把执行前提置为 False。replace 保留动态类型，子类的初始化可以把 execution 重新设为 True；独立探测确认 mock 的声明与 Registry 的 pose_goal.available 均可变为 True。另一个冻结的观测子类携带可调用字段，mock 与 Registry 的状态读取会原样返回该句柄。

这是同一个具体数据边界缺口：只读接口的普通值不应成为带行为的继承扩展点。由开发助手修正，独立助手复核。补充严格的具体类型 / 嵌套值验证及子类回归；保留既有 ID API、领域语义和安装方式，不引入通用安全沙箱。修正后在 [AR-0014](AR-0014-readonly-registry-final.md) 记录新的覆盖与结果。

## 验收边界

此记录结束时 DEF-0006 尚未关闭，DEV-M1-04 继续 DOING，I01 技术出口尚未闭合；产品验收 PENDING。原 DEF-0005 的基本 API 已有实现，但本轮不能据此完成只读交付。现实设备、后端运行时换代、执行链与完整状态投影均不在本轮验证范围。
