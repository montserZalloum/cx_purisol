# Tasks: Reports (Phase 7)

**Input**: Design documents from `/specs/007-reports/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/reports.md, quickstart.md

**Tests**: Test tasks are INCLUDED per plan.md (per-report unit tests + bundle-level integration tests + cross-cutting property tests).

**Organization**: Tasks are grouped by user story (bundle) to enable independent shipping per SC-007. Bundles share zero implementation files; the only common artefacts are the patch anchor and the shared test seed helper, both in Phase 2 (Foundational).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Frappe custom app — `cx_purisol/cx_purisol/` is the module root
- Per-report folders under `cx_purisol/cx_purisol/report/<snake_case_name>/`
- Shared test fixtures under `cx_purisol/cx_purisol/tests/`
- Translations in `cx_purisol/translations/ar.csv`
- Patches in `cx_purisol/patches/v0_7_0/` + append to `cx_purisol/patches.txt`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Version anchor + translations scaffolding

- [x] T001 Create `cx_purisol/patches/v0_7_0/__init__.py` as empty package marker
- [x] T002 Create `cx_purisol/patches/v0_7_0/add_phase_7_reports.py` with a no-op `execute()` function (reports migrate via `bench migrate`'s standard `Report` sync per research.md §15)
- [x] T003 Append `cx_purisol.patches.v0_7_0.add_phase_7_reports` as a new line to `cx_purisol/patches.txt`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared deterministic test seed helper and integration test file skeleton. Every Phase 3/4/5 per-report test and every bundle-level integration test imports from `report_seed.py`; it MUST exist before any per-report test task runs.

**⚠️ CRITICAL**: No user story work can begin until T004 completes (per-report tests and integration tests depend on it).

- [x] T004 Create `cx_purisol/cx_purisol/tests/report_seed.py` with entry-point functions `seed_for_operations()`, `seed_for_finance()`, `seed_for_analytics()`, and `seed_full_phase_7()` composing existing Phase 1–6 fixtures (`make_booklet_in_stock`, `submit_assign`, `make_employee`, `seed_open_discrepancy`, `seed_administrator_user`, etc.) per research.md §10 — deterministic dataset: 3 customers, 4 delivery men, 6 booklets in mixed states, multiple consumption entries spanning known dates, discrepancies in varied resolution states, Sales Invoices at two price lists, Journal/Payment Entries against the liability account
- [x] T005 Create `cx_purisol/cx_purisol/tests/test_report_flows.py` with a `FrappeTestCase` skeleton that imports `report_seed`, sets up a site-level test user with `Purisol Administrator` role, sets up a non-admin user, and exposes a `_run_report(report_name, filters)` helper that invokes Frappe's query-report execution path — individual test methods are added in later phases as each bundle's integration tests are written

**Checkpoint**: Foundation ready — Bundles 1/2/3 can proceed in parallel.

---

## Phase 3: User Story 1 — Operational Reports (Priority: P1) 🎯 MVP

**Goal**: Ship the four operational reports (Daily Delivery Man Summary, Active Booklets per Customer, Current Custody by Delivery Man [reuse], Coupon Consumption Log) so the Administrator can answer "what happened today, who has what, and where do my coupons stand?".

**Independent Test**: Seed `seed_for_operations()` → open each of the four operational reports with filter combinations from spec US1 acceptance scenarios → verify rows/columns/derived values exactly match the hand-calculable expected results. Bundle is shippable standalone (Bundle 2 and Bundle 3 not required).

### Implementation for User Story 1

**R1 — Daily Delivery Man Summary (Script Report)**

- [x] T006 [P] [US1] Create `cx_purisol/cx_purisol/report/daily_delivery_man_summary/__init__.py` (empty package marker)
- [x] T007 [P] [US1] Create `cx_purisol/cx_purisol/report/daily_delivery_man_summary/daily_delivery_man_summary.json` with `report_type = "Script Report"`, `is_standard = "Yes"`, `module = "Cx Purisol"`, `roles = [{"role": "Purisol Administrator"}]`, filters `from_date` (Date), `to_date` (Date), `delivery_man` (Link → Employee) per contracts/reports.md §R1
- [x] T008 [P] [US1] Create `cx_purisol/cx_purisol/report/daily_delivery_man_summary/daily_delivery_man_summary.py` with `execute(filters)` returning `(columns, data)` — three SQL aggregates (coupons-per-pair, booklets-per-pair, discrepancies-per-pair all keyed by (posting_date, delivery_man)), Python dict-merge with missing-defaults-to-0, column fieldnames `posting_date`, `delivery_man`, `coupons_submitted`, `booklets_touched`, `discrepancies_count`, `discrepancy_total` — each column label wrapped in `frappe._()` per contracts/reports.md §R1 aggregation logic
- [x] T009 [P] [US1] Create `cx_purisol/cx_purisol/report/daily_delivery_man_summary/test_daily_delivery_man_summary.py` — seeds a minimal dataset (1 delivery man, 2 booklets, 3 consumption entries, 1 discrepancy), imports `execute` directly, asserts one row for (today, delivery_man_A) with `coupons_submitted=8`, `booklets_touched=2`, `discrepancies_count=1`, `discrepancy_total` matching the seeded amount (spec US1 AS1)

**R2 — Active Booklets per Customer (Query Report)**

- [x] T010 [P] [US1] Create `cx_purisol/cx_purisol/report/active_booklets_per_customer/__init__.py`
- [x] T011 [P] [US1] Create `cx_purisol/cx_purisol/report/active_booklets_per_customer/active_booklets_per_customer.json` with `report_type = "Query Report"`, `is_standard = "Yes"`, `module = "Cx Purisol"`, `roles = [{"role": "Purisol Administrator"}]`, single optional `customer` (Link → Customer) filter, columns `customer`/`booklet`/`status`/`consumed_count`/`remaining_count`/`sold_on`/`days_since_sale`, embedded SQL per contracts/reports.md §R2 skeleton (filter on `b.status IN ('Sold', 'Depleted') AND b.customer IS NOT NULL`, optional-filter idiom, order by customer ASC then sold_on DESC)
- [x] T012 [P] [US1] Create `cx_purisol/cx_purisol/report/active_booklets_per_customer/active_booklets_per_customer.py` with auto-discovery stub comment matching the Phase-2 `current_custody_by_delivery_man.py` pattern
- [x] T013 [P] [US1] Create `cx_purisol/cx_purisol/report/active_booklets_per_customer/test_active_booklets_per_customer.py` following Phase-2 pattern (in-file `_REPORT_SQL` constant + `_run_report(customer=...)` helper); seeds 1 customer × 3 booklets (20/20 Depleted, 12/20 Sold, 0/20 Sold); asserts three rows with correct status/consumed/remaining and computed days_since_sale (spec US1 AS2)

**R3 — Current Custody by Delivery Man (reuse Phase 2 — verify only)**

- [x] T014 [US1] Add a smoke test method to `cx_purisol/cx_purisol/tests/test_report_flows.py` that seeds via `seed_for_operations()`, invokes the existing Phase-2 `current_custody_by_delivery_man` report for (delivery_man_A with 2 booklets assigned 5d and 1d ago, delivery_man_B with 0 booklets), asserts delivery_man_A appears with both booklets and `days_in_custody` of 5 and 1, delivery_man_B does NOT appear (spec US1 AS3) — NO modification to the Phase-2 report folder

**R4 — Coupon Consumption Log (Query Report)**

- [x] T015 [P] [US1] Create `cx_purisol/cx_purisol/report/coupon_consumption_log/__init__.py`
- [x] T016 [P] [US1] Create `cx_purisol/cx_purisol/report/coupon_consumption_log/coupon_consumption_log.json` with `report_type = "Query Report"`, metadata as above, filters `from_date`/`to_date` (Date), `delivery_man` (Link → Employee), `customer` (Link → Customer), `booklet` (Link → Purisol Coupon Booklet), columns per contracts/reports.md §R4, embedded SQL joining `tabPurisol Coupon` → `tabPurisol Coupon Booklet` → `tabPurisol Coupon Consumption Entry` filtered `c.status = 'Consumed' AND cce.docstatus = 1`
- [x] T017 [P] [US1] Create `cx_purisol/cx_purisol/report/coupon_consumption_log/coupon_consumption_log.py` auto-discovery stub
- [x] T018 [P] [US1] Create `cx_purisol/cx_purisol/report/coupon_consumption_log/test_coupon_consumption_log.py` — seeds 12 consumption entries × 40 coupons across 3 customers / 4 delivery men over a week, asserts exactly 40 rows with correct columns for a week-range filter (spec US1 AS4)

### Integration Tests for User Story 1

- [x] T019 [US1] Add `test_us1_daily_delivery_man_summary_acceptance_scenario_1` to `cx_purisol/cx_purisol/tests/test_report_flows.py` covering spec US1 AS1 end-to-end via `seed_for_operations()`
- [x] T020 [US1] Add `test_us1_active_booklets_per_customer_acceptance_scenario_2` to `cx_purisol/cx_purisol/tests/test_report_flows.py` covering spec US1 AS2
- [x] T021 [US1] Add `test_us1_coupon_consumption_log_acceptance_scenario_4` to `cx_purisol/cx_purisol/tests/test_report_flows.py` covering spec US1 AS4 (40-row assertion)
- [x] T022 [US1] Add `test_us1_export_contract_acceptance_scenario_5` to `cx_purisol/cx_purisol/tests/test_report_flows.py` — smoke-verify that `frappe.get_doc("Report", <name>)` returns a doc for each of the four Bundle-1 reports and that the Frappe viewer's export endpoints can be invoked without raising (spec US1 AS5 — export is platform-provided per research.md §13, so this test is a smoke-level presence check)

### Localisation for User Story 1

- [x] T023 [US1] Append Arabic translations to `cx_purisol/translations/ar.csv` for every new column label, filter label, and `frappe._()`-wrapped string introduced by Bundle 1 reports (R1, R2, R4) — one CSV row per string

**Checkpoint**: Bundle 1 fully functional and independently testable. Ship-ready for MVP.

---

## Phase 4: User Story 2 — Financial & Oversight Reports (Priority: P2)

**Goal**: Ship the four financial/oversight reports (Delivery Man Discrepancies, Delivery Man Liability Balance, Booklet Sales Report, Discrepancy Rate by Delivery Man) so the Administrator can audit delivery-man behaviour, reconcile GL liability, and review all booklet-driven sales.

**Independent Test**: Seed `seed_for_finance()` → open each of the four financial reports → verify figures tie to the GL (SC-003) and to spec US2 acceptance scenarios. Bundle is shippable standalone (independent of Bundle 1 and Bundle 3 per SC-007).

### Implementation for User Story 2

**R5 — Delivery Man Discrepancies (Query Report)**

- [x] T024 [P] [US2] Create `cx_purisol/cx_purisol/report/delivery_man_discrepancies/__init__.py`
- [x] T025 [P] [US2] Create `cx_purisol/cx_purisol/report/delivery_man_discrepancies/delivery_man_discrepancies.json` with metadata per conventions, filters `from_date`/`to_date` (Date), `delivery_man` (Link → Employee), `status` (Select with five discrepancy statuses), columns per contracts/reports.md §R5, embedded SQL joining `tabPurisol Coupon Discrepancy` → `tabPurisol Coupon Consumption Entry` (LEFT JOIN on `triggering_consumption_entry`) with the subquery for `coupons_count` and `d.docstatus = 1`
- [x] T026 [P] [US2] Create `cx_purisol/cx_purisol/report/delivery_man_discrepancies/delivery_man_discrepancies.py` auto-discovery stub
- [x] T027 [P] [US2] Create `cx_purisol/cx_purisol/report/delivery_man_discrepancies/test_delivery_man_discrepancies.py` — seeds 3 Open + 1 Paid discrepancy across 2 delivery men, asserts 4 rows with correct IDs/statuses/amounts for a date-range filter covering both (spec US2 AS1)

**R6 — Delivery Man Liability Balance (Script Report)**

- [x] T028 [P] [US2] Create `cx_purisol/cx_purisol/report/delivery_man_liability_balance/__init__.py`
- [x] T029 [P] [US2] Create `cx_purisol/cx_purisol/report/delivery_man_liability_balance/delivery_man_liability_balance.json` with `report_type = "Script Report"`, metadata, single optional `delivery_man` (Link → Employee) filter, columns per contracts/reports.md §R6
- [x] T030 [P] [US2] Create `cx_purisol/cx_purisol/report/delivery_man_liability_balance/delivery_man_liability_balance.py` with `execute(filters)`: (1) read `Purisol Settings.employee_liability_account` fresh; (2) if unset, return one info row per research.md §5 with `_("Configure employee_liability_account in Purisol Settings to enable this report")`; (3) else SQL `SUM(debit)/SUM(credit) GROUP BY party` on `tabGL Entry` filtered `account = settings.employee_liability_account AND party_type = 'Employee' AND is_cancelled = 0`; (4) Python lookup `Employee.employee_name` per row; (5) compute `open_balance = owed - paid`
- [x] T031 [P] [US2] Create `cx_purisol/cx_purisol/report/delivery_man_liability_balance/test_delivery_man_liability_balance.py` — configures `employee_liability_account`, seeds 2 liability JEs + 1 offsetting Payment Entry for delivery_man_A, asserts `total_owed`/`total_paid`/`open_balance` match seeded sums (spec US2 AS2); separate test case clears the account, asserts the info-row fallback

**R7 — Booklet Sales Report (Query Report)**

- [x] T032 [P] [US2] Create `cx_purisol/cx_purisol/report/booklet_sales_report/__init__.py`
- [x] T033 [P] [US2] Create `cx_purisol/cx_purisol/report/booklet_sales_report/booklet_sales_report.json` with metadata, filters `from_date`/`to_date` (Date), `customer` (Link → Customer), `price_list` (Link → Price List), columns per contracts/reports.md §R7, embedded SQL joining `tabSales Invoice Item` (filtered `sii.purisol_booklet IS NOT NULL`) → `tabSales Invoice` with `si.docstatus = 1` and `si.selling_price_list = %(price_list)s` optional filter
- [x] T034 [P] [US2] Create `cx_purisol/cx_purisol/report/booklet_sales_report/booklet_sales_report.py` auto-discovery stub
- [x] T035 [P] [US2] Create `cx_purisol/cx_purisol/report/booklet_sales_report/test_booklet_sales_report.py` — seeds 7 Sales Invoices × 3 customers × 2 price lists within a date range, asserts the price-list filter narrows to matching invoices only (spec US2 AS3)

**R8 — Discrepancy Rate by Delivery Man (Script Report)**

- [x] T036 [P] [US2] Create `cx_purisol/cx_purisol/report/discrepancy_rate_by_delivery_man/__init__.py`
- [x] T037 [P] [US2] Create `cx_purisol/cx_purisol/report/discrepancy_rate_by_delivery_man/discrepancy_rate_by_delivery_man.json` with `report_type = "Script Report"`, metadata, filters `from_date`/`to_date` (Date), columns per contracts/reports.md §R8 (`delivery_man`, `coupons_submitted`, `discrepancies_count`, `discrepancy_rate` [Percent], `discrepancy_total` [Currency])
- [x] T038 [P] [US2] Create `cx_purisol/cx_purisol/report/discrepancy_rate_by_delivery_man/discrepancy_rate_by_delivery_man.py` with `execute(filters)`: two SQL aggregates (coupons_per_dm, discrepancies_per_dm both grouped by `cce.delivery_man` filtered on `cce.posting_date` range), Python dict-merge over `coupons.keys()`, rate formula `round(100 * d_count / c_count, 2) if c_count else 0`, order `rate DESC, coupons_submitted DESC`
- [x] T039 [P] [US2] Create `cx_purisol/cx_purisol/report/discrepancy_rate_by_delivery_man/test_discrepancy_rate_by_delivery_man.py` — seeds delivery_man_A (100 coupons, 4 discrepancies) and delivery_man_B (50 coupons, 0 discrepancies); asserts A's rate is 4.0 and total > 0; B's rate is 0 and total is 0 (spec US2 AS4)

### Integration Tests for User Story 2

- [x] T040 [US2] Add `test_us2_delivery_man_discrepancies_acceptance_scenario_1` to `cx_purisol/cx_purisol/tests/test_report_flows.py` covering spec US2 AS1 via `seed_for_finance()`
- [x] T041 [US2] Add `test_us2_liability_balance_acceptance_scenario_2` to `cx_purisol/cx_purisol/tests/test_report_flows.py` covering spec US2 AS2
- [x] T042 [US2] Add `test_us2_booklet_sales_report_acceptance_scenario_3` to `cx_purisol/cx_purisol/tests/test_report_flows.py` covering spec US2 AS3 (price-list filter)
- [x] T043 [US2] Add `test_us2_discrepancy_rate_acceptance_scenario_4` to `cx_purisol/cx_purisol/tests/test_report_flows.py` covering spec US2 AS4 (4% / 0% rates)
- [x] T044 [US2] Add `test_us2_filter_refresh_acceptance_scenario_5` to `cx_purisol/cx_purisol/tests/test_report_flows.py` — for each Bundle-2 report run with two different filter values and assert the rows differ (spec US2 AS5)
- [x] T045 [US2] Add `test_us2_liability_gl_reconciliation_property` to `cx_purisol/cx_purisol/tests/test_report_flows.py` — runs Delivery Man Liability Balance for a delivery man with mixed liability JEs and offsetting Payment Entries, calls `frappe.get_all("GL Entry", ...)` against the same account/party, asserts `total_owed` / `total_paid` / `open_balance` match the GL aggregate exactly (SC-003)

### Localisation for User Story 2

- [x] T046 [US2] Append Arabic translations to `cx_purisol/translations/ar.csv` for every new column label, filter label, and `frappe._()`-wrapped string introduced by Bundle 2 reports (R5, R6, R7, R8), including the liability "Configure …" info-row string

**Checkpoint**: Bundle 2 fully functional and ships independently of Bundle 1 / Bundle 3.

---

## Phase 5: User Story 3 — Analytical Reports (Priority: P3)

**Goal**: Ship the two analytical reports (Customer Consumption Rate, Booklet Lifecycle Duration) so the Administrator can forecast customer re-order timing and size future generation batches.

**Independent Test**: Seed `seed_for_analytics()` with known hand-calculable datedifs → open both analytical reports → verify averages match hand-computed values exactly. Bundle ships independently of Bundle 1 / Bundle 2.

### Implementation for User Story 3

**R9 — Customer Consumption Rate (Query Report)**

- [x] T047 [P] [US3] Create `cx_purisol/cx_purisol/report/customer_consumption_rate/__init__.py`
- [x] T048 [P] [US3] Create `cx_purisol/cx_purisol/report/customer_consumption_rate/customer_consumption_rate.json` with `report_type = "Query Report"`, metadata, no filters, columns `customer`/`booklets_depleted`/`avg_days_to_deplete` per contracts/reports.md §R9, embedded SQL `AVG(DATEDIFF(b.depleted_on, b.sold_on)) GROUP BY b.customer` filtered `b.status = 'Depleted' AND b.depleted_on IS NOT NULL AND b.sold_on IS NOT NULL AND b.customer IS NOT NULL`, order `avg_days_to_deplete ASC`
- [x] T049 [P] [US3] Create `cx_purisol/cx_purisol/report/customer_consumption_rate/customer_consumption_rate.py` auto-discovery stub
- [x] T050 [P] [US3] Create `cx_purisol/cx_purisol/report/customer_consumption_rate/test_customer_consumption_rate.py` — seeds C1 with 3 Depleted booklets (30, 45, 60 days) and C2 with 2 Depleted booklets (10, 20 days); asserts C1 row has `avg_days_to_deplete = 45.0`, C2 row has `avg_days_to_deplete = 15.0`, customers with no Depleted booklets are omitted (spec US3 AS1)

**R10 — Booklet Lifecycle Duration (Script Report)**

- [x] T051 [P] [US3] Create `cx_purisol/cx_purisol/report/booklet_lifecycle_duration/__init__.py`
- [x] T052 [P] [US3] Create `cx_purisol/cx_purisol/report/booklet_lifecycle_duration/booklet_lifecycle_duration.json` with `report_type = "Script Report"`, metadata, no filters, single-row three-column output per contracts/reports.md §R10
- [x] T053 [P] [US3] Create `cx_purisol/cx_purisol/report/booklet_lifecycle_duration/booklet_lifecycle_duration.py` with `execute(filters)` returning a single row with three `AVG(CASE WHEN ...)` values from a single SQL over `tabPurisol Coupon Booklet`; `null` values pass through untouched so the viewer renders empty cells (research.md §6); column labels wrapped in `frappe._()`
- [x] T054 [P] [US3] Create `cx_purisol/cx_purisol/report/booklet_lifecycle_duration/test_booklet_lifecycle_duration.py` — seeds booklets with known creation/sold_on/depleted_on offsets (30/45/60 days generated, 10/20/30 days sold, 0/5/10 days depleted); asserts the three averages exactly (e.g. `avg_full_lifetime = 40.0`); second test case with zero Depleted booklets asserts single row with `null` averages

### Integration Tests for User Story 3

- [x] T055 [US3] Add `test_us3_customer_consumption_rate_acceptance_scenario_1` to `cx_purisol/cx_purisol/tests/test_report_flows.py` covering spec US3 AS1 via `seed_for_analytics()`
- [x] T056 [US3] Add `test_us3_booklet_lifecycle_duration_acceptance_scenario_2` to `cx_purisol/cx_purisol/tests/test_report_flows.py` covering spec US3 AS2
- [x] T057 [US3] Add `test_us3_export_contract_acceptance_scenario_3` to `cx_purisol/cx_purisol/tests/test_report_flows.py` — smoke-verify `frappe.get_doc("Report", <name>)` for both analytical reports (spec US3 AS3; export itself is platform-provided per research.md §13)

### Localisation for User Story 3

- [x] T058 [US3] Append Arabic translations to `cx_purisol/translations/ar.csv` for every new column label and `frappe._()`-wrapped string introduced by Bundle 3 reports (R9, R10)

**Checkpoint**: All three bundles independently functional. Phase 7 feature-complete.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Cross-cutting tests and verification that span all three bundles.

- [x] T059 Add `test_permissions_across_all_reports` parametrised test to `cx_purisol/cx_purisol/tests/test_report_flows.py` — iterates over all 10 report names, sets `frappe.set_user(<non_admin_user>)`, asserts execution returns a permission error or equivalent deny (FR-004, SC-005)
- [x] T060 Add `test_cancelled_sales_invoice_excluded_from_booklet_sales_report` to `cx_purisol/cx_purisol/tests/test_report_flows.py` — cancel a submitted Sales Invoice after seed, rerun, assert rows disappear (FR-005 / SC-005 for Sales Invoice source)
- [x] T061 Add `test_cancelled_consumption_entry_excluded_from_consumption_log_and_summary` to `cx_purisol/cx_purisol/tests/test_report_flows.py` — cancel a submitted Consumption Entry, assert its rows disappear from Coupon Consumption Log and that its row in Daily Delivery Man Summary updates (FR-005 / SC-005 for Consumption Entry source)
- [x] T062 Add `test_cancelled_discrepancy_excluded_from_discrepancies_and_rate` to `cx_purisol/cx_purisol/tests/test_report_flows.py` — cancel a submitted Discrepancy, assert it disappears from Delivery Man Discrepancies and from the Discrepancy Rate by Delivery Man's numerator (FR-005 / SC-005 for Discrepancy source)
- [x] T063 Add `test_current_custody_by_delivery_man_unchanged_under_phase_7_dataset` to `cx_purisol/cx_purisol/tests/test_report_flows.py` — confirms the pre-existing Phase-2 report still renders under the shared seed and that the role gate still rejects non-admin users (reuse verification per plan.md)
- [ ] T064 Run `bench --site <site> migrate` on a clean test site; verify all 10 Report records appear under the `Cx Purisol` module group in the Reports menu (quickstart.md Step 2) [MANUAL — requires bench access]
- [ ] T065 Run the full test suite `bench --site <site> run-tests --app cx_purisol`; verify all Phase 1–7 tests pass (quickstart.md Step 8) [MANUAL — requires bench access]
- [ ] T066 Execute quickstart.md Steps 3–7 manually on the test site (permission gate check, Bundle 1/2/3 smokes, export smoke) and record results [MANUAL — requires bench access]
- [ ] T067 Execute quickstart.md Step 9 manually (Arabic locale spot-check) and confirm column/filter labels render in Arabic [MANUAL — requires bench access]

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1 — T001–T003)**: No dependencies; can start immediately.
- **Foundational (Phase 2 — T004–T005)**: Depends on Setup completion. **BLOCKS every user story** (every per-report test task imports from `report_seed.py` and every integration test lives in `test_report_flows.py`).
- **Phase 3 (Bundle 1) / Phase 4 (Bundle 2) / Phase 5 (Bundle 3)**: All depend on Phase 2. The three bundles are independent of each other per SC-007 — they can be implemented in parallel by different developers, or sequentially in priority order P1 → P2 → P3.
- **Phase 6 (Polish)**: Depends on all three bundles being complete (cross-cutting tests reference every Phase-7 report).

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2 — no dependency on Bundle 2 or Bundle 3.
- **User Story 2 (P2)**: Can start after Phase 2 — independent of Bundle 1 and Bundle 3. Shares the liability GL-reconciliation property with no cross-bundle code.
- **User Story 3 (P3)**: Can start after Phase 2 — independent of Bundle 1 and Bundle 2.

### Within Each User Story

- All four (or two for US3) reports in a bundle share no implementation files — all `[P]` tasks within a bundle are genuinely parallelisable.
- Within a single report: folder `__init__.py` + JSON + Python + per-report test can all be created in parallel (different files).
- Integration test methods inside `test_report_flows.py` are sequential within a story because they share the file — but each story's block of integration tests is independent of the others.
- Arabic-translation append task is the last task of each bundle because its input is the set of new strings introduced by that bundle.

### Parallel Opportunities

- **Phase 1** (T001–T003): T001 + T002 parallel; T003 depends on T002's file existing.
- **Phase 2** (T004 + T005): T004 and T005 are in different files — both parallel.
- **Phase 3**: T006–T013 all parallel (different report folders / different files), T014 depends on T004, T015–T018 parallel, T019–T022 sequential (same file), T023 last.
- **Phase 4**: T024–T039 all parallel within each report group (different folders), T040–T045 sequential (same file), T046 last.
- **Phase 5**: T047–T054 parallel across the two reports, T055–T057 sequential, T058 last.
- **Phase 6**: T059–T063 sequential (same file); T064–T067 can follow in any order once all tests pass locally.
- **Across bundles**: once Phase 2 is done, three developers can each take one bundle and work in parallel; nothing in Bundle 2 blocks Bundle 1 and vice versa.

---

## Parallel Example: User Story 1

```bash
# Once Phase 2 (T004, T005) completes, launch all Bundle-1 report files in parallel:
Task: "Create daily_delivery_man_summary/__init__.py"            # T006
Task: "Create daily_delivery_man_summary.json"                   # T007
Task: "Create daily_delivery_man_summary.py"                     # T008
Task: "Create test_daily_delivery_man_summary.py"                # T009
Task: "Create active_booklets_per_customer/__init__.py"          # T010
Task: "Create active_booklets_per_customer.json"                 # T011
Task: "Create active_booklets_per_customer.py"                   # T012
Task: "Create test_active_booklets_per_customer.py"              # T013
Task: "Create coupon_consumption_log/__init__.py"                # T015
Task: "Create coupon_consumption_log.json"                       # T016
Task: "Create coupon_consumption_log.py"                         # T017
Task: "Create test_coupon_consumption_log.py"                    # T018

# Integration tests in test_report_flows.py are sequential (same file):
Task: "Add test_us1_daily_delivery_man_summary_acceptance_scenario_1"  # T019
Task: "Add test_us1_active_booklets_per_customer_acceptance_scenario_2"# T020
Task: "Add test_us1_coupon_consumption_log_acceptance_scenario_4"      # T021
Task: "Add test_us1_export_contract_acceptance_scenario_5"             # T022
Task: "Append Arabic translations for Bundle 1 to ar.csv"              # T023
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 Setup (T001–T003) — anchor + patches wiring.
2. Phase 2 Foundational (T004–T005) — shared seed + test file skeleton.
3. Phase 3 User Story 1 (T006–T023) — Bundle 1.
4. **STOP and VALIDATE**: Quickstart Steps 1–4 pass. Ship Bundle 1 as Phase-7 MVP — the Administrator has the four reports they use every working day.

### Incremental Delivery

1. Phases 1 + 2 → foundation ready.
2. Phase 3 (Bundle 1) → ship to Administrator → feedback.
3. Phase 4 (Bundle 2) → ship to Administrator → feedback.
4. Phase 5 (Bundle 3) → ship to Administrator → feedback.
5. Phase 6 → cross-cutting polish, quickstart walk-through, sign-off.

Each bundle adds independent value without breaking the earlier bundles — no shared report-folder files between bundles.

### Parallel Team Strategy

With three developers and Phase 2 complete:

- Developer A: Phase 3 (Bundle 1 — 4 operational reports)
- Developer B: Phase 4 (Bundle 2 — 4 financial/oversight reports)
- Developer C: Phase 5 (Bundle 3 — 2 analytical reports)

Each works in their own set of `cx_purisol/cx_purisol/report/<name>/` folders. Integration test methods in `test_report_flows.py` must be merged sequentially (same file), but each developer's block is independent. Arabic translations are appended independently by each developer to `ar.csv` (merge conflicts resolvable line by line). Phase 6 runs last after all three bundles land.

---

## Notes

- **Read-only phase**: No Phase-7 code path writes to any Purisol, ERPNext, or Frappe DocType at runtime. Only the test-seed helper writes (to set up test state), and only the migration/patch anchor writes (no-op).
- **Zero new DocTypes, zero new fields, zero new roles, zero new client-side JS, zero new fixtures** — verified by the plan's constitution check.
- **[P] tasks** = different files, no dependencies.
- **[Story] label** maps task to specific user story for traceability; bundles ship independently per SC-007.
- Each bundle is independently completable and testable against `seed_for_<bundle>()`.
- Commit after each bundle checkpoint (recommended: one commit per report folder plus one commit per integration-test block plus one commit per bundle's `ar.csv` append).
- Avoid: cross-bundle report-folder imports (breaks SC-007); modifying the Phase-2 `current_custody_by_delivery_man/` folder (research.md §12).
