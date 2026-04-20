---

description: "Phase 8 — Dashboard task list"
---

# Tasks: Dashboard (Phase 8)

**Input**: Design documents from `/specs/008-dashboard/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/dashboard.md, quickstart.md (all present)

**Tests**: REQUIRED — the plan, data-model, constitution Principle X, and per-bundle "Independent Test" criteria all mandate Frappe `FrappeTestCase` integration tests; the contracts also require a per-report unit test for the new `Customers Low on Coupons` report.

**Organization**: Tasks are grouped by user story. Each user story phase is independently completable, independently testable, and shippable as an MVP increment per the spec's three-bundle delivery model (SC-009).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Different file from any other task in the same phase, no in-phase dependency on an incomplete task — safe to run in parallel.
- **[Story]**: `[US1]`, `[US2]`, or `[US3]` for user-story-phase tasks; absent for Setup, Foundational, and Polish phases.
- File paths below are absolute relative to the repo root `/home/corex/aurevia-bench/apps/cx_purisol/`.

## Path Conventions

Standard Frappe custom-app layout (consistent with Phases 1–7):

- Python modules: `cx_purisol/cx_purisol/` (the inner `cx_purisol` package mirrors the Frappe module folder)
- Fixtures: `cx_purisol/fixtures/`
- Reports: `cx_purisol/cx_purisol/report/<report_name>/`
- Patches: `cx_purisol/patches/v<phase>_0/`
- Tests: `cx_purisol/cx_purisol/tests/`
- Translations: `cx_purisol/translations/`
- App-level files: `cx_purisol/hooks.py`, `cx_purisol/patches.txt`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Per-phase version-marker patch anchor (matches Phase-2/3/4/5/6/7 convention).

- [X] T001 Create `cx_purisol/patches/v0_8_0/` directory with empty `cx_purisol/patches/v0_8_0/__init__.py`
- [X] T002 Create no-op patch file `cx_purisol/patches/v0_8_0/add_dashboard_widgets.py` containing an `execute()` function with a docstring explaining that widgets migrate via `bench migrate`'s standard fixture loader and the patch is a version-marker anchor only (per contracts/dashboard.md §Patches Anchor)
- [X] T003 [P] Append `cx_purisol.patches.v0_8_0.add_dashboard_widgets` to the `[post_model_sync]` section of `cx_purisol/patches.txt`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Cross-bundle plumbing that EVERY user story depends on — the role gate (FR-003), the default-landing mapping (FR-002), the fixtures-export registration, and the test-file scaffolding. No user-story task can begin until Phase 2 is complete.

**⚠️ CRITICAL**: T004, T005, and T006 below MUST be merged before any US1/US2/US3 task starts.

- [X] T004 [P] Add `role_home_page = {"Purisol Administrator": "مياه نبع النعيم"}` to `cx_purisol/hooks.py` AND extend the existing `fixtures` list in the same file with two new entries — one `{"dt": "Number Card", "filters": [["name", "in", [...]]]}` listing the four Number Card record names, and one `{"dt": "Dashboard Chart", "filters": [["name", "in", [...]]]}` listing the four Dashboard Chart record names (per contracts/dashboard.md §Fixtures Registration)
- [X] T005 [P] Update `cx_purisol/fixtures/workspace.json` to set `"roles": [{"role": "Purisol Administrator"}]` on the `مياه نبع النعيم` workspace record (per contracts/dashboard.md §Workspace Role Gate); leave `charts`, `number_cards`, `quick_lists`, and `content` as empty arrays / minimal placeholder for now (each user-story phase fills its slot)
- [X] T006 [P] Create `cx_purisol/cx_purisol/tests/test_dashboard.py` with a `TestDashboard(FrappeTestCase)` class scaffold containing: (a) `setUp` that imports the Phase-7 `report_seed` helper, (b) `test_workspace_exists_after_migrate` asserting the `مياه نبع النعيم` workspace loads with `roles = [{"role": "Purisol Administrator"}]`, (c) `test_role_gate_blocks_non_admin` that creates a non-admin user and asserts `frappe.PermissionError` on `frappe.get_doc("Workspace", "مياه نبع النعيم")` per research §17, (d) `test_default_landing_for_admin` asserting `frappe.get_hooks("role_home_page")` resolves the Purisol Administrator role to the workspace name

**Checkpoint**: Foundation ready — US1, US2, US3 implementation can now proceed (sequentially within each story for files they share, in parallel across different files).

---

## Phase 3: User Story 1 — Morning Operational Health View (Priority: P1) 🎯 MVP

**Goal**: Deliver Bundle 1 (5 widgets — W1, W2a, W2b, W3, W7) so the Administrator's morning login lands on a dashboard that answers: how many booklets are on the shelf, who's holding what, how many are actively sold, and how many coupons came in today per delivery man.

**Independent Test**: Seed booklets across all four statuses (some In Stock, some In Custody distributed across 3 delivery men, some Sold), seed today's consumption entries for several delivery men, log in as a `Purisol Administrator` user with no personal home preference. Verify (a) the user lands on the dashboard automatically, (b) W1/W2a/W3 cards show correct counts, (c) W2b chart shows one bar per holder with correct counts, (d) W7 chart shows today's per-delivery-man consumption summing to the total, and (e) clicking each widget drills through to the correctly filtered list/report. Bundle is shippable on its own — the Risk and Follow-up bundles are not required.

### Implementation for User Story 1

- [X] T007 [P] [US1] Create `cx_purisol/fixtures/number_card.json` containing three Number Card fixture records — `Purisol — Booklets In Stock` (W1), `Purisol — Booklets In Custody` (W2a), `Purisol — Active Sold Booklets` (W3) — each with `function = "Count"`, `document_type = "Purisol Coupon Booklet"`, `is_public = 1`, `cache = 0`, `type = "Document Type"`, and the `filters_json` per contracts/dashboard.md §W1/§W2a/§W3
- [X] T008 [P] [US1] Create `cx_purisol/fixtures/dashboard_chart.json` containing two Dashboard Chart fixture records — `Purisol — In-Custody Breakdown` (W2b: `chart_type = "Group By"`, `document_type = "Purisol Coupon Booklet"`, `group_by_based_on = "current_delivery_man"`, `group_by_type = "Count"`, `filters_json` per contracts §W2b) and `Purisol — Today's Consumption` (W7: `chart_type = "Report"`, `report_name = "Daily Delivery Man Summary"`, `x_field = "delivery_man"`, `y_axis = [{"y_field": "coupons_submitted", "color": "#449CF0"}]`, `dynamic_filters_json = '{"from_date":"Today","to_date":"Today"}'`, `cache = 0`, `is_public = 1`, `type = "Bar"` per contracts §W7)
- [X] T009 [US1] Update `cx_purisol/fixtures/workspace.json` to (a) populate `number_cards` with three entries `{"number_card_name": "Purisol — Booklets In Stock"}`, `{"number_card_name": "Purisol — Booklets In Custody"}`, `{"number_card_name": "Purisol — Active Sold Booklets"}`, (b) populate `charts` with `{"chart_name": "Purisol — In-Custody Breakdown"}` and `{"chart_name": "Purisol — Today's Consumption"}`, and (c) restructure the `content` field's escaped-JSON-string to include the Operations bundle blocks per contracts/dashboard.md §Workspace Content Layout (header "Operations" + 3 cards + 2 charts + spacer); preserve any existing top-level header block until US2/US3 augment further
- [X] T010 [P] [US1] Append rows to `cx_purisol/translations/ar.csv` for the new English strings used in this bundle: `Operations`, `Booklets In Stock`, `Booklets In Custody`, `Active Sold Booklets`, `In-Custody Breakdown`, `Today's Consumption` — each with the Arabic translation from contracts/dashboard.md §Localisation
- [X] T011 [P] [US1] Add five US1 acceptance-scenario tests to `cx_purisol/cx_purisol/tests/test_dashboard.py`: `test_us1_default_landing_redirects_admin`, `test_us1_booklet_status_counts_match_seed` (W1/W2a/W3 against 17/42/120 seed), `test_us1_in_custody_breakdown_per_delivery_man` (W2b: A=20, B=15, C=7), `test_us1_today_consumption_per_delivery_man` (W7: bars sum to 23 across 3 delivery men), `test_us1_widget_click_through_filters` (assert each widget's `filters_json` resolves to the correct list-view URL per contracts §W1/§W2a/§W2b/§W3/§W7)

**Checkpoint**: User Story 1 is fully functional and testable independently. The Operations row of the dashboard renders, drives the morning ritual, and replaces five-to-ten minutes of manual list navigation with one glance. Ship as MVP.

---

## Phase 4: User Story 2 — Financial Risk Watchlist (Priority: P2)

**Goal**: Deliver Bundle 2 (3 widgets — W5a, W5b, W6) so the Administrator can see at a glance whether any open discrepancies need attention and how much money is currently owed by delivery men.

**Independent Test**: Seed two Open discrepancies on different dates, one Resolved-Liable discrepancy producing a known liability journal entry, one Resolved-Paid discrepancy partially offsetting that liability. Open the dashboard. Verify (a) W5a count = 2 with the Red accent, (b) W5b lists exactly the two open discrepancies in `modified desc` order, (c) W6 chart shows one bar per delivery man with the correct `open_balance` from the Phase-7 report, (d) totals reconcile with the Phase-7 `Delivery Man Liability Balance` report row-by-row (SC-004), (e) clicking each widget drills through correctly. Bundle is shippable on its own — Operations and Follow-up bundles are not required.

### Implementation for User Story 2

- [X] T012 [P] [US2] Append a fourth Number Card record `Purisol — Open Discrepancies` (W5a) to `cx_purisol/fixtures/number_card.json` — `function = "Count"`, `document_type = "Purisol Coupon Discrepancy"`, `color = "Red"`, `filters_json` includes BOTH `["status","=","Open"]` AND `["docstatus","=",1]` per contracts/dashboard.md §W5a (the docstatus filter excludes cancelled discrepancies)
- [X] T013 [P] [US2] Append a third Dashboard Chart record `Purisol — Outstanding Liabilities` (W6) to `cx_purisol/fixtures/dashboard_chart.json` — `chart_type = "Report"`, `report_name = "Delivery Man Liability Balance"`, `x_field = "delivery_man"`, `y_axis = [{"y_field": "open_balance", "color": "#E24C4C"}]`, `cache = 0`, `is_public = 1`, `type = "Bar"` per contracts §W6
- [X] T014 [US2] Update `cx_purisol/fixtures/workspace.json` to (a) append `{"number_card_name": "Purisol — Open Discrepancies"}` to the `number_cards` array, (b) append `{"chart_name": "Purisol — Outstanding Liabilities"}` to the `charts` array, (c) populate the `quick_lists` array with one inline entry `{"document_type": "Purisol Coupon Discrepancy", "label": "Open Discrepancies", "filters_json": "[[\"status\",\"=\",\"Open\"]]"}` (W5b — per contracts §W5b), and (d) extend the `content` escaped-JSON-string with the Risk Watchlist bundle blocks per contracts §Workspace Content Layout (spacer + header "Risk Watchlist" + W5a card + W5b quick_list + W6 chart)
- [X] T015 [P] [US2] Append rows to `cx_purisol/translations/ar.csv` for: `Risk Watchlist`, `Open Discrepancies`, `Outstanding Liabilities` — each with the Arabic translation from contracts §Localisation
- [X] T016 [P] [US2] Add five US2 acceptance-scenario tests to `cx_purisol/cx_purisol/tests/test_dashboard.py`: `test_us2_open_discrepancies_count_three_with_severity` (3 open + 1 resolved → count=3, color=Red), `test_us2_open_discrepancies_count_zero_healthy_state` (no open → count=0, severity perceptible without colour via empty Quick List), `test_us2_outstanding_liabilities_per_delivery_man` (W6 bars match seed: A's unpaid + B's full liability), `test_us2_widget_click_through_targets` (W5a/W5b/W6 click-through to correct list/report), `test_us2_zero_data_renders_cleanly` (no discrepancies + no liability JEs → both widgets render zero, no error)

**Checkpoint**: User Stories 1 AND 2 both work independently. The Risk Watchlist row of the dashboard surfaces open discrepancies and unpaid liabilities at a glance; SC-004 reconciliation is satisfied by construction (W6 reads the same Phase-7 report rows the underlying liability view shows).

---

## Phase 5: User Story 3 — Customer Follow-up Signals (Priority: P3)

**Goal**: Deliver Bundle 3 (2 widgets — W4, W8) plus the supporting `Customers Low on Coupons` Query Report so the Administrator can drive proactive customer outreach: spotting customers near empty (sell a new booklet before they run out) and reviewing recently depleted booklets (resale prompt).

**Independent Test**: Seed five customers with total remaining 0/1/2/3/4 across their Sold booklets and `Purisol Settings.customer_low_stock_threshold = 3`; seed three booklets depleted within the last seven days and two depleted more than seven days ago. Open the dashboard. Verify (a) W4 lists exactly four customers (totals 0/1/2/3) ordered ascending, (b) W4 caps at 10 if more qualify, (c) W8 lists exactly the three recently-depleted booklets, (d) clicking each widget drills through correctly, (e) editing the threshold to 5 in Purisol Settings then refreshing the dashboard adds customers with totals 4 (SC-007 live read). Bundle is shippable on its own.

### Implementation for User Story 3

- [X] T017 [US3] Create the new report folder `cx_purisol/cx_purisol/report/customers_low_on_coupons/` with an empty `cx_purisol/cx_purisol/report/customers_low_on_coupons/__init__.py`
- [X] T018 [P] [US3] Create `cx_purisol/cx_purisol/report/customers_low_on_coupons/customers_low_on_coupons.json` with the Report definition: `name = "Customers Low on Coupons"`, `ref_doctype = "Purisol Coupon Booklet"`, `is_standard = "Yes"`, `report_type = "Query Report"`, `module = "Cx Purisol"`, `roles = [{"role": "Purisol Administrator"}]`, `query` = the SQL from contracts/dashboard.md §R-NEW (correlated subquery on `tabSingles` for the live threshold read, `LIMIT 10`, ORDER BY `total_remaining ASC`), and `columns` = `[{"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer", "width": 240}, {"fieldname": "total_remaining", "label": "Remaining Coupons", "fieldtype": "Int", "width": 160}]`
- [X] T019 [P] [US3] Create `cx_purisol/cx_purisol/report/customers_low_on_coupons/customers_low_on_coupons.py` as a one-line Frappe auto-discovery stub matching the Phase-7 per-report convention (no `execute()` function is needed for Query Reports whose SQL is self-contained in the .json — see Phase-7 reports for the exact stub pattern)
- [X] T020 [P] [US3] Create `cx_purisol/cx_purisol/report/customers_low_on_coupons/test_customers_low_on_coupons.py` with `TestCustomersLowOnCoupons(FrappeTestCase)` covering: (a) threshold edge-case test (customers with totals 0/1/2/3/4, threshold=3 → result includes 0/1/2/3, excludes 4), (b) `LIMIT 10` cap test (12 qualifying customers → exactly 10 returned, lowest-first), (c) Depleted-excluded test (customer with one Depleted booklet only → not in result), (d) live-threshold-read test (change `Purisol Settings.customer_low_stock_threshold` from 3 to 5 → re-run report → result expands to include totals 4 and 5), (e) zero-Sold-booklet test (customer with no Sold booklets → not in result) — mirror the Phase-7 per-report `_REPORT_SQL` constant + `_run_report` helper pattern
- [X] T021 [P] [US3] Append a fourth Dashboard Chart record `Purisol — Customers Low on Coupons` (W4) to `cx_purisol/fixtures/dashboard_chart.json` — `chart_type = "Report"`, `report_name = "Customers Low on Coupons"`, `x_field = "customer"`, `y_axis = [{"y_field": "total_remaining", "color": "#FFA00A"}]`, `cache = 0`, `is_public = 1`, `type = "Bar"` per contracts §W4
- [X] T022 [US3] Update `cx_purisol/fixtures/workspace.json` to (a) append `{"chart_name": "Purisol — Customers Low on Coupons"}` to the `charts` array, (b) append a second inline entry to the `quick_lists` array `{"document_type": "Purisol Coupon Booklet", "label": "Recent Depleted Booklets", "filters_json": "[[\"status\",\"=\",\"Depleted\"],[\"depleted_on\",\">=\",\"[Today - 7d]\"]]"}` (W8 — per contracts §W8, relative-date token), and (c) extend the `content` escaped-JSON-string with the Customer Follow-up bundle blocks per contracts §Workspace Content Layout (spacer + header "Customer Follow-up" + W4 chart + W8 quick_list)
- [X] T023 [P] [US3] Append rows to `cx_purisol/translations/ar.csv` for: `Customer Follow-up`, `Customers Low on Coupons`, `Recent Depleted Booklets`, `Remaining Coupons` (the report column label) — each with the Arabic translation from contracts §Localisation
- [X] T024 [P] [US3] Add five US3 acceptance-scenario tests to `cx_purisol/cx_purisol/tests/test_dashboard.py`: `test_us3_low_stock_widget_at_or_below_threshold` (5 customers totals 0/1/2/3/4, threshold=3 → list has 0/1/2/3 ascending), `test_us3_low_stock_widget_caps_at_ten` (12 qualifying → 10 shown, lowest-first), `test_us3_recent_depleted_within_7_days` (3 recent + 2 old → list has only 3), `test_us3_widget_click_through_targets` (W4 → report, W8 row → booklet detail), `test_us3_empty_state_renders_cleanly` (no low-stock customers + no recent depletions → both widgets render empty-state, no error)

**Checkpoint**: All three user stories are independently functional. Every dashboard widget renders, drills through correctly, and the supporting `Customers Low on Coupons` Query Report is migration-installed alongside.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Tests and verifications that span multiple user stories — empty-state rendering for the whole dashboard, cancelled-document filter end-to-end, SC-004 reconciliation, SC-007 live-refresh, relative-date token regression guard, full test-suite green check, and quickstart manual smoke.

- [X] T025 [US3] Add `test_dashboard_empty_state_all_widgets` to `cx_purisol/cx_purisol/tests/test_dashboard.py` — set up a fresh test site with zero Purisol records and assert each of the 8 widgets (W1, W2a, W2b, W3, W5a, W5b, W6, W7, W8) renders without raising, with Number Cards showing 0, Dashboard Charts showing empty frames, and Quick Lists showing the Frappe default "no records" state per research §20
- [X] T026 Add `test_dashboard_cancelled_discrepancy_filter` to `cx_purisol/cx_purisol/tests/test_dashboard.py` — submit a discrepancy, capture the W5a count, cancel the discrepancy, re-run the W5a query, assert the count decreased by one (verifies the `docstatus = 1` filter from contracts §W5a is doing its job)
- [X] T027 Add `test_dashboard_sc004_w6_reconciles_with_phase7_report` to `cx_purisol/cx_purisol/tests/test_dashboard.py` — seed liability journal entries across two delivery men, run the Phase-7 `Delivery Man Liability Balance` report, run the W6 chart's underlying query, assert row-by-row that the chart's `(delivery_man, open_balance)` pairs equal the report's `(delivery_man, open_balance)` column values exactly (SC-004)
- [X] T028 Add `test_dashboard_sc007_w4_live_threshold_read` to `cx_purisol/cx_purisol/tests/test_dashboard.py` — seed customers with various totals, run the W4 underlying report at `Purisol Settings.customer_low_stock_threshold = 3` and capture the row count, change the setting to 5 via `frappe.db.set_single_value` (or use the `single_value` API — read-only test path), re-run the report, assert the row count expanded to include customers with totals 4 and 5 (SC-007 — no cache, no restart)
- [X] T029 Add `test_dashboard_w8_relative_date_token_evaluates` to `cx_purisol/cx_purisol/tests/test_dashboard.py` — call `frappe.get_list("Purisol Coupon Booklet", filters=[["status","=","Depleted"],["depleted_on",">=","[Today - 7d]"]])` directly, assert the result against a hand-constructed expected set (3 booklets depleted within the last 7 days, 2 outside) per research §6's test-coverage note — guards against any future Frappe relative-date-token regression
- [ ] T030 Run the full test suite via `bench --site <site> run-tests --app cx_purisol` and verify zero regressions in any Phase 1–7 tests AND every new Phase-8 test passes (15 user-story tests + 5 cross-cutting tests + 5 per-report tests + 4 foundational tests = 29 new test methods minimum)
- [ ] T031 Execute `specs/008-dashboard/quickstart.md` Steps 1–11 manually on a local bench site against the seeded Phase-1-through-7 dataset — confirm every Definition-of-Done item passes (default landing, role gate, all 8 widgets render under 3s, click-through, SC-004 manual reconciliation, SC-007 manual threshold change, cancelled-document filter, empty-state, Arabic locale render)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1, T001–T003)**: No dependencies. Can start immediately. Within the phase: T002 depends on T001 (same directory); T003 is independent.
- **Foundational (Phase 2, T004–T006)**: Depends on Setup completion. BLOCKS every user story. Within the phase: T004, T005, T006 touch three different files (`hooks.py`, `workspace.json`, `test_dashboard.py`) and are fully independent — all three [P].
- **User Story 1 (Phase 3, T007–T011)**: Depends on Foundational completion. Independent of US2 and US3.
- **User Story 2 (Phase 4, T012–T016)**: Depends on Foundational completion. Independent of US1 and US3 in correctness, but in practice T012/T013 append to fixture files US1 created and T014 extends the workspace `content` US1 populated — execute US2 after US1 if working serially, or coordinate fixture-file appends if parallel.
- **User Story 3 (Phase 5, T017–T024)**: Depends on Foundational completion. Independent of US1 and US2 in correctness, with the same shared-file caveat as US2.
- **Polish (Phase 6, T025–T031)**: Tests T025–T029 depend on the corresponding user-story phase having added the widgets they test. T030 depends on every other Phase-8 task. T031 depends on T030 (run automated tests before manual smoke).

### User Story Dependencies (correctness-level — bundles are independent per SC-009)

- **US1 (P1)**: No dependency on US2 or US3. Ship alone if needed.
- **US2 (P2)**: No correctness dependency on US1 or US3. The dashboard's Risk row works whether or not the Operations row is populated.
- **US3 (P3)**: No correctness dependency on US1 or US2. Requires the Phase-7 `Daily Delivery Man Summary` and `Delivery Man Liability Balance` reports to exist on master (per plan research §13) — but those are pre-Phase-8 prerequisites, not US-internal dependencies.

### Within Each User Story

- Tests (T011, T016, T024 plus the per-report tests in T020) MUST be added alongside implementation tasks; verify each test method runs and asserts the expected behaviour against a seeded dataset before marking the story complete.
- Fixture-file edits before workspace.json reference edits is the natural order, but Frappe gracefully handles dangling references at migrate time so the strict order is not enforced.
- Workspace `content`-field edit (T009 / T014 / T022) is the most error-prone task per research §18 — the recommended workflow is build the layout via Frappe Desk UI, then `bench export-fixtures` to capture the correctly-escaped JSON string, rather than hand-writing the escaped string.

### Parallel Opportunities Within Each Phase

- **Setup**: T001 + T003 can run in parallel; T002 follows T001.
- **Foundational**: T004 + T005 + T006 — three different files, fully parallel.
- **US1**: T007 + T008 + T010 + T011 — four different files, parallel. T009 (workspace.json) is independent of those four file-wise but depends on Foundational T005's role-gate edit being done.
- **US2**: T012 + T013 + T015 + T016 — four different files, parallel. T014 (workspace.json) depends on T009 being merged (or coordinated).
- **US3**: T017 first (creates the report folder); then T018 + T019 + T020 + T021 + T023 + T024 — six different files, fully parallel. T022 (workspace.json) depends on T014 being merged (or coordinated).
- **Polish**: T025–T029 all edit `test_dashboard.py` — sequential within the file. T030 after T025–T029. T031 after T030.

---

## Parallel Example: User Story 1

```bash
# After Foundational (T004, T005, T006) is merged, launch US1's parallel tasks together:
Task: "T007 [US1] Create cx_purisol/fixtures/number_card.json with W1, W2a, W3 records"
Task: "T008 [US1] Create cx_purisol/fixtures/dashboard_chart.json with W2b, W7 records"
Task: "T010 [US1] Append Operations + W1/W2a/W2b/W3/W7 Arabic translations to cx_purisol/translations/ar.csv"
Task: "T011 [US1] Add 5 US1 acceptance-scenario tests to cx_purisol/cx_purisol/tests/test_dashboard.py"
# Then run T009 (workspace.json — references widgets created above and adds Operations content blocks)
```

## Parallel Example: User Story 3

```bash
# After T017 creates the report folder:
Task: "T018 [US3] Write Customers Low on Coupons Report .json with SQL"
Task: "T019 [US3] Write report .py auto-discovery stub"
Task: "T020 [US3] Write per-report unit tests"
Task: "T021 [US3] Append W4 Dashboard Chart record to dashboard_chart.json"
Task: "T023 [US3] Append Customer Follow-up + W4/W8 Arabic translations to ar.csv"
Task: "T024 [US3] Add 5 US3 acceptance-scenario tests to test_dashboard.py"
# Then run T022 (workspace.json — adds W4/W8 references and Customer Follow-up content blocks)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) — T001/T002/T003.
2. Complete Phase 2 (Foundational) — T004/T005/T006. CRITICAL.
3. Complete Phase 3 (User Story 1) — T007–T011.
4. **STOP and VALIDATE**: run the US1 tests, verify the Operations row of the dashboard renders for an admin user, click each widget to confirm drill-through, run the empty-state test (T025) early to catch first-install regressions.
5. Deploy/demo MVP — at this point the morning-glance ritual is replaced; Bundle 1 alone delivers the headline value of Phase 8.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. Add US1 → Test independently → Demo (MVP).
3. Add US2 → Test independently (cancelled-document filter T026, SC-004 reconciliation T027 land here too) → Demo.
4. Add US3 → Test independently (SC-007 live-refresh T028, relative-date-token T029 land here) → Demo.
5. Polish: T025/T026/T027/T028/T029/T030/T031 round out the cross-cutting tests and final manual smoke.

### Parallel Team Strategy

With three developers post-Foundational:

1. Team completes Setup + Foundational together (one PR).
2. Once Foundational is merged:
   - Developer A: US1 (T007–T011) — Operations bundle.
   - Developer B: US2 (T012–T016) — Risk Watchlist bundle.
   - Developer C: US3 (T017–T024) — Customer Follow-up bundle (largest scope due to the new Report).
3. Coordinate workspace.json `content`-field edits via either (a) merge-order discipline (US1 → US2 → US3 sequential merges) or (b) one developer owns workspace.json and integrates the others' bundle blocks.
4. Cross-cutting Polish tasks (T025–T029) can be parcelled out per topic; T030 and T031 are end-of-phase by definition.

---

## Notes

- [P] tasks edit different files within their phase and have no in-phase dependency on incomplete tasks.
- [Story] label maps task to its user story for traceability and bundle-independence audit (SC-009).
- Each user story is independently completable, independently testable, and shippable as a bundle.
- The single shared file across all stories is `cx_purisol/fixtures/workspace.json`. Tasks T009 / T014 / T022 are sequential by virtue of editing the same file's `number_cards`, `charts`, `quick_lists`, and `content` arrays.
- Tests are required by the plan (§Testing), the constitution (Principle X), and the per-bundle "Independent Test" criteria in spec.md. Aim for ≥ 29 new test methods total: 4 in Foundational, 5 per US (15), 5 in per-report tests, 5 cross-cutting in Polish.
- Commit after each task or each logical group within a story. Stop at any checkpoint to validate independently.
- Arabic translations land in `cx_purisol/translations/ar.csv` per Phase 1–7 convention; English labels live in the fixture JSONs and Frappe's `_()` machinery translates at render time.
- Avoid: hand-writing the workspace `content` JSON string (use Desk UI + `bench export-fixtures` per research §18); duplicating Phase-7 SQL in widget queries (reuse Phase-7 reports per research §13); introducing per-widget role gates (the workspace-level role gate plus underlying-DocType permissions are sufficient per plan).
