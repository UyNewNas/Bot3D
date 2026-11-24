# DEV-M1-06 命令日志与幂等 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付规范化执行摘要、JournalPort 和线程安全内存日志，明确候选接受、写入未知和保留边界。

**Architecture:** 纯领域类型承载命令和不可变日志事实；应用层声明同步端口；内存适配器原子插入和 CAS 追加，永不触发外部执行。延续既有项目设计，不提前实现协调器。

**Tech Stack:** CPython 3.12.11、标准库、uv 0.10.9、pytest 8.4.2。

**Spec:** [DEV-M1-06 设计](../../design/10-command-journal-and-idempotency.md)

## Global Constraints

- 运行第三方依赖为零；uv.lock、Python / uv / pytest 版本保持不变。
- 非编辑安装后用 `python -I` 验证；源目录不冒充安装包。
- robot_id＋command_id 为键，request_id 不入摘要；全部执行语义入摘要。
- 不发布物理执行、不实现 SQLite / STOP 集成，不把内存确认称为持久化。
- 保留原绑定、历史终态和 UNKNOWN；产品验收 PENDING。

## Review Focus

- 等价 q / -q 和负零应重试，但相邻有限浮点目标必须冲突。
- 原绑定 / 租约已经失效的已知命令仍可由获准调用者查历史；摘要不能使用当前上下文。
- 并发同键插入和同版本追加只有一个新写入，失败者不能覆盖已提交记录。
- 写后确认丢失与写前失败都不能使 key 被当成可重新执行；旧快照不能变成半写入状态。
- 迟到原句柄可补充 UNKNOWN 终态事实，不能重写结果或新增一次运动尝试。

## Execution ledger

基线 `e653eea`，独立 worktree `feat/dev-m1-06-command-journal`。环境与 383 项基线日志保存在 `.local/AR-0021/`。用户已授权继续该工作包及既有 PR 流程；原 PR #3 保持原状。本轮执行者落实相互依赖的代码任务，独立助手复核需求、环境及最终分支。

### Task 1: 命令类型与规范摘要

**Files:** Create `src/framework/domain/commands.py`; test `tests/test_command_digest.py`; add pytest slice markers to `pyproject.toml`.

**Interfaces:** Produces `CommandKey`, `CommandTiming`, `CommandContext`, `PoseConstraints`, `PoseCommand`, `canonical_execution(command) -> bytes`, `execution_digest(command) -> str` as defined by the spec.

- [x] Write independent fixed-byte digest, request-only retry, q / -q, negative-zero, one-ULP target and per-field conflict tests, plus concrete immutable boundary validation.
- [x] Run `uv run --no-sync python -I -m pytest -q tests/test_command_digest.py`; expected missing installed API assertions (RED): 51 failed with explicit missing installed API assertion.
- [x] Implement the pure concrete values and versioned encoding, retaining the existing geometry equality rules.
- [x] Reinstall with `uv sync --locked --no-editable --reinstall-package bot3d-kernel --offline --link-mode copy --default-index https://pypi.org/simple`; run the digest tests and full suite; PASS: 434 passed.
- [x] Commit task and actual verification evidence.

### Task 2: 日志端口、顺序和内存原子性

**Files:** Create `src/framework/domain/journal.py`, `src/framework/adapters/memory_journal.py`; modify `src/framework/application/ports.py`; test `tests/test_memory_journal.py`, `tests/test_journal_faults.py`.

**Interfaces:** Consumes Task 1 command types and digest. Produces immutable `CommandAcceptance`, `JournalEntry`, `CommandRecord`, `AcceptanceWrite`, typed event payloads and structured errors; `JournalPort.retention`, `lookup(key)`, `record_acceptance(acceptance)`, `append(key, entry, *, expected_revision)`; concrete `InMemoryJournal`.

- [x] Write candidate / publication, original-record retry/conflict, threaded insert / CAS, intent / receipt ordering, duplicate entry, terminal immutability, and declared lifetime tests.
- [x] Write storage faults using test-only mapping doubles: before-write, after-write acknowledgement loss, reads and intent / terminal updates; assert no false success, no partial snapshots and no new writes after uncertainty.
- [x] Run the new files against installed baseline; RED: 45 explicit missing journal API assertions.
- [x] Implement immutable records and guards, protocol and atomic memory adapter. Keep full authority / time / motion decisions in the future coordinator.
- [x] Reinstall and run both new files plus full suite; PASS: 45 journal tests and 479 total tests. Import boundary checker: 15 core modules PASS.
- [x] Commit task and actual verification evidence.

### Task 3: 安装消费者、文档与交付

**Files:** Extend `tools/installed_api_probe.py`; update README and project / iteration / acceptance / test-plan / requirements tracking; add AR-0021 / AR-0022 records.

**Interfaces:** Consumes Tasks 1–2 APIs; exposes a runnable local example without any device action.

- [x] Add installed-consumer exercise for canonical retry, accepted event, sole intent, original handle and immutable terminal; full installed suite 493 passed.
- [x] Build sdist→wheel and verify empty offline consumer, all 19 framework files agree across source / installed / sdist / wheel, zero runtime dependencies and current README metadata.
- [x] Run existing documentation, runtime-design and import checks; `git diff --check` PASS; 47 Markdown documents, 44 DOC scenarios and 15 core modules verified.
- [x] Obtain independent whole-branch review; 3 Important findings reproduced with 12 failing tests and 2 passing controls, then fixed with 493-test full regression. Long-history append performance remains a documented Minor.
- [ ] Mark completed work accurately and create the next feature PR against master, preserving the existing delivery convention. Since #3 is open, declare the dependency and provide the DEV-M1-06-only comparison from e653eea. Do not merge either PR.
