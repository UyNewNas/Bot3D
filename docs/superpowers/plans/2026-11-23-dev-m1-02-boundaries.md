# DEV-M1-02 Dependency Boundary Repair Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Close the reproduced HTTP and pure-domain concurrency import-policy gaps in DEV-M1-02.

**Architecture:** Keep the existing read-only AST checker. Reject known standard-library HTTP transports in every core layer, and concurrency dependencies only in the pure domain. Keep application orchestration available and leave the clock API unchanged.

**Tech Stack:** CPython 3.12.11, uv 0.10.9, pytest 8.4.2, standard-library AST.

**Spec:** [AC-001](../../project/requirements.md), [runtime design section 4](../../design/05-runtime-coordination.md), [foundation](../../design/06-python-foundation.md).

## Global Constraints

- Continue DEV-M1-02 only; DEV-M1-03 remains TODO.
- Retain zero runtime dependencies and the existing Python/tool lock.
- Check sources without executing bad fixtures; the policy is not a Python sandbox.
- Preserve previous AR evidence and product acceptance PENDING.
- I01 excludes Git commits, pushes and external publication without separate authorization; prepare an uncommitted, reviewable result.

## Review Focus

- Type-only HTTP imports must fail even though runtime import probes cannot observe them.
- Function-local HTTP imports must fail without calling those functions.
- Package-root, domain and application HTTP imports all obey AC-001.
- Pure-domain locks, event loops, executors and processes are rejected; application concurrency remains allowed.
- Allowed standard-library and inward imports, installed-package origin, and independent wheel consumption retain their existing checks.

## Task 1: Repair and verify the dependency policy

**Files:** `tools/check_import_boundaries.py`, `tests/test_dependency_boundaries.py`, `docs/design/06-python-foundation.md`, README and project evidence links; new AR records in `docs/project/records/`.

**Interfaces:** Preserve `import_violations(source, module, *, layer, is_package=False)` and `check_tree(package_root)`, including diagnostics and return shapes.

- [x] Add literal negative fixtures for type-only/function-local `xmlrpc.client`, `wsgiref.simple_server`, and domain imports of `threading`, `_thread`, `asyncio`, `concurrent.futures`, `multiprocessing`; add positive application concurrency fixtures.
- [x] Run the new pytest cases before changing the checker. Expected: HTTP/domain negatives fail because they return no violations; application positives pass. Preserve FAIL in AR-0006.
- [x] Add `xmlrpc` and `wsgiref` to core forbidden roots and a separate domain-only concurrency set. Extend the standard-library self-tests and isolated HTTP import guard.
- [x] Run targeted tests and the whole suite using the pinned environment. Expected: all pass; original 66 cases remain covered.
- [x] Rebuild sdist/wheel and run the isolated offline wheel consumer, lock, import, runtime-design and project-document checks. Record actual exits/counts in AR-0007, index both ARs and link the latest evidence without replacing AR-0005.
- [x] Obtain a fresh read-only final review and leave the completed diff ready for approval of Git publication.
