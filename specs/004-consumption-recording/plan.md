# Implementation Plan: Consumption Recording

**Branch**: `004-consumption-recording` | **Date**: 2026-04-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-consumption-recording/spec.md`

## Summary

Introduce a new submittable DocType `Purisol Coupon Consumption Entry` (with a child table `Purisol Coupon Consumption Item`) that records, in a single all-or-nothing transaction, every coupon a delivery man hands in at end of day. The Administrator picks the delivery man and lists coupons using either **Mode A — "By Booklet"** (pick a booklet → tick `Available` coupons → "Add to Entry") or **Mode B — "By Coupon Number"** (type/paste/scan coupon numbers with Enter-to-commit). Both modes populate the same child table so downstream logic is mode-agnostic. On submit, three blocking validations gate the operation — no empty child table, every coupon exists, no duplicate coupon in the entry, no already-`Consumed` coupon — and any failure rejects the whole submit with zero side effects. On success, in a single transaction, every listed coupon transitions `Available → Consumed` with `consumed_on = entry.posting_datetime`, `consumed_by_delivery_man = entry.delivery_man`, `consumption_entry = entry.name`; every touched booklet's `consumed_count` / `remaining_count` are recomputed; and any booklet whose `consumed_count` hits 20 transitions `Sold → Depleted` with `depleted_on` stamped. Cancellation is the symmetrical all-or-nothing reversal (clear consumption metadata, recompute booklet aggregates, revert `Depleted → Sold` where this entry was the trigger). Phase 4 emits **zero** discrepancy records and **zero** notifications — the seams for Phase 5 (`has_warnings`, `discrepancies_detected`) exist on the schema but are reserved-empty.

**Technical approach** (summarised from research.md):

- **New submittable DocType `Purisol Coupon Consumption Entry`** (`is_submittable = 1`, `track_changes = 1`, naming series `PCC-.YYYY.-.#####`). Fields: `posting_date` (Date, reqd, default today), `posting_time` (Time, reqd, default now), `delivery_man` (Link → Employee, reqd), `received_by` (Link → User, read-only, stamped in `before_insert`), `coupons` (Table → `Purisol Coupon Consumption Item`, reqd), `total_coupons` (Int, read-only, computed on validate), `has_warnings` (Check, read-only, always 0 in Phase 4), `discrepancies_detected` (Table → `Purisol Coupon Discrepancy Item` — a thin reserved-empty child table registered as a DocType stub so Phase 5 can fill it without schema churn), `notes` (Small Text). Permissions: `Purisol Administrator` only (create, write, submit, cancel, amend, print, read).
- **New child table DocType `Purisol Coupon Consumption Item`** (`istable = 1`). Fields: `coupon` (Link → Purisol Coupon, reqd, search_index), `booklet` (Link → Purisol Coupon Booklet, read-only, `fetch_from = coupon.booklet`), `customer` (Link → Customer, read-only, `fetch_from = coupon.booklet.customer`, may be empty if booklet is not `Sold`). Stored rows are mode-agnostic — Mode A and Mode B produce identical row shapes.
- **New child table DocType stub `Purisol Coupon Discrepancy Item`** (`istable = 1`, Phase-5 placeholder). Empty field set except a `notes` data field — exists only so Phase 4 can declare the `discrepancies_detected` table and Phase 5 adds its fields without renaming the parent table. Never populated in Phase 4; validated read-only empty on submit (FR-035).
- **Coupon-controller widening (`purisol_coupon.py`)**: Phase 1's validate insists `status == "Available"` and freezes every field. Phase 4 replaces that with a transition guard: allowed states `{Available, Consumed}`, allowed transitions `{(Available, Consumed), (Consumed, Available)}`. The reserved consumption-metadata fields (`consumed_on`, `consumed_by_delivery_man`, `consumption_entry`) may now be written by the controller — but only by the server-side Consumption Entry submit/cancel code (the JSON fields remain `read_only = 1` on the form). Direct form edits of `status` or those fields are still rejected by the form read-only + the transition guard.
- **Booklet-controller widening (`purisol_coupon_booklet.py`)**: `_ALLOWED_STATUSES` grows to `{In Stock, In Custody, Sold, Depleted}` and `_ALLOWED_TRANSITIONS` adds `(Sold, Depleted)` and `(Depleted, Sold)`. `Depleted` is only reachable via the Consumption Entry submit path's auto-depletion; `Depleted → Sold` is only reachable via the Consumption Entry cancel path's auto-revert (when cancel drops `consumed_count` below 20 and this entry was the trigger). No new direct form transition is enabled.
- **Consumption Entry controller (`purisol_coupon_consumption_entry.py`)** implements:
  - `before_insert`: stamp `received_by = frappe.session.user`.
  - `validate`: compute `total_coupons = len(coupons)`; non-empty child table; no duplicate `coupon` within the entry; every referenced coupon exists (link-integrity is Frappe's default, we only add duplicate-check). **We do not check `status == Available` in `validate`** — that check belongs in `before_submit` so that a draft can hold rows whose underlying coupon was consumed and failed by another entry between drafts and submit, surfacing the error only at submit as the spec requires (FR-033, edge case "coupon already consumed by intervening entry").
  - `before_submit`: per-row, load the live coupon state via a single `frappe.get_all("Purisol Coupon", filters={"name": ["in", coupon_names]}, fields=["name", "status", "consumption_entry"])` bulk read; build an errors list for every row whose coupon doesn't exist, is duplicated, or is already `Consumed` (naming the prior `consumption_entry` for the diagnostic hint). Any error aborts the submit via `frappe.throw("<br>".join(errors))` — inside the submit transaction, so no side effect is visible.
  - `on_submit`: in a single pass, for each row, `db_set("status", "Consumed")`, `db_set("consumed_on", self.posting_datetime)`, `db_set("consumed_by_delivery_man", self.delivery_man)`, `db_set("consumption_entry", self.name)` on the coupon (using `frappe.db.set_value` with `update_modified=True` on each coupon, which triggers `tabVersion` via track_changes). Then per distinct booklet touched: recompute `consumed_count = frappe.db.count("Purisol Coupon", {"booklet": name, "status": "Consumed"})`, set `remaining_count = 20 - consumed_count`, and if `consumed_count == 20` transition `status = Depleted` and stamp `depleted_on = self.posting_datetime`. Transition writes use `frappe.get_doc(...).save(ignore_permissions=True)` so the booklet controller's widened validate is exercised (guarantees the `Sold → Depleted` transition is allowed and all other side-fields stay consistent). Add a `Comment` on the booklet `_("Depleted via {0}").format(self.name)` to preserve the "why" in the timeline (matches research.md §7).
  - `on_cancel`: symmetric reversal. For each row: `status = Available`, clear the three consumption-metadata fields via `db_set`. Per distinct booklet: recompute `consumed_count` / `remaining_count`. If a booklet's `status == Depleted` AND this entry was the original trigger (detected by finding the most-recent Consumption Entry that contains at least one coupon from the booklet — see research.md §6 for the exact rule), revert to `Sold`, clear `depleted_on`. If another later entry now holds the booklet at `consumed_count = 20`, the booklet stays `Depleted`. All-or-nothing: any pre-cancel data-integrity failure raises before any write.
- **Mode A + Mode B form UX** delivered as a client script (`public/js/purisol_coupon_consumption_entry.js`) that adds two dialogs / in-form widgets above the `coupons` grid:
  - Mode A: a booklet autocomplete + a call to the whitelisted `cx_purisol.cx_purisol.api.consumption.list_available_coupons(booklet)` that returns `[{coupon, page_number}]` for all `Available` coupons of that booklet. The client renders a checkbox list; "Add to Entry" appends one row per tick with `{coupon, booklet, customer}` (customer fetched client-side from the booklet record).
  - Mode B: a text input whose Enter handler splits on newlines, calls `cx_purisol.cx_purisol.api.consumption.resolve_coupons(coupon_numbers: list[str])` (batched whitelisted endpoint; one round trip for a pasted block), and for each resolved coupon appends a row; for each unresolved coupon, adds an inline red error line naming the missing coupon number (valid rows are preserved — FR-020 / FR-021 / edge case "multi-line paste with bad lines").
  - Both modes write into the same `coupons` grid. Removing a row in the grid before submit has no server-side side effect (draft state is not a reservation — spec edge case "draft listing coupons has no effect").
- **Whitelisted API (`cx_purisol/cx_purisol/api/consumption.py`)**:
  - `list_available_coupons(booklet: str) -> list[dict]` — permission-gated on `Purisol Administrator`; returns coupons of the given booklet whose `status == "Available"`, sorted by `page_number`.
  - `resolve_coupons(coupon_numbers: list[str]) -> {resolved: list[dict], unresolved: list[str]}` — permission-gated; a single round trip for pasted blocks. Server never side-effects — purely a read for UI preview. Submit-time validation (FR-030–FR-033) is authoritative.
- **Concurrency**: rely on per-coupon optimistic locks (`modified` stamp). Two concurrent submits that reference the same coupon — one succeeds; the other's `before_submit` reads a now-`Consumed` coupon and rejects with the already-consumed blocking error (FR-033). In the rare case that both `before_submit` reads see `Available` and both `on_submit` passes race to write, the second write fails with `frappe.TimestampMismatchError`, which Frappe rolls back the whole submit transaction for (FR-061). Pessimistic locking (`SELECT ... FOR UPDATE`) is not used — conflicts are rare at operational scale and the optimistic-lock error is clear enough.
- **Tests**:
  - Unit tests: `test_purisol_coupon_consumption_entry.py` (DocType-local — validate rules, duplicate-in-entry, empty child table); `test_purisol_coupon.py` widens to cover `Available → Consumed` and back; `test_purisol_coupon_booklet.py` widens to cover `Sold → Depleted` and `Depleted → Sold`.
  - API tests: `api/test_consumption.py` for `list_available_coupons` (permission, filtering, sort) and `resolve_coupons` (batched resolution, unresolved list).
  - Integration tests: `tests/test_consumption_flows.py` — one test per user story (Mode A single booklet, Mode B multi-booklet, mixed Mode A + Mode B, auto-deplete, auto-deplete across many entries) plus one test per rejection path in Story 4 (empty, duplicate in entry, unknown coupon, already consumed) plus cancel round-trip (full reversal) and a concurrent-submit race test.

## Technical Context

**Language/Version**: Python 3.10+ (Frappe server), JavaScript (Frappe client scripts).
**Primary Dependencies**: Frappe Framework 15.x, ERPNext 15.x (`Employee`, `Customer`, `User`). No new third-party libraries. Reuses Phase 1 DocTypes (`Purisol Coupon Booklet`, `Purisol Coupon`) and their existing reserved fields.
**Storage**: Frappe DocTypes on MariaDB via `frappe.db` / `frappe.get_doc`; no raw SQL writes. Two new custom DocTypes (one submittable parent + one child table) plus a reserved-empty discrepancy child-table stub. No changes to existing Purisol DocType JSON — only the controllers widen.
**Testing**: Frappe test framework (`frappe.tests.utils.FrappeTestCase`), invoked via `bench --site <test-site> run-tests --app cx_purisol`. Tests reuse the Phase-1/2/3 `tests/fixtures.py` helper — extended to seed one customer, one delivery man, one sold booklet, and `Purisol Coupon` rows in known `Available` state.
**Target Platform**: Linux server running Frappe Bench (gunicorn + RQ workers + MariaDB + Redis).
**Project Type**: Frappe custom app (`cx_purisol`) — adding three DocTypes (one submittable parent, one child table, one reserved child-table stub), widening two existing controllers, one whitelisted API module, and one client script for the dual-mode form.
**Performance Goals**:
- A typical end-of-day entry (10–20 coupons across 1–3 booklets) completes submit in under 2 s total, ending in under 90 s of administrator interaction (spec SC-001).
- Worst-case operational entry (~200 coupons one delivery man's full route) submits inside the default gunicorn 120 s window: per-coupon update is ≈ 4 field writes × 200 = 800 writes, plus 20 `COUNT(*)` booklet recomputes, well under the synchronous threshold.
- `list_available_coupons` reads at most 20 rows (single-booklet scope) — trivial.
- `resolve_coupons` on a pasted block of 200 numbers is a single `frappe.get_all` with an `IN (...)` filter — trivial.

**Constraints**:
- Atomic all-or-nothing submit (FR-034, FR-060) and atomic all-or-nothing cancel (FR-053, FR-060); no partial visibility of coupon or booklet state.
- Every multi-record write in submit and cancel must commit inside the Frappe request transaction; `frappe.throw` anywhere in the submit/cancel path must roll the whole thing back.
- Coupon state machine: permitted transitions `Available ↔ Consumed` only. Any other transition raises `frappe.ValidationError`.
- Booklet state machine transitions permitted by this phase (additive): `Sold → Depleted` (auto-depletion on submit), `Depleted → Sold` (auto-revert on cancel when this entry was the trigger and no other entry now holds the booklet at 20). `Depleted → In Stock|In Custody` remains forbidden — reopening a depleted booklet requires a new booklet (constitution III: terminal states are strictly terminal; `Depleted → Sold` here is a narrow, auditable revert path driven by an audit-trail-backed cancel, not a user-facing reopening).
- Every user-facing string wrapped in `frappe._()` (constitution IX); error messages use named placeholders so Arabic translation is unambiguous.
- Only `Purisol Administrator` can create/write/submit/cancel/amend the entry (FR-070); `received_by` is auto-stamped and non-editable (FR-071).
- **No** discrepancy record is created; **no** notification is emitted (FR-035, FR-044, SC-011). The seams exist but are reserved-empty.
- The `Purisol Coupon` form stays read-only for the three consumption-metadata fields — they are written only by the Consumption Entry controller, never by a human typing in the form.

**Scale/Scope**: Single shop, single administrator. Typical entry: 10–20 coupons. Worst realistic case: ~200 coupons per entry (one full delivery-man route). A few entries per day; cumulative dataset grows by ≈ 100–500 rows per day. Multi-branch / multi-currency / bulk-day operations of thousands of coupons are out of scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution version: **1.0.0** (10 principles). The plan template's Constitution Check section is still a placeholder (known TODO in the Sync Impact Report, carried from Phase 1); the 10 principles below are evaluated explicitly for this phase.

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Naming Convention | **PASS** | Both new DocTypes are `Purisol Coupon Consumption Entry` and `Purisol Coupon Consumption Item` — capital P, lowercase remainder, single trailing space before the descriptive name. The reserved-empty child-table stub is `Purisol Coupon Discrepancy Item` (same rule). No non-Purisol-prefixed custom DocType is introduced. |
| II | Leverage ERPNext Primitives | **PASS** | `delivery_man` is a Link to `Employee` (not `Purisol Delivery Man`); `received_by` is a Link to `User`; `customer` is fetched from the existing `Purisol Coupon Booklet.customer` which is already a Link to `Customer`. No custom Purisol customer or employee DocType is created. The submittable record of truth is a Purisol-owned DocType because no ERPNext primitive models "coupons handed in by a delivery man at end of day" — consumption is a Purisol domain concept, not an ERPNext one. Justification: coupons/booklets are Purisol-only entities; ERPNext has no analogous primitive (it is neither a stock movement, nor a payment, nor a journal entry — it is a physical-paper-to-digital record). |
| III | State Machine Enforcement | **PASS** | Coupon state machine (`Available ↔ Consumed`) is enforced in the coupon controller's `validate`; any other transition raises `frappe.ValidationError`. Booklet state machine adds exactly `(Sold, Depleted)` and `(Depleted, Sold)` with the latter narrowly gated to the Consumption Entry cancel path. Silent drift is impossible: the Consumption Entry controller calls `frappe.get_doc(...).save(ignore_permissions=True)` which re-runs the booklet `validate`, which enforces the transition set. The `Depleted → Sold` revert is audit-trail-backed (the cancel is itself a submittable action that writes to `tabVersion`) and only fires when the Consumption Entry being cancelled is the booklet's trigger-of-record; it is not a backdoor to reopen a genuinely-depleted booklet. The terminal-state rule (III.3) is preserved in spirit — the only way out of `Depleted` is cancelling the exact entry that put it there. |
| IV | Audit Trail by Default | **PASS** | `track_changes = 1` on both new DocTypes. The submittable Consumption Entry itself **is** the submittable record of truth for per-coupon state changes — coupon-level fields (`status`, `consumed_on`, `consumed_by_delivery_man`, `consumption_entry`) are written only as a consequence of the Consumption Entry's submit (per-coupon metadata preserved per constitution IV.3). Booklet aggregates (`consumed_count`, `remaining_count`, `status`, `depleted_on`) are a cache derived from the per-coupon source of truth; the recompute pass in `on_submit` / `on_cancel` guarantees they are never silently updated out-of-band. Every booklet that transitions to `Depleted` receives a `Comment` naming the triggering entry, so a later viewer can answer "why is this Depleted?" from the booklet alone (SC-010). |
| V | Error Handling Semantics | **PASS** | Phase 4's four validation categories are all **blocking** — empty child table, duplicate coupon in entry, unknown coupon, already-consumed coupon — and all use `frappe.throw(_("..."))` to raise `frappe.ValidationError` inside the submit transaction, rolling back every pending write. Phase 4 emits **zero** warning discrepancies; the `discrepancies_detected` child table stays empty and `has_warnings` stays `0` (FR-035). Silent success is impossible: every branch either persists the full atomic state change or throws. The "coupon from a non-Sold booklet" case is deliberately **not** a blocking error (edge case / assumption: deferred to Phase 5 as a warning); the Phase 4 submit succeeds and a later Phase 5 patch layers the warning in additively. |
| VI | Role Model | **PASS** | Only `Purisol Administrator` can create/write/submit/cancel/amend the Consumption Entry — enforced by the DocType's `permissions` rule. Both whitelisted API endpoints (`list_available_coupons`, `resolve_coupons`) begin with `frappe.only_for("Purisol Administrator")`. No new custom role introduced. Delivery men (Employees) are subjects of the operation, never actors: they appear as `delivery_man` (Link → Employee) on the entry and `consumed_by_delivery_man` on each coupon, but hold no system access in MVP (matches constitution VI). |
| VII | Notification Channel | **PASS** | Phase 4 emits **zero** notifications (FR-044, SC-011). The Consumption Entry's `on_submit` and `on_cancel` do not call any notification code. This preserves the dispatcher seam for Phase 6 — a future notification layer will subscribe to domain events (e.g. a booklet just transitioned to `Depleted`) without rewriting Phase 4's submit/cancel logic. |
| VIII | Background Jobs | **PASS** | A typical entry (10–20 coupons) updates ≈ 80 fields across coupons and ≈ 2 booklets' aggregate fields — well below the 100-record synchronous threshold. A worst-case 200-coupon entry issues 800 coupon-field writes plus 20 booklet recomputes — still within the gunicorn 120 s window and well-bounded. Enqueueing the submit in a background job is explicitly avoided (research.md §4): breaking the atomicity between the Consumption Entry's own submit and the coupon/booklet updates is worse than the minor latency of a 2 s synchronous submit. If a future phase introduces bulk backfills of thousands of coupons, the `on_submit` logic can be re-entered as an enqueued idempotent job without changing its contract. |
| IX | Localization | **PASS** | Every DocType label, form caption, mode-switcher label, validation message, dialog text, and Comment body is wrapped in `frappe._()`. Error messages use named placeholders (e.g., `_("Coupon {0} is already Consumed (recorded on entry {1}).").format(name, entry)`) so Arabic word order is preserved. Both LTR (English) and RTL (Arabic) render correctly — standard Frappe form widgets handle RTL automatically for Arabic locales. Arabic translations land in the existing `cx_purisol/translations/ar.csv`. |
| X | Testing Discipline | **PASS** | Unit tests: DocType validations (`test_purisol_coupon_consumption_entry.py`), coupon controller widening (`test_purisol_coupon.py`), booklet controller widening (`test_purisol_coupon_booklet.py`), API endpoints (`api/test_consumption.py`). Integration tests: one per user story + one per rejection path + cancel round-trip + concurrent-submit race (`tests/test_consumption_flows.py`). All use `FrappeTestCase`; seed fixtures extend the existing `tests/fixtures.py` helper. A clean-database run of `bench run-tests --app cx_purisol` is the phase's definition of "done". |

**No violations.** Complexity Tracking table is empty.

## Project Structure

### Documentation (this feature)

```text
specs/004-consumption-recording/
├── plan.md              # This file (/speckit.plan command output)
├── spec.md              # Feature specification (already written)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/
│   └── consumption-recording.md # Phase 1: behavioural contract for submit/cancel + Mode A/B APIs
├── checklists/          # (Spec-quality checklist — carried from earlier if present)
└── tasks.md             # Phase 2 output (/speckit.tasks command — NOT created here)
```

### Source Code (repository root)

```text
cx_purisol/                                                     # Git repo root; Frappe app package
├── cx_purisol/                                                 # Python package root
│   ├── hooks.py                                                # *** MODIFIED *** — no new doc_events; just keep Phase-3 hooks intact
│   ├── modules.txt                                             # Unchanged
│   ├── patches.txt                                             # *** MODIFIED *** — one Phase-4 widening patch
│   ├── patches/
│   │   └── v0_4_0/
│   │       ├── __init__.py
│   │       └── widen_states_for_consumption.py                 # *** NEW *** — no-op anchor patch (logs-only on fresh installs)
│   └── cx_purisol/                                             # Module folder ("Cx Purisol")
│       ├── doctype/
│       │   ├── purisol_coupon/                                 # *** MODIFIED ***
│       │   │   ├── purisol_coupon.py                           # Widen: Available ↔ Consumed transitions; permit controller-only metadata writes
│       │   │   └── test_purisol_coupon.py                      # *** MODIFIED *** — Phase-4 transition tests
│       │   ├── purisol_coupon_booklet/                         # *** MODIFIED ***
│       │   │   ├── purisol_coupon_booklet.py                   # Widen: add (Sold, Depleted), (Depleted, Sold)
│       │   │   └── test_purisol_coupon_booklet.py              # *** MODIFIED *** — Phase-4 transition tests
│       │   ├── purisol_coupon_consumption_entry/               # *** NEW *** — submittable
│       │   │   ├── __init__.py
│       │   │   ├── purisol_coupon_consumption_entry.json
│       │   │   ├── purisol_coupon_consumption_entry.py         # validate / before_submit / on_submit / on_cancel
│       │   │   ├── purisol_coupon_consumption_entry.js         # Mode A + Mode B form UX
│       │   │   └── test_purisol_coupon_consumption_entry.py    # Unit tests
│       │   ├── purisol_coupon_consumption_item/                # *** NEW *** — child table
│       │   │   ├── __init__.py
│       │   │   ├── purisol_coupon_consumption_item.json
│       │   │   └── purisol_coupon_consumption_item.py          # Empty controller (stub)
│       │   ├── purisol_coupon_discrepancy_item/                # *** NEW *** — reserved-empty child-table stub (Phase 5 fills)
│       │   │   ├── __init__.py
│       │   │   ├── purisol_coupon_discrepancy_item.json
│       │   │   └── purisol_coupon_discrepancy_item.py          # Empty controller (stub)
│       │   └── (existing Phase 1/2/3 DocTypes unchanged)
│       ├── api/
│       │   ├── __init__.py
│       │   ├── consumption.py                                  # *** NEW *** — list_available_coupons, resolve_coupons
│       │   ├── test_consumption.py                             # *** NEW *** — API unit tests
│       │   └── (existing sell_booklets.py, booklet_generation.py unchanged)
│       ├── sales_invoice/                                      # From Phase 3 — unchanged in this phase
│       ├── public/js/
│       │   └── purisol_coupon_booklet_list.js                  # From Phase 3 — unchanged
│       ├── report/                                             # From Phase 2 — unchanged in this phase
│       ├── tests/
│       │   ├── fixtures.py                                     # *** MODIFIED *** — extend seed helpers with "sell-and-ready-to-consume" flow
│       │   ├── test_consumption_flows.py                       # *** NEW *** — integration tests (Stories 1–4 + edge cases)
│       │   └── (existing Phase 1/2/3 tests unchanged)
│       └── fixtures/
│           └── (no new fixture files — permissions live in the new DocType JSONs; existing role.json unchanged)
└── specs/004-consumption-recording/                            # This plan
```

**Structure Decision**: Standard Frappe custom-app layout, consistent with Phases 1–3. Three new DocTypes are added — one submittable parent (`Purisol Coupon Consumption Entry`), one primary child table (`Purisol Coupon Consumption Item`), and one reserved-empty child-table stub (`Purisol Coupon Discrepancy Item`) so Phase 5 can land its warning structure additively without renaming the parent table. No new submodule or top-level sub-package is introduced; the whitelisted API module lives alongside existing Phase-1/3 API code. Tests split by the established convention: DocType-local tests under `doctype/.../test_*.py`, API-local tests co-located with the API module, integration tests under `tests/test_consumption_flows.py`. Controller-widening of `Purisol Coupon` and `Purisol Coupon Booklet` is strictly additive (new states / transitions / metadata writes from the Consumption Entry controller only). The patches file gains one post-model-sync entry (`cx_purisol.patches.v0_4_0.widen_states_for_consumption`) — a no-op anchor on fresh installs, required only on upgraded sites to clear cached validation state; matches the Phase-2/3 pattern.

## Complexity Tracking

> No constitutional violations; table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
