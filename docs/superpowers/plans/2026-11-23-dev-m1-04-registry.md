# DEV-M1-04 Read-only Registry Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for the code task; the controller integrates documentation and evidence in this session.

**Goal:** Deliver pure effective-capability composition and revisions, identity-preserving read-only discovery, and a SIM mock with no execution surface.

**Architecture:** capabilities owns pure composition; discovery owns immutable binding / observation values; a read-only port feeds an in-memory application Registry; the adapter supplies static SIM fixtures. Runtime epoch changes and state projection remain later work.

**Tech Stack:** CPython 3.12.11, uv 0.10.9, pytest 8.4.2; standard library only at runtime.

**Spec:** [Read-only Registry and capabilities](../../design/08-readonly-registry-and-capabilities.md), [I01](../../project/iterations/I01-M1-foundation.md).

## Global Constraints

- Start from merged master b084218d82caa20e13d5e2ef3055f69046785547 in the isolated feat/dev-m1-04-registry worktree. Preserve the previous API, README homepage structure, version pins and lock.
- No new runtime or development dependencies. No device / network connection, execution, leases, switching, persistence or StateProjection implementation.
- Pure pose-goal composition requires planning, model, frames, policy and execution. Public read-only Registry and mock always force execution=False and expose no control methods.
- Capability revisions start at 1 per binding, advance on published semantic / configuration / mode changes, and remain stable on equivalent reads. A→B→A advances twice.
- Backend identity includes device, backend ID, SIM / REAL kind and epoch. Mismatches raise without rebinding. Multiple read-only mirrors may share a device.
- Missing observations stay None / UNKNOWN; never default to zero, STOPPED or a safe physical state. Existing goal types are not actual feedback.
- Four T29 / T46 slices add UNIT / MOCK evidence. Product acceptance remains PENDING; I01 is not automatically CLOSED.
- Continue the authorized commit / feature-branch PR workflow after validation; do not merge master automatically. Controller owns final publication.

## Review Focus

- All-declared inputs or richer injected backends cannot cause a read-only public capability to become executable.
- Missing-reason changes while unavailable and configuration / mode changes with identical booleans both advance revisions; repeated reads and display-name changes do not.
- Duplicate IDs, identity drift and failed registrations do not replace established bindings or mutate prior snapshots. A failed discovery batch commits no capability revisions; a successful retry publishes each changed binding once.
- Input lists are copied, nested values immutable, wrong wrappers / booleans / NaN rejected, and absent feedback stays unknown.
- Device-sharing mirrors keep distinct logical identities and independent revisions; package probes exercise new modules from installed artifacts.

## Task 1: Implement capabilities, read-only Registry and mock

**Files:** Create src/framework/domain/capabilities.py, src/framework/domain/discovery.py, src/framework/application/registry.py, src/framework/adapters/mock_robot.py; tests/test_capability_composition.py, test_capability_revision.py, test_registry_discovery.py, test_readonly_mock.py. Modify application/ports.py, pyproject.toml markers, tests/test_package.py, tests/test_dependency_boundaries.py and tools/check_wheel_install.py. No documentation edits in this task.

**Interfaces:** Exact classes, functions, fields, errors and semantics are fixed in spec sections 2–4. Reuse existing RobotId, DeviceId and finite validation. Do not make up an execution port, mutable state projection or protocol payload.

- [x] Write tests first for all four slices, register t29_compose, t29_revision, t46_discovery, t46_readonly, and capture explicit API-unavailable assertion failures before implementation. Each new test belongs to exactly one marker. Save every RED output to a unique path.
- [x] Implement spec section 2, including all-five pure success and one-missing cases, fixed full reason order, non-boolean rejection, initial revision1, no-op reads, changed reasons/config/mode, A→B→A and frozen snapshots.
- [x] Implement spec section 3 values with strict field validation, list-to-tuple copying, duplicate-joint rejection, unknown-vs-empty distinction and separate RobotId/DeviceId. Known joint fixture uses position_rad=0.25 and velocity_rad_s=None; missing mock uses all absent physical data and UNKNOWN.
- [x] Implement section 4 Registry, read port and SIM mock. Tests cover empty/sorted discovery, same-robot duplicate rejection before any replacement backend read, unknown/wrong IDs, full identity drift in describe/state, per-binding revisions, shared-device mirrors and failed registration atomicity.
- [x] Verify read-only enforcement at both adapter and Registry, including injected execution=True plus control-method traps; public results contain ordinary values only. No connection or movement calls, including on repeated reads and failures.
- [x] Extend existing isolated import and offline wheel probes with an actual registered mock, identity-preserving description/state, unavailable pose goal and unknown feedback; preserve the current geometry/time probes and no-dependency/non-editable assertions.
- [x] Reinstall pinned non-editable package after source changes. Run full pytest, four slice markers, core scan and checker self-tests; save commands/counts/logs and report concerns. Do not commit; controller packages the stable diff for spec and quality review.
- [x] Resolve concrete review findings, preserving failures and separate recheck evidence, then hand off stable code.

## Task 2: Integrate docs, verify and publish

**Files:** README.md; docs/README.md; design/project entry points; backlog, requirements, I01 and acceptance index; new execution records; this plan and local ledger. Controller owns these files.

**Interfaces:** Consume the actual installed public API and Task 1 evidence. Keep README centered on the project; add a short working read-only example and current module / roadmap updates.

- [x] Record baseline170 and first RED in the next execution record; add a new success record after implementation. Preserve historical records and all failures without overwrite.
- [x] Run lock check, full tests / four markers, import checks, sdist→wheel build, empty offline consumer, README examples, DOC checks and git diff --check. Evidence is recorded in AR-0015; independent whole-branch review follows before publication.
- [x] Mark DEV-M1-04 DONE only with evidence, REQ-003 DEVELOPING and I01 ten completed technical slices; retain product PENDING and move I01 to IN_ACCEPTANCE when its technical exit is complete. Identify subsequent I02 scope without starting execution features.
Publication follows the review gate: commit the validated change, publish a new feature branch and PR against current master using the connected GitHub path, and verify remote tree equality. No master merge; the user handoff records the remote commit and PR.
