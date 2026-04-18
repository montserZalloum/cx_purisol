---
description: "Task list for implementing Discrepancy Detection & Resolution (Phase 5)"
---

# Tasks: Discrepancy Detection & Resolution

**Input**: Design documents from `/specs/005-discrepancy-detection/`
**Prerequisites**: plan.md (✓), spec.md (✓), research.md (✓), data-model.md (✓), contracts/discrepancy.md (✓), quickstart.md (✓)

**Tests**: Tests are explicitly required — plan.md §Constitution Check X and spec's SC-001…SC-012 mandate unit, service, and integration tests. Test tasks are interleaved per user story.

**Organization**: Tasks are grouped by user story so each story can be implemented, merged, and demoed as an independent increment. Foundational work (three new DocTypes, widened Phase-4 stub, detection-service skeleton, consumption-entry widening, shared test fixtures) must land before any user story, because all six user stories share the same `Purisol Coupon Discrepancy` parent and the same submit transaction.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no unmet dependencies)
- **[Story]**: Maps task to the user story it serves (US1, US2, US3, US4, US5, US6)
- File paths are absolute to the repo root unless otherwise noted

## Path Conventions

Frappe custom-app layout, consistent with Phases 1–4:

- App package root: `cx_purisol/cx_purisol/` (Python) and `cx_purisol/public/js/` (assets)
- DocType folders: `cx_purisol/cx_purisol/doctype/<name>/`
- Server-side service modules: `cx_purisol/cx_purisol/api/` (not whitelisted in Phase 5)
- Shared test fixtures: `cx_purisol/cx_purisol/tests/`
- Patches: `cx_purisol/patches/v0_5_0/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffolding on disk so later tasks can create JSON / Python files in place.

- [x] T001 Create DocType folders and empty `__init__.py` at `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/__init__.py`, `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy_coupon/__init__.py`, and `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy_related_person/__init__.py`; confirm `cx_purisol/cx_purisol/api/__init__.py` and `cx_purisol/cx_purisol/tests/__init__.py` still exist (Phase-4 artefacts).
- [x] T002 Create Phase-5 anchor patch at `cx_purisol/patches/v0_5_0/__init__.py` (empty) and `cx_purisol/patches/v0_5_0/relax_consumption_entry_reserved_guards.py` (no-op `execute()` that prints a single `frappe.log_error`/`print` line naming the phase); append `cx_purisol.patches.v0_5_0.relax_consumption_entry_reserved_guards` to `cx_purisol/patches.txt` — per plan.md §10.2 and research.md §15.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Three new DocTypes (one submittable parent + two child tables), widen the Phase-4 `Purisol Coupon Discrepancy Item` stub, scaffold the detection-service module, relax the Phase-4 consumption-entry guards, and add the shared test-fixtures helpers that every user story builds on.

**⚠️ CRITICAL**: No user story work can begin until Phase 2 is complete — all six stories invoke the same `Purisol Coupon Discrepancy` parent or the same `Purisol Coupon Consumption Entry` submit seam.

- [x] T003 [P] Widen Phase-4 stub JSON at `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy_item/purisol_coupon_discrepancy_item.json` — add `discrepancy` Link → `Purisol Coupon Discrepancy` (reqd, in_list_view) and `discrepancy_type` Select (`Missing Coupons\nUnassigned Booklet`, read_only, `fetch_from = discrepancy.discrepancy_type`, in_list_view); update `field_order` to `["discrepancy", "discrepancy_type", "notes"]`; preserve `istable = 1` / `track_changes = 1` / `module = "Cx Purisol"` — per data-model §4 and research.md §13. Do NOT touch `purisol_coupon_discrepancy_item.py` (remains empty Document subclass).
- [x] T004 [P] Create child-table DocType JSON at `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy_coupon/purisol_coupon_discrepancy_coupon.json` with `istable = 1`, `track_changes = 1`, `module = "Cx Purisol"`, `engine = "InnoDB"`, fields `coupon` (Link Purisol Coupon, reqd, search-indexed, in_list_view), `coupon_number` (Data, read_only, `fetch_from = coupon.coupon_number`, in_list_view), `booklet` (Link Purisol Coupon Booklet, read_only, `fetch_from = coupon.booklet`), `notes` (Small Text) — per data-model §2.
- [x] T005 [P] Create empty controller stub at `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy_coupon/purisol_coupon_discrepancy_coupon.py` (`class PurisolCouponDiscrepancyCoupon(Document): pass`) — per data-model §2.3.
- [x] T006 [P] Create child-table DocType JSON at `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy_related_person/purisol_coupon_discrepancy_related_person.json` with `istable = 1`, `track_changes = 1`, `module = "Cx Purisol"`, `engine = "InnoDB"`, fields `delivery_man` (Link Employee, reqd, in_list_view), `role` (Select `Custody Holder\nSubmitted Adjacent Coupons`, reqd, in_list_view), `custody_entry` (Link Purisol Custody Entry, optional), `consumption_entry` (Link Purisol Coupon Consumption Entry, optional), `notes` (Small Text) — per data-model §3.
- [x] T007 [P] Create empty controller stub at `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy_related_person/purisol_coupon_discrepancy_related_person.py` (`class PurisolCouponDiscrepancyRelatedPerson(Document): pass`) — per data-model §3.3.
- [x] T008 Create parent DocType JSON at `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/purisol_coupon_discrepancy.json` with `is_submittable = 1`, `track_changes = 1`, `autoname = "PCD-.YYYY.-.#####"`, `naming_rule = "Expression (old style)"`, `engine = "InnoDB"`, `sort_field = "opened_on"`, `sort_order = "DESC"`, `search_fields = "booklet,customer,discrepancy_type"`, `title_field = "name"`, `module = "Cx Purisol"`; include all 21 fields from data-model §1.2 in order (`discrepancy_type`, `status`, `opened_on`, `resolved_on`, `section_break_detection`, `triggering_consumption_entry`, `booklet`, `customer`, `section_break_coupons`, `affected_coupons`, `section_break_related`, `related_delivery_men`, `section_break_resolution`, `liable_delivery_man`, `estimated_amount`, `resolution_action`, `resolution_notes`, `section_break_links`, `journal_entry`, `payment_entry`, `amended_from`); `permissions` grants `Purisol Administrator` full CRUD + submit/cancel/print/email/export/share/report (amend = 0, delete = 0) and `System Manager` read-only — per data-model §1.1 and §1.3.
- [x] T009 Create parent controller skeleton at `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/purisol_coupon_discrepancy.py` with (a) `PurisolCouponDiscrepancy(Document)` class, (b) `before_insert` defensive defaults (`status` → `"Open"` if empty; `opened_on` → `frappe.utils.now_datetime()` if empty), (c) `validate` placeholder with `pass`, (d) `before_submit` placeholder with `pass`, (e) `on_submit` placeholder with `pass`, (f) `on_cancel` placeholder with `pass`, (g) private module-level helpers `_create_liability_journal_entry(doc)` and `_create_cash_payment_entry(doc)` as `pass` stubs — filled by US3/US4/US5.
- [x] T010 [P] Relax Phase-4 defensive guards in `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/purisol_coupon_consumption_entry.py` — remove the two `frappe.throw` statements in `validate` that rejected non-zero `has_warnings` / non-empty `discrepancies_detected`; keep the three remaining checks (empty table, duplicate coupon, and the controller-owned ordering); replace the removed block with a single inline comment "# has_warnings and discrepancies_detected are controller-owned — populated by detect_for_entry in on_submit." — per data-model §5.1.
- [x] T011 [P] Update Phase-4 test assertions in `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/test_purisol_coupon_consumption_entry.py` — any test that previously asserted a defensive throw when setting `has_warnings = 1` or appending to `discrepancies_detected` is repurposed to assert the form fields remain `read_only = 1` on the loaded doc; tests that seed a fully-valid state and assert "after submit, has_warnings == 0 and discrepancies_detected is empty" stay as-is (those seeded states never trigger detection) — per research.md §10.
- [x] T012 [P] Create detection-service module skeleton at `cx_purisol/cx_purisol/api/discrepancy.py` exporting `detect_for_entry(entry) -> list[str]` returning `[]`, plus private helpers `_detect_missing_coupons(entry) -> list[str]` returning `[]`, `_detect_unassigned_booklets(entry) -> list[str]` returning `[]`, `_auto_populate_related_delivery_men(doc, entry, booklet) -> None` as `pass`, `_compute_estimated_amount(booklet, count) -> float` returning `0.0`, `_list_open_missing_coupon_names(booklet) -> set[str]` returning `set()` — all with full docstrings and type hints per contracts §2.1. Filled by US1/US2.
- [x] T013 Wire the Consumption Entry's `on_submit` to call the detection service — in `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/purisol_coupon_consumption_entry.py` after the existing Phase-4 coupon-flip and booklet-aggregate loops, add `from cx_purisol.cx_purisol.api.discrepancy import detect_for_entry`; call `created_names = detect_for_entry(self)`; if non-empty, set `self.has_warnings = 1`, append one `{"discrepancy": name}` row per name to `self.discrepancies_detected`, then call `self.db_update()` and iterate `self.discrepancies_detected` calling `row.db_insert()` on each — per data-model §5.2. Because helpers return `[]` in skeleton, this is a no-op until US1/US2 fill them in.
- [x] T014 [P] Extend `cx_purisol/cx_purisol/tests/fixtures.py` with four helpers used by Phase-5 tests: `configure_purisol_settings_accounts(employee_liability=None, discrepancy_offset=None, default_cash=None)` (writes to the singleton; creates default test Accounts if args omitted), `seed_open_discrepancy(*, discrepancy_type, booklet, customer=None, triggering_entry=None, affected_coupons=(), estimated_amount=0.0)` returns a draft `Purisol Coupon Discrepancy` name (bypasses the detection path for resolution-only tests — per research.md §14), `make_booklet_with_consumed_coupons(customer, employee, consumed_pages=(1,2))` drives a Sold booklet through a prior Consumption Entry so the next entry sees a non-empty consumed set, `make_in_stock_booklet()` creates an unsold booklet for US2 scenarios — all helpers module-public, all reuse Phase-1/2/3/4 helpers where possible.
- [x] T015 [P] Update `cx_purisol/hooks.py` — add `"Purisol Coupon Discrepancy": "public/js/purisol_coupon_discrepancy.js"` to `doctype_js`, add `"Purisol Coupon Discrepancy": "public/js/purisol_coupon_discrepancy_list.js"` to `doctype_list_js`; no new `doc_events`; fixture list unchanged — per data-model §10.3.

**Checkpoint**: Foundation ready. Detection service is a no-op; consumption entry submit still behaves like Phase 4. Every user story below can now start.

---

## Phase 3: User Story 1 — Auto-Detect Missing Coupons (Priority: P1) 🎯 MVP

**Goal**: During a Consumption Entry submit, detect any interior coupon-number gap inside the union of previously-consumed and now-consumed coupons of each affected booklet, and open one `Purisol Coupon Discrepancy` of type `Missing Coupons` per booklet listing the gap coupons. Idempotent across re-submits.

**Independent Test**: Seed one `Sold` booklet `WP-00001` with all 20 coupons `Available`, submit a first Consumption Entry for `CP-00001, CP-00002` (verify zero discrepancies), then submit a second Entry for `CP-00007, CP-00008`; verify exactly one `Purisol Coupon Discrepancy` of type `Missing Coupons`, status `Open`, `affected_coupons = [CP-00003..CP-00006]`, `estimated_amount = 4 × coupon_unit_price`, `triggering_consumption_entry` = second entry, and the second entry's `has_warnings = 1` with a single row in `discrepancies_detected`. See quickstart §1.

### Tests for User Story 1 ⚠️

> Write these first, ensure they FAIL against the foundational skeleton, then implement.

- [x] T016 [P] [US1] Unit test the gap algorithm in `cx_purisol/cx_purisol/api/test_discrepancy.py` — add `test_gap_interior`, `test_gap_none_when_contiguous`, `test_gap_none_below_min`, `test_gap_none_above_max`, `test_gap_dedup_against_open_discrepancy` (partial overlap — only the newly-revealed page becomes a new discrepancy), `test_gap_fully_covered_produces_no_discrepancy`. Each test calls `_detect_missing_coupons(entry)` directly after seeding a booklet in the desired state via `make_booklet_with_consumed_coupons` — per contracts §8.
- [x] T017 [P] [US1] Unit test `_compute_estimated_amount` in `cx_purisol/cx_purisol/api/test_discrepancy.py` — add `test_estimated_amount_from_invoice_line` (booklet with Sales Invoice → `rate / 20 × count`), `test_estimated_amount_from_price_list_fallback` (booklet with no invoice but settings has `coupon_item` + `default_price_list` + an `Item Price` → fallback path), `test_estimated_amount_zero_when_nothing_resolves` — per research.md §3 and contracts §8.
- [x] T018 [P] [US1] Unit test `_auto_populate_related_delivery_men` in `cx_purisol/cx_purisol/api/test_discrepancy.py` — add `test_related_persons_custody_holder_and_adjacent_30d` (booklet `In Custody` with a prior assign entry + a consumption entry from another employee 10 days ago → exactly two rows), `test_related_persons_skip_custody_holder_when_not_in_custody` (Sold booklet → only the adjacent row), `test_related_persons_30day_window_anchored_to_posting_date` (back-dated entry → window shifts), `test_related_persons_dedup_when_custody_holder_also_adjacent` (custody holder's prior consumption entry appears only once, role = `Custody Holder`) — per research.md §4.
- [x] T019 [P] [US1] Integration test the US1 acceptance scenarios in `cx_purisol/cx_purisol/tests/test_discrepancy_flows.py` — add `test_missing_coupons_scenario_1_gap_from_first_entry`, `test_missing_coupons_scenario_2_union_of_prior_and_current`, `test_missing_coupons_scenario_3_no_gap_when_contiguous`, `test_missing_coupons_scenario_4_dedup_against_open`, `test_missing_coupons_scenario_5_partial_overlap_new_coupon_only`, `test_missing_coupons_scenario_6_two_booklets_two_discrepancies` — per spec US1 acceptance scenarios 1–6.
- [x] T020 [P] [US1] Unit test Discrepancy parent immutability in `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/test_purisol_coupon_discrepancy.py` — add `test_discrepancy_type_immutable_on_edit`, `test_triggering_entry_immutable`, `test_booklet_immutable`, `test_customer_immutable`, `test_opened_on_immutable`, `test_affected_coupons_rows_immutable`, `test_related_delivery_men_rows_immutable`, `test_status_save_transition_open_to_under_review_allowed`, `test_status_save_transition_open_to_resolved_rejected`, `test_estimated_amount_recomputed_when_not_edited`, `test_estimated_amount_preserved_when_admin_edited` — per data-model §9.1 (V1–V9).

### Implementation for User Story 1

- [x] T021 [US1] Implement `_compute_estimated_amount(booklet, count)` in `cx_purisol/cx_purisol/api/discrepancy.py` — (1) if `booklet.sales_invoice` set, `frappe.get_all("Sales Invoice Item", {"parent": booklet.sales_invoice, "purisol_booklet": booklet.name}, ["rate"], limit=1)` → `rate / 20 × count`; (2) else read `frappe.get_cached_doc("Purisol Settings")`, if both `coupon_item` and `default_price_list` set, `frappe.get_all("Item Price", {"item_code": settings.coupon_item, "price_list": settings.default_price_list}, ["price_list_rate"], limit=1)` → `rate / 20 × count`; (3) else return `0.0` — per research.md §3.
- [x] T022 [US1] Implement `_auto_populate_related_delivery_men(doc, entry, booklet)` in `cx_purisol/cx_purisol/api/discrepancy.py` — (a) if `booklet.status == "In Custody"`, query the most-recent submitted `Purisol Custody Entry` whose child `Purisol Custody Entry Booklet` rows include `booklet.name` and whose `entry_type = "Assign"`, append a `Custody Holder` row with `delivery_man` + `custody_entry`; (b) query distinct delivery_men from submitted `Purisol Coupon Consumption Entry` records whose `Purisol Coupon Consumption Item` rows reference `booklet.name`, `posting_date >= entry.posting_date - 30d`, `name != entry.name`; for each distinct delivery_man (excluding the one already in the `Custody Holder` set) append a `Submitted Adjacent Coupons` row referencing the most-recent such entry; (c) handle the edge where the triggering entry itself is the only touchpoint → append one `Submitted Adjacent Coupons` row referencing `entry.name` per spec US6 scenario 6.2 — per research.md §4.
- [x] T023 [US1] Implement `_list_open_missing_coupon_names(booklet)` in `cx_purisol/cx_purisol/api/discrepancy.py` — `frappe.get_all("Purisol Coupon Discrepancy", {"booklet": booklet, "discrepancy_type": "Missing Coupons", "status": "Open", "docstatus": 0}, ["name"])`; for each, `frappe.get_all("Purisol Coupon Discrepancy Coupon", {"parent": <disc>, "parenttype": "Purisol Coupon Discrepancy"}, ["coupon"])`; flatten to a `set[str]` — per research.md §2 step 6.
- [x] T024 [US1] Implement `_detect_missing_coupons(entry)` in `cx_purisol/cx_purisol/api/discrepancy.py` per research.md §2 — for each distinct `booklet` in `entry.coupons`: read all 20 coupons via `frappe.get_all("Purisol Coupon", {"booklet": b}, ["name","page_number","status"])`; compute `consumed_pages`, skip if `< 2`; compute interior gap `{lo+1..hi-1} \ consumed_pages`; filter to `Available`; subtract `_list_open_missing_coupon_names(b)`; if non-empty, build a `Purisol Coupon Discrepancy` via the common builder (T026) and append to results. Return list of created names.
- [x] T025 [US1] Wire `detect_for_entry(entry)` in `cx_purisol/cx_purisol/api/discrepancy.py` to call `_detect_missing_coupons(entry) + _detect_unassigned_booklets(entry)` and return the concatenated list (the Unassigned helper remains `[]` until US2 lands) — per contracts §2.1.
- [x] T026 [US1] Extract a common discrepancy-builder helper `_build_and_insert_discrepancy(*, discrepancy_type, triggering_entry, booklet_doc, affected_coupon_names, customer)` in `cx_purisol/cx_purisol/api/discrepancy.py` that performs the sequence from data-model §6.3: `frappe.new_doc("Purisol Coupon Discrepancy")` → set `discrepancy_type`, `status = "Open"`, `opened_on = now_datetime()`, `triggering_consumption_entry`, `booklet`, `customer`; append one `affected_coupons` row per coupon name; call `_auto_populate_related_delivery_men(doc, triggering_entry, booklet_doc)`; set `estimated_amount = _compute_estimated_amount(booklet_doc, len(affected_coupon_names))`; `doc.insert(ignore_permissions=True)`; return `doc.name`. Used by both `_detect_missing_coupons` (US1) and `_detect_unassigned_booklets` (US2).
- [x] T027 [US1] Implement Discrepancy `validate` in `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/purisol_coupon_discrepancy.py` per data-model §9.1 — load `self.get_doc_before_save()`; if non-None (i.e., edit of an existing draft): reject any change to `discrepancy_type`, `triggering_consumption_entry`, `booklet`, `customer`, `opened_on` (V1–V5) with translated `frappe.throw`; reject row add/remove/reorder/edit in `affected_coupons` (V6) and `related_delivery_men` (V7) by comparing row counts + per-row `coupon`/`delivery_man`+`role` tuples; enforce `status` save-time transitions (V8) `{Open, Under Review}` only — any direct save-time write to a `Resolved - *` state throws (submit owns those transitions). For V9 (auto-recompute `estimated_amount`): track an insert-time sentinel (e.g., `self._initial_estimated_amount` cached in `before_insert`) and skip recompute if `self.estimated_amount != self._initial_estimated_amount` (admin edited) — else recompute via `_compute_estimated_amount(booklet, len(affected_coupons))`. All error messages wrapped in `frappe._()`.
- [x] T028 [US1] Verify Phase-4 `test_consumption_flows.py` still passes with the now-live detection path: the existing Phase-4 integration tests seed fully-valid scenarios (Sold booklet, all coupons Available, contiguous consumption) and must keep producing zero discrepancies — re-run `bench --site <test-site> run-tests --app cx_purisol --module cx_purisol.cx_purisol.tests.test_consumption_flows` and adjust only the assertions that read `has_warnings` / `discrepancies_detected` (spelling, not semantics) — per research.md §10.

**Checkpoint**: US1 independently functional. Missing-coupons detection fires; no resolution path yet but the discrepancies are queryable via the list view and the `discrepancies_detected` child table.

---

## Phase 4: User Story 2 — Auto-Detect Coupons From an Unassigned Booklet (Priority: P1)

**Goal**: For each coupon in a Consumption Entry whose parent booklet's status is not `Sold`, open one `Purisol Coupon Discrepancy` of type `Unassigned Booklet` (per-coupon, not per-booklet).

**Independent Test**: Seed booklet `WP-00002` `In Stock` with all coupons `Available`, submit a Consumption Entry for `CP-00025`; verify `CP-00025` transitions to `Consumed`, exactly one `Purisol Coupon Discrepancy` of type `Unassigned Booklet` is created with `customer = null`, `affected_coupons = [CP-00025]`, the entry's `has_warnings = 1`, and the post-submit modal fires. See quickstart §2.

### Tests for User Story 2 ⚠️

- [x] T029 [P] [US2] Unit test the per-coupon rule in `cx_purisol/cx_purisol/api/test_discrepancy.py` — add `test_unassigned_detection_in_stock_booklet`, `test_unassigned_detection_in_custody_booklet`, `test_unassigned_detection_no_discrepancy_when_sold`, `test_unassigned_detection_three_coupons_three_discrepancies` (all from the same `In Stock` booklet) — per spec US2 scenarios 1–3 and research.md §5.
- [x] T030 [P] [US2] Integration test US2 acceptance scenarios in `cx_purisol/cx_purisol/tests/test_discrepancy_flows.py` — add `test_unassigned_scenario_1_in_stock_booklet`, `test_unassigned_scenario_2_in_custody_booklet_not_sold`, `test_unassigned_scenario_3_three_coupons_three_records`, `test_unassigned_scenario_4_mixed_sold_and_unassigned_in_one_entry`, `test_unassigned_scenario_5_both_anomaly_types_in_one_entry` (the mixed-bag case combining US1's Missing Coupons with US2's Unassigned Booklet — per spec US2 scenario 5 and FR-020) — per spec US2 acceptance scenarios 1–5.
- [x] T031 [P] [US2] Contract test: "service does not mutate source records" in `cx_purisol/cx_purisol/api/test_discrepancy.py::test_no_mutation_of_source_records` — snapshot the `modified` stamp of the entry, every coupon, and the booklet before calling `detect_for_entry`; assert all three remain unchanged after the call (contracts §2.2 no-mutation guarantee, FR-021).

### Implementation for User Story 2

- [x] T032 [US2] Implement `_detect_unassigned_booklets(entry)` in `cx_purisol/cx_purisol/api/discrepancy.py` per research.md §5 — for each row in `entry.coupons`, fetch the booklet doc (use a per-call cache to avoid re-reading the same booklet); if `booklet.status != "Sold"`, call `_build_and_insert_discrepancy(discrepancy_type="Unassigned Booklet", triggering_entry=entry, booklet_doc=booklet, affected_coupon_names=[row.coupon], customer=None)` and collect the name. Return list of created names.

**Checkpoint**: Both P1 detection paths live. All Missing-Coupons and Unassigned-Booklet anomalies surface as `Open` draft discrepancies linked via `discrepancies_detected`. Resolution paths still TBD.

---

## Phase 5: User Story 3 — Resolve a Discrepancy as Administrator Error (Priority: P2)

**Goal**: Administrator submits an `Open` discrepancy with `resolution_action = "None"`; no financial document is created; the discrepancy transitions to `Resolved - Admin Error` and locks per ERPNext submittable semantics.

**Independent Test**: Use `seed_open_discrepancy(...)` to create one draft discrepancy, set `resolution_action = "None"`, optionally set `resolution_notes`, submit; verify `status == "Resolved - Admin Error"`, `resolved_on` stamped, `journal_entry` and `payment_entry` both null, and no `Journal Entry` / `Payment Entry` exists in the DB. Further edits and amendments are rejected. See quickstart §3.

### Tests for User Story 3 ⚠️

- [x] T033 [P] [US3] Unit tests in `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/test_purisol_coupon_discrepancy.py` — add `test_resolution_action_required_on_submit` (empty action → aggregated error with the `"Please choose a resolution action before submitting."` message — contracts §3.5 S1), `test_admin_error_resolution_success` (contracts §3.2), `test_admin_error_does_not_require_liable_delivery_man` (spec US3 scenario 2), `test_admin_error_preserves_resolution_notes` (spec US3 scenario 3, FR-016), `test_on_cancel_throws_for_resolved` (contracts §3.7, data-model §9.3 C1).
- [x] T034 [P] [US3] Integration test in `cx_purisol/cx_purisol/tests/test_discrepancy_flows.py` — add `test_admin_error_resolution_end_to_end` seeding via detection path (US1 or US2), opening the new discrepancy, setting `resolution_action = "None"` and `resolution_notes`, submitting, and asserting no financial documents exist and the record is locked — per spec US3 scenarios 1–3 and FR-011.
- [x] T035 [P] [US3] Amend-disabled test in `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/test_purisol_coupon_discrepancy.py::test_amend_disabled` — submit a discrepancy via Admin Error, attempt `frappe.get_doc(...).amend()` (or inspect permissions: `frappe.has_permission("Purisol Coupon Discrepancy", "amend")` is `False` for `Purisol Administrator`), assert the expected denial — per research.md §11 and FR-017.
- [x] T036 [P] [US3] Locked-after-submit test in `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/test_purisol_coupon_discrepancy.py::test_locked_after_submit` — submit a discrepancy, set any detection-time field on the now-submitted doc, call `.save()` and assert the standard "Cannot edit submitted document" `frappe.LinkValidationError`/`frappe.TimestampMismatchError`/`frappe.exceptions.ValidationError` is raised — per contracts §3.7 and FR-017.

### Implementation for User Story 3

- [x] T037 [US3] Implement the `resolution_action = ""` and `"None"` branches of `before_submit` in `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/purisol_coupon_discrepancy.py` per data-model §9.2 S1 + S4 — if `resolution_action` is empty or unset, `frappe.throw(_("Please choose a resolution action before submitting."))`; if `resolution_action == "None"`, set `self.status = "Resolved - Admin Error"` and `self.resolved_on = frappe.utils.now_datetime()`; no `journal_entry` / `payment_entry` writes. Branches for the two financial actions remain `pass` (filled by US4/US5).
- [x] T038 [US3] Implement `on_cancel` in `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/purisol_coupon_discrepancy.py` per data-model §1.5 + §9.3 C1 — `frappe.throw(_("Cancelling a resolved discrepancy is not permitted. Corrections must go through a reversing Journal Entry or Payment Entry."))`. All three resolution paths share this throw (discrepancy lifecycle is forward-only).

**Checkpoint**: US3 independently functional. Admin Error is the first closed-loop resolution path; discrepancies can be opened by US1/US2 detection and closed by US3's null-financial-effect path.

---

## Phase 6: User Story 4 — Resolve by Adding to Delivery Man's Liability Ledger (Priority: P2)

**Goal**: Administrator submits with `resolution_action = "Add to Liability Ledger"`, `liable_delivery_man` set, and the two required settings accounts configured; system creates a balanced Journal Entry (debit employee-liability with party/party_type, credit discrepancy-offset), links it on `self.journal_entry`, and the discrepancy transitions to `Resolved - Delivery Man Liable`.

**Independent Test**: Pre-configure `Purisol Settings.employee_liability_account` + `.discrepancy_offset_account`, seed an Open discrepancy with `estimated_amount = 40`, set `liable_delivery_man` and `resolution_action = "Add to Liability Ledger"`, submit; verify a submitted `Journal Entry` with correct debit/credit lines, the discrepancy's `journal_entry` link, `status = "Resolved - Delivery Man Liable"`, and the amount on the Employee Ledger. See quickstart §4.

### Tests for User Story 4 ⚠️

- [x] T039 [P] [US4] Unit tests in `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/test_purisol_coupon_discrepancy.py` — add `test_liability_missing_liable_delivery_man_rejects` (spec US4 scenario 2; contracts §3.5 S2a), `test_liability_missing_employee_liability_account_rejects` (spec US4 scenario 4; contracts §3.5 S2b), `test_liability_missing_discrepancy_offset_account_rejects` (contracts §3.5 S2c), `test_liability_aggregated_errors` (all three preconditions missing → one error listing all three — data-model §9.2 "errors aggregated"), `test_liability_uses_edited_estimated_amount` (spec US4 scenario 3 — admin edits to 35.00 → JE debits 35.00).
- [x] T040 [P] [US4] Integration test in `cx_purisol/cx_purisol/tests/test_discrepancy_flows.py::test_liability_resolution_creates_je` — end-to-end: detection path → open discrepancy → configure settings accounts → set `liable_delivery_man` → submit with `Add to Liability Ledger`; assert JE debit line (account = settings.employee_liability_account, party_type = "Employee", party = liable_delivery_man, amount = estimated_amount), credit line (account = settings.discrepancy_offset_account, amount = estimated_amount), JE `total_debit == total_credit == estimated_amount`, `discrepancy.journal_entry` holds the JE name, `discrepancy.status == "Resolved - Delivery Man Liable"`, `resolved_on` stamped — per spec US4 scenario 1 and contracts §3.3.

### Implementation for User Story 4

- [x] T041 [US4] Implement `_create_liability_journal_entry(doc)` in `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/purisol_coupon_discrepancy.py` per research.md §7 and data-model §1.6 — read `settings = frappe.get_cached_doc("Purisol Settings")`; build `frappe.new_doc("Journal Entry")` with `voucher_type = "Journal Entry"`, `posting_date = frappe.utils.today()`, `company = settings.get("company") or erpnext.get_default_company()`, `user_remark = _("Discrepancy {0} — liable {1}").format(doc.name, doc.liable_delivery_man)`; append two account rows (debit: `settings.employee_liability_account`, `party_type = "Employee"`, `party = doc.liable_delivery_man`, `debit_in_account_currency = doc.estimated_amount`; credit: `settings.discrepancy_offset_account`, `credit_in_account_currency = doc.estimated_amount`); `je.insert(ignore_permissions=True)` then `je.submit()`; return the JE document.
- [x] T042 [US4] Extend `before_submit` in `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/purisol_coupon_discrepancy.py` with the `"Add to Liability Ledger"` branch per data-model §9.2 S2a–S2c — collect aggregated errors if `liable_delivery_man` missing, `settings.employee_liability_account` empty, or `settings.discrepancy_offset_account` empty; if any, `frappe.throw` with the errors joined by `<br>`; else call `_create_liability_journal_entry(self)`, assign `self.journal_entry = je.name`, set `self.status = "Resolved - Delivery Man Liable"` and `self.resolved_on = frappe.utils.now_datetime()`. All error messages use `frappe._()`.

**Checkpoint**: US4 independently functional. The first of the two financial resolution paths is live; Employee Ledger / GL reports reflect liability-path submits.

---

## Phase 7: User Story 5 — Resolve via Immediate Cash Payment (Priority: P2)

**Goal**: Administrator submits with `resolution_action = "Immediate Cash Payment"`, `liable_delivery_man` set, and the two required settings accounts configured; system creates a Payment Entry (type `Receive`, from offset to cash, party = employee, references the discrepancy), links it on `self.payment_entry`, and the discrepancy transitions to `Resolved - Paid`.

**Independent Test**: Pre-configure `Purisol Settings.discrepancy_offset_account` + `.default_cash_account`, seed an Open discrepancy, set `liable_delivery_man` and `resolution_action = "Immediate Cash Payment"`, submit; verify a submitted `Payment Entry` with `payment_type = "Receive"`, `paid_from = discrepancy_offset_account`, `paid_to = default_cash_account`, `paid_amount = estimated_amount`, a references row pointing at the discrepancy, `status = "Resolved - Paid"`, and `resolved_on` stamped. See quickstart §5.

### Tests for User Story 5 ⚠️

- [x] T043 [P] [US5] Unit tests in `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/test_purisol_coupon_discrepancy.py` — add `test_cash_payment_missing_liable_delivery_man_rejects` (spec US5 scenario 2; contracts §3.5 S3a), `test_cash_payment_missing_discrepancy_offset_account_rejects` (contracts §3.5 S3b), `test_cash_payment_missing_default_cash_account_rejects` (spec US5 scenario 3; contracts §3.5 S3c), `test_cash_payment_aggregated_errors` (all preconditions missing → one aggregated error).
- [x] T044 [P] [US5] Integration test in `cx_purisol/cx_purisol/tests/test_discrepancy_flows.py::test_cash_payment_resolution_creates_pe` — end-to-end: detection path → open discrepancy → configure settings accounts → set `liable_delivery_man` → submit with `Immediate Cash Payment`; assert PE `payment_type == "Receive"`, `paid_from == settings.discrepancy_offset_account`, `paid_to == settings.default_cash_account`, `paid_amount == received_amount == estimated_amount`, `party_type == "Employee"`, `party == liable_delivery_man`, exactly one references row with `reference_doctype = "Purisol Coupon Discrepancy"` and `reference_name = discrepancy.name`; assert `discrepancy.payment_entry` holds the PE name, `status == "Resolved - Paid"`, `resolved_on` stamped — per spec US5 scenario 1 and contracts §3.4.
- [x] T045 [P] [US5] Parametrized precondition-error test in `cx_purisol/cx_purisol/tests/test_discrepancy_flows.py::test_resolution_missing_preconditions` — parametrize across the seven failure modes from contracts §3.5 (S1, S2a/b/c, S3a/b/c); each parameter asserts the exact localized message surfaces — per contracts §8.

### Implementation for User Story 5

- [x] T046 [US5] Implement `_create_cash_payment_entry(doc)` in `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/purisol_coupon_discrepancy.py` per research.md §8 and data-model §1.6 — read settings; build `frappe.new_doc("Payment Entry")` with `payment_type = "Receive"`, `posting_date = frappe.utils.today()`, `company = settings.get("company") or erpnext.get_default_company()`, `paid_from = settings.discrepancy_offset_account`, `paid_to = settings.default_cash_account`, `paid_amount = doc.estimated_amount`, `received_amount = doc.estimated_amount`, `party_type = "Employee"`, `party = doc.liable_delivery_man`; append one references row with `reference_doctype = "Purisol Coupon Discrepancy"`, `reference_name = doc.name`, `allocated_amount = doc.estimated_amount`; `pe.insert(ignore_permissions=True)` then `pe.submit()`; return the PE document.
- [x] T047 [US5] Extend `before_submit` in `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/purisol_coupon_discrepancy.py` with the `"Immediate Cash Payment"` branch per data-model §9.2 S3a–S3c — aggregated-error check for `liable_delivery_man`, `settings.discrepancy_offset_account`, `settings.default_cash_account`; on success call `_create_cash_payment_entry(self)`, assign `self.payment_entry = pe.name`, set `self.status = "Resolved - Paid"` and `self.resolved_on = frappe.utils.now_datetime()`.

**Checkpoint**: All three resolution paths live. A discrepancy opened by US1/US2 can be closed by US3, US4, or US5. Financial integration fully exercised.

---

## Phase 8: User Story 6 — Surface Discrepancies for Investigation (Priority: P3)

**Goal**: Add the three investigation-UX surfaces: post-submit modal on Consumption Entry, "Open Discrepancies" list-view default filter, and dynamic-visibility + related-men shortlist banner on the Discrepancy form. All three are thin client-side wrappers on top of US1–US5's server logic.

**Independent Test**: (a) Submit a Consumption Entry that creates a discrepancy → a non-blocking modal appears listing the new discrepancy with a click-through link. (b) Open the Discrepancy list → defaults to `status = "Open"`, sorted `opened_on desc`, with the five documented columns. (c) Open a Discrepancy form with `resolution_action = "Add to Liability Ledger"` → `liable_delivery_man` becomes visible and required; the related-men banner lists the shortlist. See quickstart §6.

### Tests for User Story 6 ⚠️

- [x] T048 [P] [US6] Unit test `related_delivery_men` population invariants in `cx_purisol/cx_purisol/api/test_discrepancy.py` — add `test_related_men_custody_only_when_in_custody` (spec US6 scenario 1 + 2), `test_related_men_30day_window_excludes_older_entries` (spec US6 scenario 3), `test_related_men_includes_triggering_delivery_man_when_sole_touchpoint` (research.md §4 final paragraph) — per FR-007 and SC-011.
- [x] T049 [P] [US6] Integration test for the modal + list surfaces in `cx_purisol/cx_purisol/tests/test_discrepancy_flows.py::test_us6_investigation_surfaces` — seed a booklet with prior custody and prior consumption; submit a triggering entry; assert the new discrepancy's `discrepancies_detected` row is present on the entry (proves the data the modal reads is correct — the actual modal is DOM-layer and out of `FrappeTestCase`'s scope); assert `frappe.get_list("Purisol Coupon Discrepancy", filters={"status": "Open"}, order_by="opened_on desc")` returns the expected ordering (proves the list-view contract's server-side shape — per spec US6 scenario 5, contracts §7).

### Implementation for User Story 6

- [x] T050 [P] [US6] Widen `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/purisol_coupon_consumption_entry.js` — add a `refresh` handler gated by `frm.doc.docstatus === 1 && frm.doc.has_warnings === 1 && frm.doc.discrepancies_detected.length > 0 && !frm.__discrepancy_modal_shown` that builds an HTML `<ul>` with one `<li>` per `discrepancies_detected` row (anchor `<a href="/app/purisol-coupon-discrepancy/{discrepancy}" target="_blank">{discrepancy}</a> — {discrepancy_type} — {booklet}` where `booklet` is read from a `frappe.db.get_value` fetch per row since the row only carries `discrepancy` + fetched `discrepancy_type`), calls `frappe.msgprint({ title: __("Discrepancies detected"), message: html, indicator: "orange", wide: true })`, then sets `frm.__discrepancy_modal_shown = true` — per contracts §6 and research.md §9.
- [x] T051 [P] [US6] Create `cx_purisol/public/js/purisol_coupon_discrepancy.js` — two `frappe.ui.form.on("Purisol Coupon Discrepancy", { ... })` concerns: (1) `refresh` + `resolution_action` handler toggles `liable_delivery_man` visibility/reqd (`None` → hidden & optional; the two financial actions → visible & reqd via `frm.set_df_property`); (2) `refresh` renders a read-only "Related Delivery Men" banner HTML above the form body listing each `related_delivery_men` row (delivery_man, role, click-through link to custody_entry or consumption_entry) so the admin can pick `liable_delivery_man` with one click — per plan.md client-script section. All user-facing strings via `__()`.
- [x] T052 [P] [US6] Create `cx_purisol/public/js/purisol_coupon_discrepancy_list.js` — set `frappe.listview_settings["Purisol Coupon Discrepancy"] = { onload(listview) { if (listview.filter_area.is_empty()) listview.filter_area.add([["Purisol Coupon Discrepancy", "status", "=", "Open"]]); } }` — per contracts §7 and research.md §12. Default sort already ships from the DocType JSON (`sort_field = "opened_on"`, `sort_order = "DESC"`).
- [x] T053 [P] [US6] Add Arabic translations for Phase-5 user-facing strings to `cx_purisol/translations/ar.csv` — every new error message from `before_submit`, `on_cancel`, `validate` immutability/transition checks; select-option labels (`Missing Coupons`, `Unassigned Booklet`, `Open`, `Under Review`, `Resolved - Admin Error`, `Resolved - Delivery Man Liable`, `Resolved - Paid`, `Custody Holder`, `Submitted Adjacent Coupons`, `None`, `Add to Liability Ledger`, `Immediate Cash Payment`); the modal title and item template used in T050 — per constitution IX.

**Checkpoint**: All six user stories complete. The system detects, surfaces, and resolves discrepancies end-to-end.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Final cleanup, cross-story validation, and quickstart walkthrough.

- [ ] T054 [P] Run the quickstart walkthrough (§0–§7) on a dev site: configure Purisol Settings accounts, trigger one Missing Coupons discrepancy, one Unassigned Booklet discrepancy, resolve one via `None`, one via `Add to Liability Ledger`, one via `Immediate Cash Payment`, verify the list view defaults and modal behaviour, attempt amend on a resolved record — every step should match the documented outcomes.
- [ ] T055 [P] Run the full test suite on a clean site: `bench --site <test-site> run-tests --app cx_purisol` — green run is the phase's definition of done. Verify Phase-1/2/3/4 tests still pass unchanged except for the Phase-4 assertions updated in T011.
- [x] T056 [P] Code-quality sweep on Phase-5 files: `ruff check cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy{,_coupon,_related_person}/ cx_purisol/cx_purisol/api/discrepancy.py cx_purisol/cx_purisol/api/test_discrepancy.py cx_purisol/cx_purisol/tests/test_discrepancy_flows.py cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/ cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy_item/`; resolve every lint finding.
- [x] T057 [P] Refresh `CLAUDE.md` "Active Technologies" section to mark 005-discrepancy-detection as implemented (not just planned); keep the existing Phase-5 tech-stack entry since it's already current.
- [x] T058 Verify constitution-X testing discipline: every SC-001…SC-012 from spec has ≥ 1 corresponding test (grep `test_discrepancy_flows.py`, `test_purisol_coupon_discrepancy.py`, `test_discrepancy.py`); spot-check each acceptance scenario of US1–US6 has a corresponding integration test; if any SC has no test, add one before declaring done.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. Blocks all user stories.
- **US1 (Phase 3) — P1 / MVP**: Depends on Phase 2. Independent of US2–US6. First delivery slice.
- **US2 (Phase 4) — P1**: Depends on Phase 2. Can run parallel to US1 (different detection helper; shares `_build_and_insert_discrepancy` in T026 which lives in US1's phase — US2 consumes that helper).
- **US3 (Phase 5) — P2**: Depends on Phase 2. Can run parallel to US1/US2.
- **US4 (Phase 6) — P2**: Depends on Phase 2 and on US3 (extends the same `before_submit` added in T037).
- **US5 (Phase 7) — P2**: Depends on Phase 2 and on US3 (extends the same `before_submit`). Independent of US4.
- **US6 (Phase 8) — P3**: Depends on Phase 2 (JSON) and gains full behavioural coverage once US1–US5 are live. The client-script tasks T050–T053 are pure JS/translations and technically can run after Phase 2 alone, but the integration test T049 depends on end-to-end detection + resolution working.
- **Polish (Phase 9)**: Depends on all desired user stories.

### User Story Dependencies

- **US1 (Missing Coupons)** is the MVP. Ship-first candidate.
- **US2 (Unassigned Booklet)** — same priority tier, but depends on the common builder `_build_and_insert_discrepancy` introduced in US1's T026. US2 work can start in parallel with US1 once T026 is drafted.
- **US3 (Admin Error)** is the lightest resolution path and should ship before US4/US5 because both financial paths share `before_submit` with US3 and need it shaped first.
- **US4 and US5** are independent resolution paths that can be developed in parallel after US3's `before_submit` skeleton is in place.
- **US6** layers UX on top of US1–US5 and can be scheduled last; its three client-side concerns (T050/T051/T052/T053) are all independently parallelizable.

### Within Each User Story

- Tests (T016–T020 for US1, etc.) are written first and should FAIL against the skeleton before implementation starts.
- Service helpers before detection entrypoints (T021–T023 before T024).
- The shared builder (T026) lands early in US1 so US2's T032 can reuse it.
- Controller lifecycle hooks (T027, T037, T038, T042, T047) layer onto the same file — land them in the documented order so merges are linear.

### Parallel Opportunities

- Phase 1 T001/T002 are sequential on the same `patches.txt` file — don't parallelize.
- Phase 2 T003, T004, T006, T010, T011, T012, T014, T015 operate on disjoint files and are all `[P]`. T008 (parent JSON) and T009 (parent controller) must sequence after T003–T007 (they reference the child DocTypes) but can run parallel to each other on disjoint files. T013 (wire consumption entry) must sequence after T010 and T012.
- Within US1: T016–T020 are all on separate test files / distinct test classes → all `[P]`. Implementation tasks T021–T023 are all in `api/discrepancy.py` — sequence them (same file). T027 is on a different file → `[P]` with T021–T023 but blocked by the helpers until end-to-end integration test T019 runs.
- Within US3/US4/US5: the `before_submit` branches all edit the same file (`purisol_coupon_discrepancy.py`) — do not parallelize T037/T042/T047. The helper additions (T041, T046) are in the same file too. All US3–US5 **test** files are distinct or additive and can parallelize.
- Within US6: T050 (consumption-entry JS), T051 (new discrepancy JS), T052 (new list JS), T053 (translations) all operate on disjoint files → fully `[P]`.

---

## Parallel Example: Phase 2 Foundational

```bash
# Launch the independent foundational JSON and test-fixture tasks together:
Task: "Widen Phase-4 stub JSON — purisol_coupon_discrepancy_item.json" (T003)
Task: "Create child-table JSON — purisol_coupon_discrepancy_coupon.json" (T004)
Task: "Create child-table JSON — purisol_coupon_discrepancy_related_person.json" (T006)
Task: "Relax Phase-4 guards in purisol_coupon_consumption_entry.py" (T010)
Task: "Create detection-service skeleton — api/discrepancy.py" (T012)
Task: "Extend fixtures.py with Phase-5 helpers" (T014)
Task: "Update hooks.py — doctype_js + doctype_list_js" (T015)
```

## Parallel Example: User Story 1 Tests

```bash
Task: "Unit tests — gap algorithm edge cases in api/test_discrepancy.py" (T016)
Task: "Unit tests — estimated_amount fallback cascade" (T017)
Task: "Unit tests — related_delivery_men auto-populate" (T018)
Task: "Integration tests — US1 acceptance scenarios 1–6" (T019)
Task: "Unit tests — Discrepancy parent immutability V1–V9" (T020)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks every story)
3. Complete Phase 3: US1 (Missing Coupons detection)
4. **STOP and VALIDATE**: Submit the two-entry scenario from quickstart §1; verify one `Open` discrepancy of type `Missing Coupons` is created with the right `affected_coupons`, `estimated_amount`, and `related_delivery_men`.
5. Deploy / demo as MVP. Resolution still TBD — but detection is the single highest-value behaviour (spec: "P1 because this is the one capability whose absence would make the whole phase not worth shipping").

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. Add US1 (Missing Coupons) → test + demo (MVP).
3. Add US2 (Unassigned Booklet) → test + demo (both P1 anomalies covered).
4. Add US3 (Admin Error resolution) → test + demo (closed-loop, no financials yet).
5. Add US4 (Liability Ledger) → test + demo (first financial path).
6. Add US5 (Cash Payment) → test + demo (second financial path).
7. Add US6 (UX surfaces) → test + demo (investigation aids).
8. Polish + quickstart walkthrough + full test suite.

### Parallel Team Strategy

With multiple developers after Phase 2 completes:

- **Dev A**: US1 (includes the shared `_build_and_insert_discrepancy` builder, T026) — other US tasks wait on T026 in particular.
- **Dev B**: US2 — starts as soon as T026 is drafted; integration tests wait on US1 detection helpers landing.
- **Dev C**: US3 — independent; lands the `before_submit` + `on_cancel` skeleton that US4/US5 extend.
- After US3: **Dev B / Dev C** split US4 and US5.
- **Dev A/B/C**: split US6's four independent JS/translation tasks.

---

## Notes

- Every Phase-5 user-facing string (error message, select option, modal text, translations) passes through `frappe._()` / `__()` — constitution IX.
- Phase 5 adds zero new roles, zero new custom fields, zero whitelisted endpoints, zero new fixture files beyond the translation widening in T053.
- The detection service is deliberately a non-whitelisted internal module — no external attack surface.
- Amend on `Purisol Coupon Discrepancy` is permanently disabled (JSON permission `amend = 0` plus `on_cancel` throw) per FR-017 and constitution IV.
- `db_update` + `db_insert` in T013 are chosen over `self.save()` to avoid triggering a recursive `validate`/`on_submit` pass during the consumption entry's own `on_submit` — per data-model §5.2.
- Failure in any discrepancy `.insert()` during detection rolls back the Consumption Entry's whole `on_submit` transaction — the atomic "entry + its discrepancies commit together or neither does" guarantee from FR-001 + FR-002 hinges on this. See research.md §1.
- Resolved discrepancies are **not** included in the Missing-Coupons dedup exclusion set (`_list_open_missing_coupon_names` filters on `status = "Open"` only) — this is spec-intended so that a physically-still-present gap can be re-flagged after an Admin-Error resolution.
- Every task checkbox is `- [ ]` until the task is complete. Mark `- [x]` on completion (same convention as Phases 1–4 tasks.md).
- Commit after each task or logical group; do not batch across stories.
- When in doubt about a precondition or guarantee, the authoritative source is `contracts/discrepancy.md` — it captures the observable contracts as the developer-facing acceptance layer.
