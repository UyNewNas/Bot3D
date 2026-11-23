# AR-0006：工程基础依赖边界复核

| 日期 | 范围 | 基线 | 技术结果 | 产品验收 |
| --- | --- | --- | --- | --- |
| 2026-11-23 | I01 · DEV-M1-02 · T26/imports 回归检查 | Linux x86_64、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | FAIL：新增违规反例漏检 | PENDING |

## 环境与范围

起点为提交 `319fed05a2d319bc6dc1865963670585fdc27cf9`，加上本轮未提交的回归测试；此时依赖检查器尚未修改。执行角色为开发助手，代码复核由独立助手承担，现实验收角色未指定。沿用原 Python、工具、依赖锁与非编辑安装；没有连接设备或改变时钟 API。

原有 Windows 证据保留在 [AR-0005](AR-0005-python-foundation-recheck.md)。本轮先运行原始全量 pytest，66 项全部通过；然后为两个实际漏检点增加 16 个有独立预期的测试。测试只解析坏样例，不执行 HTTP、线程或进程操作。

## 实际执行

在仓库根目录、完成锁定环境的非编辑安装后运行：

```bash
.venv/bin/python -I -m pytest
.venv/bin/python -I -m pytest tests/test_dependency_boundaries.py -k 'stdlib_http_transports or concurrency' --tb=short -q
```

第一条为未加入回归测试时的基线运行：退出 0，66 passed。第二条为测试已加入、检查器未修复时的运行：退出 1，14 failed、2 passed、32 deselected。14 个失败全部是预期的拒绝断言收到空违规列表，没有导入错误或环境失败。

| 子场景 | 预期 | 修复前实际 |
| --- | --- | --- |
| 根包 / 领域 / 应用三层中的类型专用、函数内 XML-RPC 导入，以及 WSGI HTTP 服务导入 | 按 AC-001 拒绝 HTTP 依赖，共 9 个反例 | 全部放行，9 FAIL |
| 纯领域的 threading、_thread、asyncio、concurrent.futures、multiprocessing 依赖 | 按运行时设计第 4 节拒绝并发运行机制，共 5 个反例 | 全部放行，5 FAIL |
| 应用层 asyncio / threading | 保留应用协调层的并发实现选择，共 2 个正例 | 2 PASS |

## 缺陷与结论

DEF-0002：依赖检查器按标准库顶层模块名放行未禁用项，漏掉标准库 HTTP 传输和纯领域并发依赖。`TYPE_CHECKING` 分支与函数内导入不会在普通模块导入时执行，因此现有运行时探测不能弥补静态漏检。

影响为 T26/imports 的回归保护不完整；当前产品源码没有上述违规依赖，原有 66 项测试的通过记录有效。修复限于检查器和测试，不增加第三方依赖或业务功能，不改变 AC。该次 FAIL 保留，修复后的结果必须另建 AR；DEV-M1-03、T28 / T29 / T46 和产品闸门不据此放行。
