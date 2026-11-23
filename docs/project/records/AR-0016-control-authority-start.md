# AR-0016：控制租约与显式激活启动及首次 RED

| 日期 | 范围 | 环境 | 技术结果 | 产品验收 |
| --- | --- | --- | --- | --- |
| 2026-11-23 | I02 · DEV-M1-05 · T01 / T07 / T30 / T42 的控制权切片 | Linux x86_64、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | 基线 PASS；新增 API RED / FAIL | PENDING |

## 开始条件与范围

PR #2 已由用户合并为 `ffae4645dbf6677bc6a6ead06c47308406f5f667`。在已有隔离工作区创建新的功能分支，保留旧分支、原有只读 API 与验证记录。用户要求继续既有开发 / 提交流程，本轮建立 [I02](../iterations/I02-M1-control-loop.md) 的完整选择及最低验收主题，当前只执行 DEV-M1-05。

交付范围见[控制权与激活设计](../../design/09-control-authority-and-activation.md)：不可变绑定 / 租约 / 授权 / 策略值、设备单写与会话租约、显式激活、单调钟到期、拒绝时仍保留失权交接、未结执行标记。源码保持标准库和依赖向内。契约由独立助手核对，实现与修正另做独立复核；产品验收角色未指定。

## 实际执行

| 检查 | 退出码 | 结果 |
| --- | --- | --- |
| uv sync --locked --no-editable --reinstall-package bot3d-kernel --offline --link-mode copy --default-index https://pypi.org/simple | 0 | 精确版本与非编辑安装成功，锁文件未改 |
| uv run --no-sync python -I -m pytest -q | 0 | 原有 303 项全部通过 |
| 四个新 marker 的实现前 RED | 1 | 74 failed、303 deselected；均显式断言安装包缺少 framework.domain.control，无收集错误 |

RED 先于新增产品源码编写；原始输出为本地 `AR-0016/task-1-authority-red.log`，不覆盖历史。它证明已编写的行为断言不能在缺少控制权 API 时误通过；后续成功复验另记 [AR-0017](AR-0017-control-authority-final.md)。

## 缺口与设计复核

DEF-0008：基线没有控制租约、激活、失权和执行门禁 API，74 项新增测试 FAIL。按专题设计实现后，必须复验四个切片与原有全量集合，再以新 AR 关闭。

实现前独立复核补齐了四处契约：绑定能力上下文在释放 / 过期后仍保留，变化使旧绑定退役；真正执行不确定性原子设置聚合标记并撤权，解除覆盖所有未结原因；时钟维护效果不被权限或业务拒绝丢弃；公开不可变值拒绝矛盾的 owner / ARMED / 代数等组合。这些选择已写入设计和实现计划，未新增设备操作或认证协议。

## 边界

内部授权登记接收已认证事实，本轮没有认证协议或设备控制端口。失权结果是未来 STOP 用例的输入，不是已停车证明。完整 StateProjection、任务槽、最终下发、实际执行 / 停止和持久化继续由后续工作包实现。I01 仍 IN_ACCEPTANCE，I02 ACTIVE；产品验收均 PENDING。
