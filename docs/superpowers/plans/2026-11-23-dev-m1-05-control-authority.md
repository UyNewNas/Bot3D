# DEV-M1-05 Control Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development for the coupled code task. Controller integrates docs, evidence, review and publication.

**Goal:** Deliver exclusive session-bound leases, explicit activation, monotonic expiry, and loss effects for later stopping integration.

**Architecture:** Immutable domain data and pure policy feed a synchronized in-memory application authority owner. Trusted session registration and unresolved-execution markers stay inside that owner; no backend handles or actual execution are introduced.

**Tech Stack:** CPython 3.12.11, uv 0.10.9, pytest 8.4.2; standard library runtime only.

**Spec:** [Control authority and activation](../../design/09-control-authority-and-activation.md); [I02](../../project/iterations/I02-M1-control-loop.md).

## Global Constraints

- Start from merged master ffae4645dbf6677bc6a6ead06c47308406f5f667 on feat/dev-m1-05-control-authority in the existing isolated worktree; preserve old APIs and the 303-test baseline.
- No new dependencies or lock/version changes. Do not connect devices, create an executor/STOP adapter, authentication protocol, Journal or full StateProjection.
- Existing RobotRegistry / ReadOnlyBinding / SIM mock remain readonly; their public execution support remains false.
- One writable binding per DeviceId at setup, one active lease per robot; authenticated-session authorization is registered and revoked server-side, never replaced by request-supplied permission facts.
- Exact lease/session/full binding identity is required. Fresh lease IDs never revive; every authority-sensitive entrance uses now < expiry, equality expires.
- Every loss carries the immutable original binding and survives a rejecting result. Clock failure disarms all leases and permanently blocks new authority, while protective operations remain callable.
- Qualified STOPPED is an explicit activation-only prerequisite. READY, lease, ARMED and observed motion remain independent; healthy MOVING can retain ARMED while renewing.
- Adopted capabilities remain fenced across release/expiry. Any later context mismatch or explicit CONTEXT_CHANGED retires the old binding permanently; old evidence cannot reacquire. Recovery belongs to a trusted new-epoch lifecycle.
- Genuine unresolved execution atomically latches an aggregate hold and revokes/disarms. A current trusted disposition covers every outstanding cause; observations, stop receipts and stale holds cannot clear it. After clearing, executable authority requires fresh acquisition and explicit activation.
- Apply the spec's explicit ordering: independent clock maintenance, session scope, lease identity, current scoped context/continuous policy, then operation-specific gates. A FORBIDDEN result may carry expiry or global clock-fault effects for the trusted coordinator.
- These are UNIT / MOCK authority slices. I01 and I02 product acceptance remain PENDING; no physical stopping or final-dispatch guarantee is claimed.
- Continue the authorized feature-branch commit / PR workflow after review. Do not merge master automatically.

## Review Focus

- Lost-session or revoked authorization snapshots cannot reacquire, and stale same-session lease IDs or delayed timeout notifications cannot mutate a replacement lease.
- Expiry discovered in a denied operation returns its stopping effect exactly once; a fresh lease is not granted during that same call.
- Independent readiness and healthy own motion do not trigger activation-only parking rules during renewal, while continuous protection or capability context loss disarms.
- An old exact-binding resolution cannot clear a newer aggregate execution hold; a STOPPED value alone grants nothing. Marking and clearing uncertainty cannot revive the old lease.
- Context fences survive lease termination; value constructors reject impossible owner/arming/fault/generation combinations and denied leases while allowing legitimate global clock-fault effects.
- Shared clock failures affect all active bindings without dropping effects; invalid or stale scoped requests do not retarget the current binding.

## Task 1: Implement authority values, policy and application transitions

**Files:** Create src/framework/domain/control.py; src/framework/application/control_authority.py; tests/test_control_leases.py, test_authority_loss.py, test_control_activation.py, test_authority_clock.py. Add lazy authority fixtures in tests/conftest.py if useful. Modify pyproject.toml marker list, tests/test_package.py, tests/test_dependency_boundaries.py and tools/check_wheel_install.py. A shared tools/installed_api_probe.py may consolidate the common installed API probe while preserving all three independent environment checks. No docs edits in this task.

**Interfaces:** Implement exact values and APIs in spec sections 2–4. Use existing MonotonicClock and concrete identity/capability/time values. Errors on programming inputs are TypeError / ValueError; business denials and loss effects are immutable result data. Use a single short application Lock; no concurrent primitives in domain.

- [x] Write four marked test slices first; every new test has exactly one marker. Lazy imports produce explicit missing-API assertions, not collection errors. Save RED uniquely in AR-0016.
- [x] Implement the frozen data and pure ordered policy failures, including concrete nested types, repr-redacted IDs, context validation, unknown facts and time-window comparisons.
- [x] Implement static writable-device uniqueness and trusted session registration/revocation. Tests use operator-a/operator-b/viewer and prove revoked IDs cannot be registered or used again.
- [x] Implement acquire / renew / release / deactivate with the exact spec policy. Test at 0,9,10,11 ns, capped durations, unchanged original lease identity, two contenders via Barrier, both renew/release serial orders and stale-token refusal after reacquisition.
- [x] Implement activation / check: explicit confirmation, every continuous and parking prerequisite, scoped evidence, context change, existing ARMED with healthy MOVING, no implicit activation from lease/readiness or later restored facts.
- [x] Implement expiry, scope-preserving loss results, trusted revoke/revoke_session, clock-failure latch and current-token execution holds. Test multi-binding clock failure and returned effects, rejected expiry with effect, stale timeout/hold, and clock-independent protection.
- [x] Extend installed API probes to exercise an explicit synthetic session lease + activation + expiry while retaining geometry, readonly registry and time checks. Keep probes outside source path and without runtime dependencies.
- [x] Reinstall the fixed non-editable package, run full pytest, four markers, import boundary scan and checker self-tests; report exact commands/counts/logs. No commits; controller creates review packages and owns integration.
- [x] Resolve concrete review findings with unique RED / recheck evidence, then return stable source/tests/probes.

## Task 2: Integrate I02, project homepage and verification evidence

**Files:** docs/design/09-control-authority-and-activation.md; docs/project/iterations/I02-M1-control-loop.md; README.md; docs entry points; requirements/backlog/acceptance; new AR records; this plan. Controller owns docs and publication.

**Interfaces:** Document the actual installed API, current test results and boundaries. Use homepage prose plus a linked worked authority example; preserve existing README examples.

- [x] Establish I02 selection and its complete minimum test themes before implementation; current round is DEV-M1-05, later packages remain TODO / NOT_RUN.
- [x] Preserve baseline 303, RED and any independent review failures with DEF / new ARs. Never overwrite failed logs or earlier acceptance records.
- [x] Verify pinned lock, full regression, four markers, boundaries, sdist→wheel, empty consumer, README / design examples, DOC checks and diff check; record actual counts and source / artifact equality.
- [x] Mark only DEV-M1-05 DONE with evidence. REQ-005 / REQ-006 become DEVELOPING; I02 stays ACTIVE, product acceptance PENDING; identify DEV-M1-06 next per dependencies.

Publication follows the whole-branch review: commit, publish an isolated feature branch / PR against current master using connected GitHub, and verify remote tree equality. Record remote commit / PR in the user handoff; no master merge.
