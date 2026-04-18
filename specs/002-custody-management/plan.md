# Implementation Plan: Custody Management

**Branch**: `002-custody-management` | **Date**: 2026-04-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-custody-management/spec.md`

## Summary

Introduce the `Purisol Custody Entry` submittable DocType (with its `Purisol Custody Entry Booklet` child table) to record every custody event — `Assign` (shop → delivery man), `Transfer` (delivery man → delivery man, with first-class partial support), and `Return` (delivery man → shop). On submit, each listed booklet transitions between `In Stock` and `In Custody` and its `current_delivery_man` field is set/cleared accordingly. All updates within one entry happen transactionally (all-or-nothing). On cancel, each booklet reverts to the snapshot captured at entry time, unless the booklet has since moved — in which case cancellation is rejected with a clear error. Deliver a "Current Custody by Delivery Man" Query Report for operational observability.

**Technical approach** (summarised from research.md):

- **New DocTypes** authored as Frappe fixtures under `cx_purisol/cx_purisol/cx_purisol/doctype/`:
  - `Purisol Custody Entry` — submittable (`is_submittable = 1`), `track_changes = 1`, `autoname = "PCE-.YYYY.-.#####"`, naming year-scoped.
  - `Purisol Custody Entry Booklet` — child table (`istable = 1`) with snapshot fields for safe reversal.
- **Phase 1 Booklet controller widening**: the Phase-1 `validate` guard on `Purisol Coupon Booklet` rejected any status other than `In Stock`. This phase relaxes that guard to permit transitions between `In Stock` and `In Custody`, still rejecting `Sold` and `Depleted` (deferred to Phases 3 and 4). `current_delivery_man` is made read-only *in the form* so it cannot be hand-edited from the desk; writes happen only from the Custody Entry controller using `ignore_permissions=True`.
- **Validation** runs entirely in the Custody Entry controller's `validate` hook (pre-submit), using a single per-entry-type rule set:
  - `Assign`: require `to_delivery_man`, forbid `from_delivery_man`; every booklet must be `In Stock`.
  - `Return`: require `from_delivery_man`, forbid `to_delivery_man`; every booklet must be `In Custody` with `current_delivery_man == from_delivery_man`.
  - `Transfer`: require both `from_delivery_man` and `to_delivery_man`, different; every booklet must be `In Custody` with `current_delivery_man == from_delivery_man`.
  - Empty child table and duplicate booklet rows in the same entry are rejected in all types.
- **Atomicity**: `on_submit` iterates the child table inside the request's transaction. Because Phase 1 bounds the child list at ≈ 50 booklets (assumption), a single transaction is appropriate (constitution VIII's 100-record enqueue threshold is not crossed). A late-stage failure inside `on_submit` raises `frappe.ValidationError`; Frappe aborts the submit and rolls back all writes atomically.
- **Snapshotting** happens in `before_submit` (after validation, before status writes): each child row captures `booklet_status_at_entry` and `delivery_man_at_entry` from the booklet's *current* state. These snapshots power cancel reversal without re-querying history.
- **Cancellation reversal** (`on_cancel`): for each child row, the controller verifies the booklet's *current* state matches the expected post-submit state (derived from entry type + `to_delivery_man` / cleared). If yes, it reverts the booklet to the snapshot. If no (the booklet has since moved), the cancel is rejected with a clear error — preserving the audit chain invariant.
- **Concurrency safety**: Frappe's optimistic locking on the Booklet's `modified` timestamp rejects stale writes with `frappe.TimestampMismatchError`. This is sufficient for two Administrators submitting conflicting Custody Entries: exactly one commits; the other is rejected and the Administrator retries.
- **"Current Custody by Delivery Man"** ships as a Frappe Query Report over `Purisol Coupon Booklet` filtered to `status = In Custody`, with columns `current_delivery_man`, `booklet_number`, `days_in_custody` (computed from the most-recent Custody Entry touching this booklet), and optional `customer` (null until Phase 3 — present now for forward-compat). Groupable by `current_delivery_man` via Frappe's built-in report grouping.
- **Tests**: unit tests for per-type validation, integration tests for each entry type end-to-end, plus explicit scenarios for partial transfer, atomic rollback on invalid booklet, and cancel rejection when the booklet has since moved.

## Technical Context

**Language/Version**: Python 3.10+ (Frappe server), JavaScript (Frappe client scripts).
**Primary Dependencies**: Frappe Framework 15.x, ERPNext 15.x (Employee link). No new third-party libraries.
**Storage**: Frappe DocTypes on MariaDB via `frappe.db` / `frappe.get_doc`; no raw SQL writes.
**Testing**: Frappe test framework (`frappe.tests.utils.FrappeTestCase`), invoked via `bench --site <test-site> run-tests --app cx_purisol`.
**Target Platform**: Linux server running Frappe Bench (gunicorn + RQ workers + MariaDB + Redis).
**Project Type**: Frappe custom app (`cx_purisol`) — extending the Phase 1 module with one submittable DocType, one child table, and a Query Report.
**Performance Goals**:
- A single Custody Entry submit involving up to 50 booklets completes in under 2 s end-to-end (spec SC-001 allows 60 s including UI navigation; the server path should be well under that).
- "Current Custody by Delivery Man" report loads in under 2 s for a working set of up to 1,000 booklets `In Custody` (spec SC-005).

**Constraints**:
- Frappe default gunicorn worker timeout is 120 s; 50-booklet entries are well within.
- Atomic all-or-nothing submit (spec FR-020, FR-024); no partial visibility of booklet state.
- Booklets reachable only through `In Stock ↔ In Custody` in this phase (spec FR-051); `Sold` / `Depleted` must remain blocked.
- Every user-facing string wrapped in `frappe._()` (constitution IX).
- Concurrent custody changes on the same booklet resolved by optimistic locking — exactly one submit succeeds (spec edge case; SC-003).

**Scale/Scope**: Single shop, single administrator. Typical entry: 1–20 booklets; worst realistic case: ~50. Expected steady-state: up to a few hundred booklets currently `In Custody` across a handful of delivery men. Multi-branch / multi-warehouse is out of scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution version: **1.0.0** (10 principles). The template has no pre-populated gates (constitution Sync Impact Report notes this as a known TODO, carried over from Phase 1). The 10 principles below are evaluated explicitly for this phase.

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Naming Convention | **PASS** | New DocTypes: `Purisol Custody Entry`, `Purisol Custody Entry Booklet`. Both follow prefix + single trailing space + descriptive name. No existing DocType renamed. |
| II | Leverage ERPNext Primitives | **PASS** | Delivery men are referenced as ERPNext `Employee` (not a custom DocType). No custom ledger, no parallel entity. Two new Purisol DocTypes represent genuinely-new concepts (a custody event and its child-row snapshot) — written justification for each appears in data-model.md. |
| III | State Machine Enforcement | **PASS** | The Phase-1 `Purisol Coupon Booklet.validate` guard is widened from `{In Stock}` to `{In Stock, In Custody}`. Transitions are driven exclusively by Custody Entry submit/cancel. Disallowed transitions (e.g., direct form edit, or a Custody Entry whose source state doesn't match) raise `frappe.ValidationError`. `Sold` and `Depleted` remain blocked in this phase. Cancellation rejects with `frappe.ValidationError` if the reversal would conflict with a subsequent custody event (preserves the transition chain — no silent overwrite). |
| IV | Audit Trail by Default | **PASS** | `Purisol Custody Entry` is `is_submittable = 1`, `track_changes = 1`; its child table has `track_changes = 1`. The booklet's `status` and `current_delivery_man` are caches derived from Custody Entries — every state change has a corresponding submittable record, never a silent field update. Child rows snapshot `booklet_status_at_entry` and `delivery_man_at_entry` so full reversal data is preserved on the entry itself. |
| V | Error Handling Semantics | **PASS** | All rejections (wrong source state, wrong holder, missing required field, duplicate booklet, empty list, self-transfer, invalid cancel) use `frappe.throw(_(...))` — blocking errors only. Phase 2 produces **no** warning discrepancies — by design, since custody rules are unambiguous. Silent success is impossible: every branch either modifies booklets atomically or throws. |
| VI | Role Model | **PASS** | Only `Purisol Administrator` can create, submit, or cancel a Custody Entry. DocType-level perms: `read = 1, write = 1, create = 1, submit = 1, cancel = 1`. Employees (delivery men) have no system access (spec FR-050). No new roles introduced. |
| VII | Notification Channel | **PASS** | Phase 2 emits **no** notifications. Custody events are administrative and do not require user-facing alerts in this phase. Notification wiring remains the responsibility of Phase 5/6, and no trigger is hardcoded here that would block the future dispatcher seam. |
| VIII | Background Jobs | **PASS** | A Custody Entry submit updates at most ≈ 50 booklets (≈ 100 field writes across `status` and `current_delivery_man`) — well below the 100-record enqueue threshold. Synchronous processing is appropriate and keeps atomicity simple. If a future, larger-scale scenario emerges, the submit path can be re-entered as a background job without changing the validation/snapshot logic. |
| IX | Localization | **PASS** | Every form label, select option, error message, and report heading is wrapped in `frappe._()`. No LTR-only string concatenation; error messages use named placeholders (e.g., `_("Booklet {0} is not In Stock (current: {1})").format(name, state)`) so Arabic translation is unambiguous. |
| X | Testing Discipline | **PASS** | Test files planned under `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_custody_entry/test_purisol_custody_entry.py` (unit) and `cx_purisol/cx_purisol/cx_purisol/tests/test_custody_flows.py` (integration). Coverage: all three entry types, each validation failure path, partial transfer, atomic rollback, cancel reversal, cancel rejection after subsequent move, and the "Current Custody by Delivery Man" report. |

**No violations.** Complexity Tracking table is empty.

## Project Structure

### Documentation (this feature)

```text
specs/002-custody-management/
├── plan.md              # This file (/speckit.plan command output)
├── spec.md              # Feature specification (already written)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/
│   └── custody-entry.md # Phase 1: behavioural contract for Custody Entry submit/cancel
├── checklists/
│   └── requirements.md  # Spec-quality checklist (already written)
└── tasks.md             # Phase 2 output (/speckit.tasks command — NOT created here)
```

### Source Code (repository root)

```text
cx_purisol/                                        # Git repo root; Frappe app package
├── cx_purisol/                                    # Python package root
│   ├── hooks.py                                   # Existing; fixture list extended
│   ├── modules.txt                                # Unchanged
│   ├── patches.txt                                # New entry: one-time Phase-1 validate relaxation
│   └── cx_purisol/                                # Module folder ("Cx Purisol")
│       ├── doctype/
│       │   ├── purisol_coupon_booklet/            # *** MODIFIED in this phase ***
│       │   │   └── purisol_coupon_booklet.py      # Widen validate: permit In Stock ↔ In Custody
│       │   ├── purisol_custody_entry/             # *** NEW ***
│       │   │   ├── __init__.py
│       │   │   ├── purisol_custody_entry.json     # Submittable DocType definition
│       │   │   ├── purisol_custody_entry.py       # Controller: validate, before_submit, on_submit, on_cancel
│       │   │   ├── purisol_custody_entry.js       # Client: dynamic field toggles by entry_type
│       │   │   └── test_purisol_custody_entry.py  # Unit tests (per-type validation)
│       │   └── purisol_custody_entry_booklet/     # *** NEW (child table) ***
│       │       ├── __init__.py
│       │       └── purisol_custody_entry_booklet.json
│       ├── report/                                # *** NEW directory ***
│       │   ├── __init__.py
│       │   └── current_custody_by_delivery_man/
│       │       ├── __init__.py
│       │       ├── current_custody_by_delivery_man.json    # Query Report definition
│       │       └── current_custody_by_delivery_man.py      # (optional) Python columns/helpers
│       ├── tests/
│       │   ├── test_custody_flows.py              # *** NEW *** — integration tests
│       │   └── (existing Phase 1 tests unchanged)
│       └── fixtures/                              # Existing; role fixture already covers Custody Entry perms — add perms entry for the new DocType
└── specs/002-custody-management/                  # This plan
```

**Structure Decision**: Standard Frappe custom-app layout, consistent with Phase 1. New DocTypes live beside the existing Phase-1 DocTypes under the single `Cx Purisol` module (no new module is justified — all concepts are one cohesive "booklet lifecycle" domain). The child table DocType is a sibling of its parent (Frappe convention — child tables are first-class DocTypes that happen to have `istable = 1`). The Query Report lives under the same module's `report/` sub-package. Tests split Phase-1's convention: per-DocType unit tests co-located with their DocType, cross-cutting integration tests under the module-level `tests/` directory. One `patches.txt` entry is required because the Phase-1 `Purisol Coupon Booklet.validate` guard is widening — the change is purely additive (allows one more value) so the patch is a no-op on fresh installs; on upgraded sites, it's needed only to clear any cached validation state.

## Complexity Tracking

> No constitutional violations; table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
