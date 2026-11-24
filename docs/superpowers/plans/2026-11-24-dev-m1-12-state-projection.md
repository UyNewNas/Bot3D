# DEV-M1-12 状态投影 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task; independent whole-branch review follows implementation.

**Goal:** 实现目标 / 计划 / 实际分离、确定的顺序 / 时间质量与可复核静止证据。

**Architecture:** 纯领域不可变类型 + 单协调序列持有的同步 StateProjection；不连接外部设备，第三方运行依赖为零。

**Tech Stack:** CPython 3.12.11、uv 0.10.9、pytest 8.4.2、标准库。

**Spec:** [状态投影设计](../../design/11-state-projection.md)

## Global Constraints

- 从 PR #4 的 b4f3802 建立独立 `feat/dev-m1-12-state-projection`；不合并前序 PR。
- 不改变锁文件 / 版本；非编辑重装后 `python -I` 测试，保持既有 493 项回归。
- 配置显式；未知不填零；收到数据、当前停车、历史命令结果与旧写入者失效分开。
- 单一所有者串行调用；回调 / 线程和总快照集成留协调器工作包。
- 产品验收 PENDING；不把 UNIT / MOCK 当作真实设备证据。

## Review Focus

关注源年龄与接收年龄不能互相替代、重复与映射变化不能伪造新鲜、时钟不确定区间的最保守边界、所有静止窗口失效点、迟到 FK 与旧上下文不能污染新状态、停止前采样不能作为新轮次证据。

## Tasks

### Task 1: 领域类型与投影

**Files:** `src/framework/domain/projection.py`, `src/framework/application/state_projection.py`, `tests/test_state_projection.py`, `tests/test_projection_time.py`, `tests/test_stationary_projection.py`, fixture and pytest markers.

**Interfaces:** Spec 中 `ProjectionConfig`, `ProjectionContext`, `FeedbackSample`, `ClockMapping`, `ProjectionTarget`, `ProjectionPlan`, `ForwardKinematicsResult`, `ProjectedState`, `StateProjection.ingest/snapshot/set_mapping/set_target/set_plan/change_context/begin_stationary_check/apply_fk`。

- [x] 先写行为测试，运行安装基线保存明确缺失 API 的 RED：87 failed，均为显式 missing installed state projection API 断言。
- [x] 实现输入边界、per-class 投影、顺序与上下文、映射和年龄、静止证据、FK 标记。
- [x] 非编辑重装后新增 87 项及全量 580 项通过，17 核心模块边界通过；实现提交 6acf17b。

### Task 2: 独立审查与修正

- [x] 独立完整分支审查 6acf17b，相对 b4f3802；发现 2 Critical、4 Important，均提供安装包反例。
- [x] 六类问题新增 18 项回归，修正前 15 failed / 3 passed；集中修正后全量 598 passed。保留日志，不将执行者复验写成第二次独立审查。

### Task 3: 消费者、文档与 PR

**Files:** installed API probe、README、工程台账 / 需求 / 迭代 / 验收 / 测试计划、AR-0023 / AR-0024。

- [x] 扩展仓库外安装消费者与可运行状态示例；4 个 README 示例通过，项目主页保留用途、架构和快速上手结构。
- [x] 离线构建 sdist→wheel、空消费者通过；21 个 framework 文件在源码 / 安装 / 两工件中逐字节一致，UTF-8 元数据、零运行依赖和固定版本通过。
- [x] 全量 598 项、分项 43 / 6 / 26 / 30、17 个核心模块、51 篇文档和 44 个 DOC 场景通过；`git diff --check` 通过，最终结果见 AR-0024。
- [ ] 创建面向 master 的功能 PR，说明依赖 PR #4 和本工作包独立差异，不自动合并。
