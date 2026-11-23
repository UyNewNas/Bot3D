# AR-0012：只读 Registry 与能力组合启动

| 日期 | 范围 | 环境 | 技术结果 | 产品验收 |
| --- | --- | --- | --- | --- |
| 2026-11-23 | I01 · DEV-M1-04 · T29 / T46 四个切片 | Linux x86_64、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | 基线 PASS；实现前新切片 FAIL | PENDING |

## 开始条件与范围

上一轮 PR 已合并，基线为 `b084218d82caa20e13d5e2ef3055f69046785547`，包含 [AR-0011](AR-0011-domain-foundation-final.md) 的基础类型交付。新一轮使用独立功能分支和工作区，保留已有工程与 README 项目主页。

用户要求继续既有开发流程。本轮按[只读 Registry 设计](../../design/08-readonly-registry-and-capabilities.md)交付纯能力组合 / 版本、不可变身份 / 观测数据、内存 Registry、只读端口与 SIM mock；通过 T29/compose、T29/revision、T46/discovery、T46/readonly 补齐 I01 技术切片。执行角色为开发助手，契约与实现由独立助手复核，现实验收角色未指定。

## 实际执行

| 检查 | 退出码 | 结果 |
| --- | --- | --- |
| uv sync --locked --no-editable --reinstall-package bot3d-kernel --offline --link-mode copy --default-index https://pypi.org/simple | 0 | 新工作区使用指定版本非编辑安装，依赖从缓存取得 |
| uv run --no-sync python -I -m pytest | 0 | 原有 170 项全部通过 |
| uv run --no-sync python -I -m pytest -q --tb=short -m 't29_compose or t29_revision or t46_discovery or t46_readonly' | 1 | 106 failed、170 deselected；四个测试文件正常收集，均由显式 API 不可用断言失败 |

实现前 T29 / T46 的 RED 原始输出保存在本地 `AR-0012/task-1-red.log`。每次原始输出独立保存，不覆盖旧结果；首次实现与独立复核见 [AR-0013](AR-0013-readonly-registry-review.md)，最终复验另记 [AR-0014](AR-0014-readonly-registry-final.md)。

## DEF-0005：只读 Registry 与能力 API 尚未实现

首次运行时四个新切片已定义，领域能力组合 / 版本、只读身份 / 观测、Registry 与 SIM mock 尚未实现，产生 106 个预期断言失败。这是 DEV-M1-04 范围内的实现缺口，不是测试收集错误。由本轮开发助手实现，复核角色独立检查；关闭条件为四个切片通过并完成工程回归，证据只追加到后续 AR。

## 约束与待验事项

只读 Registry 与 mock 强制缺少执行支持，公开对象没有控制方法；未知观测保持 None / UNKNOWN。能力语义 / 配置 / 模式改变递增版本，重复读取保持版本。静态绑定身份不替代实际设备核验或换代流程。

本轮不实现租约、激活、切换、执行 / 停止、持久化或完整 StateProjection。此记录结束时新切片为实现前 FAIL，I01 为 ACTIVE，产品验收 PENDING。
