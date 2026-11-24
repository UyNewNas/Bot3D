# AR-0021：命令日志与幂等启动

| 日期 | 范围 | 环境 | 技术结果 | 产品验收 |
| --- | --- | --- | --- | --- |
| 2026-11-24 | I02 / DEV-M1-06 基线与摘要切片 | Linux、CPython 3.12.11、uv 0.10.9、pytest 8.4.2 | 基线 PASS；摘要 RED→GREEN；日志尚待实现 | PENDING |

## 基线与范围

用户明确要求在 DEV-M1-05 PR 提交后继续 DEV-M1-06。GitHub 确认 PR #3 仍 open，head 为 `e653eeac9dd1c366ac1e95af70486f87f192116e`，master 为 `ffae4645dbf6677bc6a6ead06c47308406f5f667`。在该 head 创建独立工作区与 `feat/dev-m1-06-command-journal`；不合并或改动原 PR。交付继续面向 master 的功能 PR，并明示依赖。

设计见 [命令日志设计](../../design/10-command-journal-and-idempotency.md)，步骤见[实施计划](../../superpowers/plans/2026-11-24-dev-m1-06-command-journal.md)。独立助手核对运行时契约，另一个助手准备并验证锁定环境；实现由开发助手执行，最终另行独立复核。

## 实际证据

| 检查 | 结果 |
| --- | --- |
| 基线非编辑安装、隔离解释器 | 383 passed，退出 0 |
| 环境与来源 | CPython 3.12.11、uv 0.10.9、pytest 8.4.2；从 .venv site-packages 导入，全部 16 个 framework 文件与源文件一致 |
| 依赖 / 锁定安装 | 运行 Requires-Dist 为空；固定版本离线重装通过 |
| 摘要实现前 RED | 51 failed，全部为明确的 missing installed command digest API 断言；没有将导入 collection error 充作语义失败 |
| 摘要实现后 GREEN | 重装后全量 434 passed，退出 0；新增 51 项含固定编码、等价重试、20 个执行字段变更、非法值与具体类型边界 |

日志原文位于本次工作区 `.local/AR-0021/`：`baseline-*`、`digest-red.log`、`digest-install.log` 和 `digest-green.log`；不覆盖历史输出。环境脚本仅设置当前工作区工具 / 缓存路径，未修改全局配置或锁文件。

```bash
source .local/AR-0021/environment.sh
uv sync --locked --no-editable --reinstall-package bot3d-kernel --offline --link-mode copy --default-index https://pypi.org/simple
uv run --no-sync python -I -m pytest -q
```

## 待完成

JournalPort、内存原子日志、写入故障、完整分支复核、最终工件与文档验收尚未在本记录中声明完成。后续证据另存 AR-0022；REQ-009、I02 和产品验收遵循台账，不因基础切片通过而自动签收。
