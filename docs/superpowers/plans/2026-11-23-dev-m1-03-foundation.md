# DEV-M1-03 Foundation Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for the code task; the controller integrates evidence and documentation in this session.

**Goal:** Deliver immutable identities, finite SI values, scoped tool goals, quaternion algebra and framed rigid transforms with all three T28 slices.

**Architecture:** Three pure standard-library modules: values owns validated identities/vectors/unit conversion; geometry consumes values and owns quaternion/transform math; targets consumes both for required scoped goals. The public transport and application execution contracts remain unchanged.

**Tech Stack:** CPython 3.12.11, uv 0.10.9, pytest 8.4.2, standard-library dataclasses and math.

**Spec:** [Domain foundation](../../design/07-domain-types-and-geometry.md), [I01](../../project/iterations/I01-M1-foundation.md).

## Global Constraints

- Preserve previous uncommitted DEV-M1-02 work. The user's follow-up explicitly includes the README rewrite in this commit; after validation, commit the combined changes on the feature branch. Keep integration into master separate from this implementation task.
- No new runtime or development dependencies; keep CPython 3.12.11 / uv 0.10.9 and the dependency lock.
- SI positions are metres; angular conversion returns radians; right-handed active rotations, xyzw quaternion ordering.
- Quaternion norm acceptance is the closed interval [1.0 - 1e-6, 1.0 + 1e-6]; normalize only accepted inputs. Numeric assertions use abs=1e-9, rel=0.
- No unknown/default-zero feedback, no coordinate provenance/validity or tool/workspace policy claims, no DEV-M1-04 implementation; product acceptance stays PENDING.

## Review Focus

- Finite validation excludes bool/text/None and prevents nonfinite computed results; vectors with finite components are valid even when their norm is too large.
- Distinct ID classes and scoped frames prevent type and frame mixing; shared world frames remain valid.
- Type boundaries copy input arrays, preserve immutability and do not default missing pose fields.
- Quaternion lower/upper endpoints and adjacent outside floats follow the declared tolerance; q/-q rotate equally.
- Noncommuting composition and framed inverse/point/direction tests use hand-derived expected numbers.

## Task 1: Implement domain values and mathematical goals

**Files:** Create src/framework/domain/values.py, geometry.py, targets.py; tests/test_values.py, test_quaternion.py, test_transforms.py, test_targets.py. Modify pyproject.toml only to add T28 markers, tests/test_package.py and tests/test_dependency_boundaries.py to import the new core modules in their existing isolated subprocesses, and tools/check_wheel_install.py to exercise the new target/transform in an empty consumer.

**Interfaces:** Exact public class/function names and method semantics come from the spec. values exports RobotId, DeviceId, FrameId, ToolId, Vector3, mm_to_m, m_to_mm, deg_to_rad, rad_to_deg; geometry exports Quaternion, FrameMismatch, RigidTransform; targets exports PoseGoal. Preserve existing time/clock APIs. Classes use frozen dataclasses with slots. A private finite-float helper may be shared by domain modules.

- [x] Write meaningful tests first and record a RED run before implementation. Record an API-unavailable assertion as a test failure rather than hiding coverage behind skips. Register t28_values, t28_basis, t28_quaternion; each new test belongs to exactly one slice.
- [x] Implement the three modules according to spec sections 2–4. Keep errors typed, no silent numeric coercion from strings/bools, and validate output finiteness.
- [x] Cover every hand-derived row in spec section 5. Add malformed frame/type/array cases, mutation/aliasing checks, mismatched transform chains and goal transformation, noncommuting rotations, both tolerance endpoints and nextafter inside/outside, and an actually unrepresentable output that raises ValueError.
- [x] Extend existing installed-module and clean-wheel probes to import and exercise the new modules and a scoped goal. Keep their non-editable, no-source-path and no-runtime-dependencies checks.
- [x] Reinstall with the pinned uv sync command after source changes; focused tests during work, full pytest once before reporting. Run the three T28 markers, core import scan and checker self-tests. Preserve RED/GREEN logs and report file paths, exact counts and unresolved concerns. No commit.
- [x] Independent task review checks spec compliance and quality before integration.

## Task 2: Integrate evidence and finish the scoped work

**Files:** docs/README.md; relevant design/project entry points, backlog, requirements, iteration and acceptance index; AR-0008 startup/RED evidence, AR-0009 / AR-0010 numerical reviews and AR-0011 corrected final results. Update this plan/ledger using actual outcomes only. Task 3 owns README.md independently.

**Interfaces:** Consume Task 1's public API and reports; publish runnable examples using the actual installed package. Product statuses remain PENDING; only completed task DEV-M1-03 becomes DONE and requirements with partial evidence become DEVELOPING.

- [x] Preserve AR-0008 failures and AR-0009 / AR-0010 review findings; record corrected results in AR-0011 with environment, base plus local prior work, commands/counts and exact remaining scope.
- [x] Run pinned non-editable sync, lock check, full pytest/T28 slices, import checks, sdist→wheel build, clean offline consumer, existing DOC checks and git diff --check. Expected: exit 0; no claims of Windows/CI/SIM/XR/REAL execution.
- [x] Update I01 to six passed UNIT slices and four T29/T46 slices remaining; DEV-M1-04 is next TODO. Update links/counts without changing prior AR records.
- [x] Fresh final review of new code plus evidence; fix concrete blocking findings, then commit the validated code and documentation together, preserving the prior engineering fixes.

## Task 3: Rewrite the project homepage

**Files:** README.md only; source references and editorial decisions stay in the local task report.

**Goal:** Follow the user's explicit direction: introduce the project, explain the architecture and implementation approach, and provide a practical starting point. Study the official READMEs of comparable robotics projects for information structure.

- [x] Explain Bot3D's purpose and intended users before development tracking details.
- [x] Show the architecture and core design choices, clearly distinguishing implemented modules from planned integrations.
- [x] Include an executable example using Task 1's API, pinned installation commands, development route and concise documentation links.
- [x] Validate the example, local links and factual claims; include the rewrite in the same commit as DEV-M1-03.
