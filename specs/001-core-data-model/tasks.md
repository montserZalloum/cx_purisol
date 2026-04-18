---
description: "Task list for Core Data Model — Booklets & Coupons (Phase 1)"
---

# Tasks: Core Data Model — Booklets & Coupons

**Input**: Design documents from `/specs/001-core-data-model/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/booklet-generation.md, quickstart.md

**Tests**: Tests ARE requested (research.md §8 and constitution X explicitly mandate unit + integration tests for numbering logic and generation paths).

**Organization**: Tasks grouped by user story (US1=Generate Booklets P1 MVP, US2=Configure Settings P2, US3=Inspect Records P3) so each story can be implemented and validated independently.

**Path conventions**: Frappe custom-app single-module layout. All runtime code lives under `cx_purisol/cx_purisol/cx_purisol/` (repo root `/home/corex/aurevia-bench/apps/cx_purisol/`).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold the module directories and fixture-registration plumbing that every DocType and test in this feature will land into.

- [X] T001 Create DocType package skeleton directories `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_settings/`, `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/`, `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_coupon/` each with an empty `__init__.py` per plan.md Project Structure.
- [X] T002 Create API package skeleton `cx_purisol/cx_purisol/cx_purisol/api/__init__.py` and feature-level tests package `cx_purisol/cx_purisol/cx_purisol/tests/__init__.py` per plan.md Project Structure.
- [X] T003 [P] Create fixtures directory `cx_purisol/cx_purisol/cx_purisol/fixtures/` (no files yet — populated in Phase 2) per plan.md Project Structure.
- [X] T004 [P] Configure `ruff` (per CLAUDE.md Commands) by adding a minimal `[tool.ruff]` block to `cx_purisol/pyproject.toml` if not already present (line length, Python 3.10 target) to support `ruff check .` on new code.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create shared assets (role, fixture registration) that every user story depends on. No user-story task may begin until this phase is complete.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 Create `Purisol Administrator` role fixture `cx_purisol/cx_purisol/cx_purisol/fixtures/role.json` (single Role doc, `desk_access=1`) per research.md §6.
- [X] T006 Register fixtures in `cx_purisol/cx_purisol/hooks.py` by adding a `fixtures = [{"dt": "Role", "filters": [["name", "in", ["Purisol Administrator"]]]}]` entry so `bench migrate` installs the role per research.md §6.
- [X] T007 Add `@frappe.whitelist`-safe method allowlist entry in `cx_purisol/cx_purisol/hooks.py` (no-op if `override_whitelisted_methods` dict already exists) and ensure `app_name = "cx_purisol"` remains intact; no other hook changes in Phase 1.

**Checkpoint**: Role fixture + hooks wiring complete → user story implementation can now begin.

---

## Phase 3: User Story 1 - Generate a Batch of Booklets (Priority: P1) 🎯 MVP

**Goal**: Administrator invokes Generate Booklets with a quantity (and optional batch_id); the system creates N booklets (`WP-NNNNN`) and N×20 coupons (`CP-NNNNN`) with strict sequential numbering. Sync path for `quantity ≤ 20`, background job for `quantity > 20` with realtime progress feedback.

**Independent Test**: `frappe.call("cx_purisol.api.booklet_generation.purisol_generate_booklets", quantity=5)` returns the summary dict and leaves exactly 5 booklets (`WP-00001`…`WP-00005`) and 100 coupons (`CP-00001`…`CP-00100`) in the database, all with correct status and page numbers.

### Tests for User Story 1 ⚠️

> **Write these FIRST and confirm they FAIL before implementing the code under test.**

- [X] T008 [P] [US1] Unit tests for the WP↔CP mapping pure function in `cx_purisol/cx_purisol/cx_purisol/tests/test_numbering.py` covering booklet 1 → `CP-00001..CP-00020`, booklet 2 → `CP-00021..CP-00040`, booklet 50 → `CP-00981..CP-01000`, and a property check `first(N+1) == last(N) + 1` for N in 1..1000 (research.md §8 bullet 1).
- [X] T009 [P] [US1] Integration tests for synchronous generation in `cx_purisol/cx_purisol/cx_purisol/tests/test_booklet_generation.py`: `test_sync_generation_5_booklets`, `test_sync_generation_then_another_batch`, `test_generation_rejects_zero_quantity`, `test_generation_rejects_negative_quantity`, `test_generation_with_batch_id`, `test_generation_summary_shape` (research.md §8 bullet 2 + spec FR-014–FR-017, FR-020).
- [X] T010 [P] [US1] Integration test for asynchronous generation in `cx_purisol/cx_purisol/cx_purisol/tests/test_booklet_generation.py`: `test_async_generation_50_booklets` using `frappe.enqueue(..., now=True)` to drive the background-job function inline and assert the final WP→CP invariant + that `mode=="async"` is returned immediately (research.md §8 + spec FR-018, SC-004, SC-006).
- [X] T011 [P] [US1] DocType-local test `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/test_purisol_coupon_booklet.py` asserting computed fields (`first_coupon`, `last_coupon`, `total_coupons`, `consumed_count`, `remaining_count`) are populated on create and reject modification (spec FR-010, data-model.md §2 validation rules).
- [X] T012 [P] [US1] DocType-local test `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_coupon/test_purisol_coupon.py` asserting `coupon_number`, `booklet`, `page_number` immutability and `1 ≤ page_number ≤ 20` (spec FR-009, data-model.md §3 validation rules).

### Implementation for User Story 1

- [X] T013 [P] [US1] Create `Purisol Coupon Booklet` DocType JSON at `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/purisol_coupon_booklet.json` with `autoname="WP-.#####"`, `track_changes=1`, `is_submittable=0`, module "Cx Purisol", all fields per data-model.md §2 (including reserved-for-later-phase fields), status options `In Stock\nIn Custody\nSold\nDepleted`, and permissions for `Purisol Administrator` (read=1, write=1, create=0, delete=0).
- [X] T014 [P] [US1] Create `Purisol Coupon` DocType JSON at `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_coupon/purisol_coupon.json` with `autoname="CP-.#####"`, `track_changes=1`, `is_submittable=0`, all fields per data-model.md §3 (including reserved `consumed_on`, `consumed_by_delivery_man`, `consumption_entry`), status options `Available\nConsumed`, and `Purisol Administrator` permissions (read=1, write=0, create=0, delete=0).
- [X] T015 [US1] Implement `Purisol Coupon Booklet` controller at `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/purisol_coupon_booklet.py` with `autoname` hook copying `name` into `booklet_number` and computing `first_coupon`/`last_coupon` from the parsed integer K, and `validate` hook that: rejects any `status` other than `In Stock`, rejects modifications to `booklet_number`/`first_coupon`/`last_coupon`/`total_coupons`/`batch_id` after initial save (check `self.get_doc_before_save()`), and keeps `total_coupons=20`, `consumed_count=0`, `remaining_count=20` (data-model.md §2 validation rules; spec FR-009–FR-012).
- [X] T016 [US1] Implement `Purisol Coupon` controller at `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_coupon/purisol_coupon.py` with `autoname` hook copying `name` into `coupon_number`, and `validate` hook rejecting non-`Available` status, modifications to `booklet`/`page_number`/`coupon_number`, and `page_number` outside `[1, 20]` (data-model.md §3; spec FR-009, FR-011, FR-012).
- [X] T017 [US1] Implement the pure numbering helper `_coupon_range_for_booklet(k: int) -> tuple[str, str]` (returns `("CP-{(k-1)*20+1:05d}", "CP-{k*20:05d}")`) in `cx_purisol/cx_purisol/cx_purisol/api/booklet_generation.py` so the unit tests in T008 can import and exercise it without Frappe side effects (research.md §1).
- [X] T018 [US1] Implement the whitelisted entry point `purisol_generate_booklets(quantity, batch_id=None)` in `cx_purisol/cx_purisol/cx_purisol/api/booklet_generation.py` per contracts/booklet-generation.md: `frappe.only_for("Purisol Administrator")`, coerce/validate `quantity`, dispatch sync (`≤20`) vs `frappe.enqueue(..., queue="long", timeout=1800)` (`>20`), return the exact sync/async dict shapes defined in the contract (spec FR-014–FR-019a).
- [X] T019 [US1] Implement `_run_generate_booklets_job(quantity, batch_id, user)` in `cx_purisol/cx_purisol/cx_purisol/api/booklet_generation.py`: emit `status=started` realtime event, then for each of N booklets use `frappe.db.savepoint(...)` to create the booklet (via `make_autoname("WP-.#####")`) + its 20 coupons with pre-computed names `CP-((K-1)*20+1)..CP-(K*20)` (parsing K from the booklet name), call `frappe.db.set_value("Series", "CP", "current", K*20)` at batch end, `frappe.db.commit()` per booklet, emit throttled `status=progress` events (≤1%/500ms cadence), and emit `status=complete` or `status=failed` payloads matching contracts/booklet-generation.md (research.md §§1–4; spec FR-016, FR-017, FR-021, SC-006, SC-007).
- [X] T020 [US1] Add the client script `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/purisol_coupon_booklet.js` that registers a list-view "Generate Booklets" action which prompts for `quantity` + optional `batch_id`, calls `cx_purisol.api.booklet_generation.purisol_generate_booklets`, subscribes to `frappe.realtime.on("purisol_generate_booklets_progress", ...)` for progress/completion, and displays a summary dialog using the shared payload shape (spec FR-018, FR-019a; contracts/booklet-generation.md Progress events).
- [X] T021 [US1] Wrap every user-facing string in the API, controllers, and client script with `frappe._()` / `__()` (validation errors, progress/summary messages, dialog labels) per constitution IX and plan.md Technical Context "Constraints".

**Checkpoint**: User Story 1 is complete. Run the tests in T008–T012 and the quickstart.md §4–§7 steps; US1 should be independently deployable as MVP.

---

## Phase 4: User Story 2 - Configure System Settings (Priority: P2)

**Goal**: Administrator opens the `Purisol Settings` singleton and edits system-wide defaults (thresholds, item/price-list/account links, consumption-warning toggle). Singleton is structurally non-duplicable and non-deletable; only `Purisol Administrator` may read/write.

**Independent Test**: Navigate to `/app/purisol-settings`, confirm single editable record with defaults (`customer_low_stock_threshold=3`, `warehouse_low_stock_threshold=5`, `enable_consumption_warnings=1`), change a threshold, save, reload, confirm the change persists; a user without `Purisol Administrator` gets PermissionError.

### Tests for User Story 2 ⚠️

- [X] T022 [P] [US2] DocType-local tests in `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_settings/test_purisol_settings.py`: `test_singleton_exists_after_install` (`frappe.get_single("Purisol Settings")` returns a doc), `test_cannot_duplicate_singleton` (second `insert` raises), `test_defaults` (threshold/toggle defaults match data-model.md §1) per research.md §8 bullet 3 and spec FR-001, FR-002, SC-008.

### Implementation for User Story 2

- [X] T023 [US2] Create `Purisol Settings` DocType JSON at `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_settings/purisol_settings.json` with `issingle=1`, `track_changes=1`, module "Cx Purisol", all fields per data-model.md §1 (`coupon_item`, `default_price_list`, `customer_low_stock_threshold=3`, `warehouse_low_stock_threshold=5`, `employee_liability_account`, `discrepancy_offset_account`, `default_cash_account`, `enable_consumption_warnings=1`), and permissions restricting read/write to `Purisol Administrator` (no create/delete by construction) per spec FR-001–FR-003.
- [X] T024 [US2] Implement `Purisol Settings` controller at `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_settings/purisol_settings.py` with a minimal `validate` hook ensuring threshold fields are non-negative integers (data-model.md §1 Validation rules). No duplicate-prevention logic needed — `issingle=1` is the structural guarantee (research.md §5).
- [X] T025 [US2] Wrap all user-facing strings in the Settings DocType (field labels/descriptions via JSON and any validation messages in the controller) with `frappe._()` per constitution IX.

**Checkpoint**: User Story 2 complete alongside US1. Settings singleton editable by Administrator and loads on a fresh install with correct defaults.

---

## Phase 5: User Story 3 - Inspect Individual Booklet and Coupon Records (Priority: P3)

**Goal**: Administrator can browse booklet/coupon lists, open individual records, see all user-visible fields rendered with correct read-only flags, and filter booklets by `batch_id`.

**Independent Test**: Open booklet `WP-00003` → form shows `first_coupon=CP-00041`, `last_coupon=CP-00060`, counts 20/0/20, all computed fields read-only. Open any coupon → `coupon_number`, `booklet`, `page_number` read-only and correct. Filter booklet list by `batch_id` → returns only that batch.

### Tests for User Story 3 ⚠️

- [X] T026 [P] [US3] Add a list-filter integration test in `cx_purisol/cx_purisol/cx_purisol/tests/test_booklet_generation.py` (`test_booklets_filterable_by_batch_id`) that generates two batches with distinct `batch_id` values and asserts `frappe.get_all("Purisol Coupon Booklet", filters={"batch_id": "<id>"})` returns exactly the booklets from that batch (spec FR-020, acceptance scenario US3-3).

### Implementation for User Story 3

- [X] T027 [US3] Configure the `Purisol Coupon Booklet` list view by setting `in_list_view=1` in the DocType JSON (`cx_purisol/cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/purisol_coupon_booklet.json`) on `booklet_number`, `status`, `first_coupon`, `last_coupon`, `batch_id` and setting `search_fields = "batch_id,status"` so US3 acceptance scenario 3 (filter by batch_id) works out-of-the-box.
- [X] T028 [US3] Configure the `Purisol Coupon` list view by setting `in_list_view=1` on `coupon_number`, `booklet`, `page_number`, `status` in `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_coupon/purisol_coupon.json` and verify that the link filter from a booklet (child-list view) returns exactly 20 rows in page-number order (spec US3 acceptance scenario 2).
- [X] T029 [US3] Verify reserved-for-later-phase fields (`current_delivery_man`, `customer`, `sold_on`, `sales_invoice`, `depleted_on` on booklet; `consumed_on`, `consumed_by_delivery_man`, `consumption_entry` on coupon) are NOT marked `reqd=1` anywhere in the DocType JSONs so an empty Phase-1 booklet renders cleanly (spec edge case "Schema fields reserved for later phases").

**Checkpoint**: All three user stories independently functional. The quickstart.md walkthrough passes end-to-end on a clean site.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Installation validation, documentation, and cleanup spanning all user stories.

- [X] T030 Run the full feature test suite via `bench --site <test-site> run-tests --app cx_purisol` and confirm every test added in T008–T012, T022, T026 passes on a clean database per plan.md Testing and quickstart.md §8.
- [ ] T031 Execute the quickstart.md walkthrough (§§1–7) against a fresh site and record any step that fails or needs refinement back into `specs/001-core-data-model/quickstart.md` per plan.md Phase 1 workflow.
- [X] T032 [P] Run `ruff check .` from `cx_purisol/` (per CLAUDE.md Commands) and fix any lint findings in the new Python files from Phases 3–5.
- [X] T033 [P] Add a brief "Generate Booklets" operational note (how to invoke from the desk, expected progress feedback, how to recover from a stale `tabSeries` per quickstart.md §9 Troubleshooting) to `cx_purisol/docs/` (create the file if absent; do not touch existing CLAUDE.md or spec docs).
- [X] T034 Final audit: confirm every user-facing string in new Python / JS / JSON passes through `frappe._()` / `__()`, that `track_changes=1` is set on all three DocTypes, and that no Phase-1 code references later-phase DocTypes that do not yet exist (constitution IV, IX; plan.md Constitution Check).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1 — T001–T004)**: no dependencies; run first.
- **Foundational (Phase 2 — T005–T007)**: depends on Phase 1. **Blocks every user story.**
- **User Story 1 (Phase 3 — T008–T021)**: depends on Phase 2. MVP.
- **User Story 2 (Phase 4 — T022–T025)**: depends on Phase 2. Independent of US1 (Settings is not read by generation in Phase 1).
- **User Story 3 (Phase 5 — T026–T029)**: depends on Phase 3 tasks T013, T014 (DocType JSONs must exist before list-view config tweaks — same file edits).
- **Polish (Phase 6 — T030–T034)**: depends on all desired user stories being complete.

### User Story Dependencies

- **US1 (P1)**: After Foundational. Core MVP — all other stories can be deferred if only US1 is shipped.
- **US2 (P2)**: After Foundational. Independent of US1 — can run in parallel with US1 on a separate worker.
- **US3 (P3)**: After US1 (shares the booklet/coupon DocType JSON files created in T013/T014). Serial with US1 on those files; otherwise independent.

### Within Each User Story

- Tests (T008–T012, T022, T026) are written FIRST and must FAIL before the matching implementation tasks run.
- DocType JSON (T013, T014, T023) before controllers (T015, T016, T024).
- Pure helper (T017) before the API entry point (T018) before the job function (T019) before the client script (T020).
- Localization pass (T021, T025) is the last step inside each story.

### Parallel Opportunities

- **Phase 1**: T003 and T004 are `[P]`.
- **Phase 3 tests**: T008, T009, T010, T011, T012 are all `[P]` — five different files, no mutual dependencies.
- **Phase 3 DocType JSONs**: T013 and T014 are `[P]` (different files).
- **Phase 3 controllers**: T015 and T016 touch different files but each depends on its own DocType JSON from T013/T014; once those are done, T015 and T016 can run in parallel.
- **US2 vs US1**: Once Phase 2 is done, US2 tasks (T022–T025) can run in parallel with any US1 task because they touch a disjoint file set.
- **Phase 6**: T032 and T033 are `[P]`.

---

## Parallel Example: User Story 1 Tests

```bash
# Launch all US1 test files in parallel (they live in different files):
Task: "Unit tests for WP↔CP mapping in cx_purisol/cx_purisol/cx_purisol/tests/test_numbering.py"   # T008
Task: "Integration tests (sync) in cx_purisol/cx_purisol/cx_purisol/tests/test_booklet_generation.py"  # T009
Task: "Integration test (async) in cx_purisol/cx_purisol/cx_purisol/tests/test_booklet_generation.py"  # T010
Task: "DocType test in cx_purisol/cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/test_purisol_coupon_booklet.py"  # T011
Task: "DocType test in cx_purisol/cx_purisol/cx_purisol/doctype/purisol_coupon/test_purisol_coupon.py"  # T012
```

## Parallel Example: User Story 1 DocType JSONs

```bash
# Both JSONs are independent files — fan out:
Task: "Purisol Coupon Booklet DocType JSON in .../purisol_coupon_booklet.json"   # T013
Task: "Purisol Coupon DocType JSON in .../purisol_coupon.json"                   # T014
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (Setup) → T001–T004.
2. Phase 2 (Foundational) → T005–T007.
3. Phase 3 (US1) → T008–T021.
4. **STOP and VALIDATE**: run quickstart.md §§1, 4–7 and the Phase-3 tests. US1 = shipable MVP.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → MVP (generate booklets, numbering invariant, sync + async).
3. US2 → Settings singleton editable, defaults seeded.
4. US3 → list/filter/inspection UX confirmed.
5. Polish → lint, docs, full-run quickstart.

### Parallel Team Strategy

- Developer A: US1 (T008–T021) — heaviest thread.
- Developer B: US2 (T022–T025) — can start immediately after Phase 2; no file overlap with US1.
- Developer C: US3 (T026–T029) — must wait for T013/T014 to land, then appends list-view config.
- All converge on Phase 6.

---

## Notes

- `[P]` marks tasks that touch different files and have no dependency on other incomplete tasks.
- `[Story]` labels (`[US1]`, `[US2]`, `[US3]`) map each task to its story for traceability.
- Each user story is independently testable — stop at any checkpoint to validate before proceeding.
- Commit after each task or logical group; do not bundle across phases.
- Verify failing tests before writing implementation for the same behaviour.
- Avoid cross-story coupling: US2 must not read `Purisol Settings` from within US1's generation path in Phase 1 (spec Assumptions: "first generation can proceed with default values").
