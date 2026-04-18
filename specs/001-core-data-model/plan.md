# Implementation Plan: Core Data Model — Booklets & Coupons

**Branch**: `001-core-data-model` | **Date**: 2026-04-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-core-data-model/spec.md`

## Summary

Establish the foundational entities of the Purisol water-coupon system: a `Purisol Settings` singleton, and `Purisol Coupon Booklet` + `Purisol Coupon` DocTypes with their full MVP schema (fields for later phases included but unused). Ship a "Generate Booklets" action that creates N booklets + N×20 coupons with strict sequential numbering (`WP-NNNNN` / `CP-NNNNN`, never reset, coupons continuing across booklets), running synchronously for quantity ≤ 20 and via `frappe.enqueue` for quantity > 20, with progress feedback through `frappe.publish_realtime`. No custody, sale, consumption, discrepancy, notification, or reporting logic lands in this phase.

**Technical approach** (summarised from research.md):

- **DocTypes** authored as Frappe fixtures in `cx_purisol/cx_purisol/cx_purisol/doctype/`.
- **Naming**: Frappe naming series `WP-.#####` and `CP-.#####`, extending the `tabSeries` registry. A single serialized `frappe.model.naming.make_autoname` call per record is the authority; no custom number table.
- **Generation entry point**: whitelisted Python function in `cx_purisol/cx_purisol/cx_purisol/api/booklet_generation.py` (`purisol_generate_booklets`). Dispatches synchronously when `quantity ≤ 20`, otherwise `frappe.enqueue(...)`.
- **Concurrency**: generation acquires a short `frappe.db.get_value("Series", "WP", for_update=True)` row lock to serialize series consumption across simultaneous requests; coupon numbering is computed per-booklet inside the same transaction, so the invariant `WP-N ↔ CP-((N-1)*20+1)…CP-(N*20)` is held by construction rather than checked post hoc.
- **Atomicity**: each booklet + its 20 coupons are created inside a single transaction (`frappe.db.savepoint` per booklet). On failure, the partial booklet+its coupons rollback; already-committed earlier booklets remain, and the next generation resumes from the current series head with no gaps (spec FR-017).
- **Progress feedback**: `frappe.publish_realtime("purisol_generate_booklets_progress", {...})` on a per-job channel, consumed by a small client handler attached to the Generate Booklets form.
- **Validation**: Settings singleton enforced by `issingle=1` (Frappe native); duplicate-prevention is therefore structural, not policy.
- **Tests**: unit + integration using `FrappeTestCase`, exercising numbering across multiple batches, the WP→CP mapping, sync/async dispatch thresholds, and attempted Settings duplication.

## Technical Context

**Language/Version**: Python 3.10+ (Frappe server), JavaScript (Frappe client scripts).
**Primary Dependencies**: Frappe Framework 15.x, ERPNext 15.x (Item, Price List, Account links on Settings). No new third-party libraries.
**Storage**: Frappe DocTypes backed by MariaDB, accessed exclusively via `frappe.db` / `frappe.get_doc` (no raw SQL writes — per constitution "Additional Constraints").
**Testing**: Frappe test framework (`frappe.tests.utils.FrappeTestCase`), invoked via `bench --site <test-site> run-tests --app cx_purisol`.
**Target Platform**: Linux server running Frappe Bench (gunicorn + RQ workers + MariaDB + Redis).
**Project Type**: Frappe custom app (`cx_purisol`) — single-module Frappe app, no separate frontend.
**Performance Goals**:
- Sync path: ≤ 20 booklets (≤ 400 coupons) complete end-to-end within 5 s (spec SC-003).
- Async path: control returns to the UI within 2 s (spec SC-004); background job completes 1,000 booklets (20,000 coupons) without worker timeout.
- Dashboard/reporting performance is out of scope for this phase.

**Constraints**:
- Frappe default gunicorn worker timeout is 120 s → any operation touching > 400 records must be enqueued (constitution VIII).
- Strict no-gap, no-duplicate numbering under concurrent generation (spec FR-021, SC-006, SC-007).
- `WP-N` ↔ `CP-((N-1)*20+1)…CP-(N*20)` invariant across all time (spec FR-008, SC-002).
- All user-facing strings wrapped in `frappe._()` (constitution IX).

**Scale/Scope**: Single shop, single administrator. Expected steady-state: a few hundred booklets in circulation at a time; largest realistic single-batch generation ≈ 100 booklets. Hard cap is not imposed in this phase (background job handles 1,000 booklet stress runs cleanly).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution version: **1.0.0** (10 principles). The template has no pre-populated gates (constitution Sync Impact Report notes this as a known TODO). The 10 principles below are evaluated explicitly for this phase.

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Naming Convention | **PASS** | All new DocTypes are `Purisol Coupon Booklet`, `Purisol Coupon`, `Purisol Settings`. Prefix + single trailing space + descriptive name. |
| II | Leverage ERPNext Primitives | **PASS** | `Purisol Settings` links to ERPNext `Item`, `Price List`, `Account`. No custom replacement for any ERPNext concept. Three custom DocTypes represent genuinely-new concepts (coupon, booklet, app settings) with justification in data-model.md. |
| III | State Machine Enforcement | **PASS** | Status domains `In Stock / In Custody / Sold / Depleted` and `Available / Consumed` are frozen in the schema now. Only the initial states are reachable in this phase; transition hooks (`before_save` / `on_update`) will be added in later phases. Forbidding direct status writes (except to the initial value) is enforced via `read_only_depends_on` + Python guard on `Purisol Coupon Booklet.validate` that rejects any status other than `In Stock` for this phase. Attempt to set any unreachable value raises `frappe.ValidationError`. |
| IV | Audit Trail by Default | **PASS** | `track_changes = 1` on all three DocTypes. No submittable record is introduced in this phase (none of the Phase-1 actions are state transitions beyond creation); the per-coupon consumption metadata fields exist but are unpopulated. Generation is not a state transition — it is record creation, which is already captured in `tabVersion` via `track_changes`. |
| V | Error Handling Semantics | **PASS** | Generation rejects non-positive qty and attempted Settings duplication with `frappe.throw(_(...))` — blocking errors only. No warning discrepancies arise in Phase 1. Silent success is not possible (every code path either creates records or throws). |
| VI | Role Model | **PASS** | Single custom role `Purisol Administrator` is declared via fixture. All three DocTypes grant read/write (and for Settings: only read+write, no create/delete because `issingle=1`). No other roles introduced. |
| VII | Notification Channel | **PASS** | Progress feedback uses `frappe.publish_realtime` — the same realtime path the bell channel uses. A dispatcher seam (`cx_purisol.notifications.dispatch(event, payload)`) is *not* required in Phase 1 (no notifications are emitted), but the progress-feedback call is structured so it is trivial to route through the dispatcher once Phase 5/6 introduces it. |
| VIII | Background Jobs | **PASS** | Generation > 20 booklets (> 400 records) uses `frappe.enqueue("cx_purisol.api.booklet_generation._run_generate_booklets_job", ...)`. Job is idempotent: it consumes the next N series values, so a retry after partial success continues from the current series head (no gaps, no duplicates). |
| IX | Localization | **PASS** | Every user-facing string (form labels, error messages, summary messages, progress messages) is wrapped in `frappe._()`. No hardcoded LTR assumptions: summary format is `{first} → {last}` rather than textual sentence fragments. |
| X | Testing Discipline | **PASS** | Test files planned in `cx_purisol/cx_purisol/cx_purisol/tests/` (see Project Structure). Unit tests cover numbering logic and the WP→CP mapping function; integration tests exercise `generate_booklets(N=5)` (sync), `generate_booklets(N=50)` (async, enqueue mocked or inline via `frappe.enqueue(now=True)`), and attempted singleton duplication. |

**No violations.** Complexity Tracking table is empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-core-data-model/
├── plan.md              # This file (/speckit.plan command output)
├── spec.md              # Feature specification (already written)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/
│   └── booklet-generation.md  # Phase 1: Python API contract for generate_booklets
├── checklists/
│   └── requirements.md  # Spec-quality checklist (already written)
└── tasks.md             # Phase 2 output (/speckit.tasks command — NOT created here)
```

### Source Code (repository root)

```text
cx_purisol/                                  # Git repo root; Frappe app package
├── cx_purisol/                              # Python package root
│   ├── hooks.py                             # Existing; fixture registration added here
│   ├── modules.txt                          # Existing; module "Cx Purisol" unchanged
│   ├── patches.txt                          # Existing; no patches needed for initial schema
│   └── cx_purisol/                          # Module folder ("Cx Purisol")
│       ├── doctype/
│       │   ├── purisol_settings/
│       │   │   ├── __init__.py
│       │   │   ├── purisol_settings.json    # DocType definition (issingle=1)
│       │   │   ├── purisol_settings.py      # Controller (validate only)
│       │   │   └── test_purisol_settings.py
│       │   ├── purisol_coupon_booklet/
│       │   │   ├── __init__.py
│       │   │   ├── purisol_coupon_booklet.json
│       │   │   ├── purisol_coupon_booklet.py   # Controller: autoname, validate
│       │   │   └── test_purisol_coupon_booklet.py
│       │   └── purisol_coupon/
│       │       ├── __init__.py
│       │       ├── purisol_coupon.json
│       │       ├── purisol_coupon.py         # Controller: autoname, validate
│       │       └── test_purisol_coupon.py
│       ├── api/
│       │   ├── __init__.py
│       │   └── booklet_generation.py        # purisol_generate_booklets (@frappe.whitelist)
│       ├── tests/
│       │   ├── __init__.py
│       │   ├── test_numbering.py            # unit: WP↔CP mapping
│       │   └── test_booklet_generation.py   # integration: sync + async generation
│       └── fixtures/
│           ├── role.json                    # Purisol Administrator role
│           └── custom_role_permission.json  # (if needed beyond DocType-level perms)
└── specs/001-core-data-model/               # This plan
```

**Structure Decision**: Standard single-module Frappe custom app layout. The app has exactly one module (`Cx Purisol`, per existing `modules.txt`), so all three Phase-1 DocTypes plus the generation API live beneath `cx_purisol/cx_purisol/cx_purisol/`. The generation entry point is a dedicated `api/` sub-package rather than a method on any DocType controller — generation is a batch operation across multiple records, not a single-record lifecycle event. Tests are split: DocType-local tests live beside each DocType (Frappe's convention for unit tests of a single DocType); cross-cutting tests (numbering invariant, generation orchestration) live under a feature-level `tests/` directory.

## Complexity Tracking

> No constitutional violations; table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
