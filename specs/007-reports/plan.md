# Implementation Plan: Reports

**Branch**: `007-reports` | **Date**: 2026-04-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/007-reports/spec.md`

## Summary

Phase 7 ships ten reports — four operational, four financial/oversight, two analytical — on top of the Phase 1–6 stack. Each report is a standard Frappe `Report` document (one folder per report under `cx_purisol/cx_purisol/report/`), discoverable from the Reports menu under the existing `Cx Purisol` module group, and gated to the `Purisol Administrator` role via the report's own `roles` block. The ten reports split cleanly into two report types: **Query Reports** (six reports — single SQL `SELECT` with parameter substitution suffices: Active Booklets per Customer, Current Custody by Delivery Man, Coupon Consumption Log, Delivery Man Discrepancies, Booklet Sales Report, Customer Consumption Rate, Booklet Lifecycle Duration) and **Script Reports** (three reports — Python aggregation across multiple sources: Daily Delivery Man Summary, Delivery Man Liability Balance, Discrepancy Rate by Delivery Man — needed because they cross-join consumption activity with discrepancy aggregates and/or general-ledger balances and require zero-divisor-safe derived columns). One Query Report (`Current Custody by Delivery Man`) **already exists** as a Phase-2 deliverable and is verified in place against the Phase-7 spec rather than rewritten — its existing columns and filters match FR-012 (Delivery Man, Booklet, Days in Custody, Customer, plus an extra Batch ID for context); the only Phase-7 addition is an integration-test row in `tests/test_report_flows.py` that asserts it loads cleanly under the Phase-7 seeded dataset and that the role gate works.

**Cancelled-document filter** (FR-005, SC-005) is implemented uniformly: every query that touches a submittable DocType (`Purisol Coupon Consumption Entry`, `Purisol Coupon Discrepancy`, `Purisol Custody Entry`, `Sales Invoice`, `Journal Entry`, `Payment Entry`) joins on `docstatus = 1` so cancelled and amended-replaced records contribute zero. **Click-through** (FR-006) is automatic: every report column whose `fieldtype` is `Link` renders as a clickable hyperlink to the referenced record in the standard Frappe report viewer — no custom JavaScript is shipped in this phase. **Excel/PDF export** (FR-003, SC-006) is provided by the standard Frappe report viewer's built-in actions and is not re-implemented per report. **Permissions** (FR-004) are enforced by the per-report `roles` block (`[{"role": "Purisol Administrator"}]`), which gates both menu visibility and direct URL access. **Live data** (FR-041) follows naturally — every report runs its query against the operational database on each open/refresh; no caching, no materialised views, no scheduled rebuild step.

**Bundle-by-bundle delivery (SC-007)**: the three bundles are independently shippable because they share zero implementation files — each report is its own folder. The plan lists them in priority order (Bundle 1 P1 Operational, Bundle 2 P2 Financial/Oversight, Bundle 3 P3 Analytical) so the team can ship Bundle 1 first if needed, then Bundle 2, then Bundle 3 — but nothing structural prevents implementing them in parallel.

**Technical approach** (consolidated from research.md):

- **Reports menu group "Purisol"** (FR-001) — Frappe groups standard reports under their owning module's name in the Reports menu. The `module` field on every Phase-7 report JSON is `"Cx Purisol"`, which already shows up as the "Cx Purisol" group in the Reports menu (verified in production via the existing Phase-2 `Current Custody by Delivery Man` report). No additional menu wiring is needed; no Workspace shortcut is introduced in this phase (Workspace shortcuts are a Phase-8 dashboard concern).
- **Per-report folder layout** (matches Phase-2 `Current Custody by Delivery Man`):
  ```
  cx_purisol/cx_purisol/report/<report_name>/
    __init__.py
    <report_name>.json          # Report definition: name, type, filters, columns, query (Query) or roles (Script)
    <report_name>.py            # For Query Reports: a one-line stub explaining auto-discovery. For Script Reports: execute(filters) -> (columns, data)
    test_<report_name>.py       # Per-report sanity test: seeds a deterministic dataset, runs the report, asserts rows
  ```
  Folder name and report name use snake_case and Title Case respectively. Every Phase-7 report's `is_standard = "Yes"` so it ships as part of the app and migrates via `bench migrate`.
- **Query Report SQL conventions**:
  - Parameter substitution uses `%(filter_name)s` placeholders matching the `fieldname` of each filter on the Report JSON. A null/unset filter value is handled with the idiom `(%(filter_name)s IS NULL OR %(filter_name)s = '' OR <column> = %(filter_name)s)` — same as the existing Phase-2 report.
  - Date-range filters use two `Date` filters `from_date` and `to_date`, each individually optional, applied as `(%(from_date)s IS NULL OR <date_col> >= %(from_date)s) AND (%(to_date)s IS NULL OR <date_col> <= %(to_date)s)`.
  - All joined submittable tables include `<alias>.docstatus = 1` in the `WHERE` clause to satisfy FR-005.
  - All `Link`-fieldtype columns expose the underlying record name (booklet name, invoice name, etc.) so the standard report viewer renders them as click-through links per FR-006.
- **Script Report conventions** (for the 3 reports requiring Python aggregation):
  - `execute(filters)` returns `(columns, data)` where `columns` is a list of dicts (`fieldname`, `label`, `fieldtype`, `options`, `width`) and `data` is a list of dicts keyed by `fieldname`.
  - Aggregation queries use `frappe.db.sql(..., as_dict=True)` for grouped intermediate tables, then Python `dict`-based join in `execute()` for cross-aggregate composition (e.g. coupons-submitted joined with discrepancies-count to produce the rate column). Pure-SQL `LEFT JOIN` of two grouped subqueries is also acceptable where it's clearer; the choice is per-report (documented in research.md §4).
  - Zero-divisor-safe rate columns use the Python idiom `rate = round(100 * num / denom, 2) if denom else 0` so a delivery man with zero coupons submitted shows 0% rather than producing a `ZeroDivisionError` (FR-023).
  - Script Reports do not embed SQL in the report JSON; the JSON only carries `report_type = "Script Report"`, `roles`, and metadata. The `.py` file holds `execute(filters)`.
- **`Delivery Man Liability Balance` GL sourcing** (FR-021, SC-003) — the report queries `tab GL Entry` filtered to `account = settings.employee_liability_account`, `party_type = 'Employee'`, and groups by `party`. `total_owed = SUM(debit_in_account_currency)`, `total_paid = SUM(credit_in_account_currency)`, `open_balance = total_owed - total_paid`. The `Purisol Settings.employee_liability_account` field is read fresh at each report run (no caching); if unset the report returns zero rows with a single info row "Configure employee_liability_account in Purisol Settings to enable this report" (research.md §5). Sourcing from the GL — not from the discrepancy records — guarantees the SC-003 reconciliation property (every figure ties to the standard GL report for that account).
- **`Booklet Sales Report` price-list filter** (FR-022 edge case) — the report joins `Sales Invoice Item` (where `purisol_booklet IS NOT NULL`) to `Sales Invoice`, filters by the invoice's `selling_price_list`, and uses the invoice's `posting_date` for the date-range filter. The custom field `purisol_booklet` on `Sales Invoice Item` (Phase-3 fixture) is the join key from invoice line to booklet.
- **`Daily Delivery Man Summary` discrepancy attribution** (FR-010, Assumption "discrepancy total value attributed via triggering consumption entry") — discrepancies are joined to the delivery man via `Purisol Coupon Discrepancy.triggering_consumption_entry` → `Purisol Coupon Consumption Entry.delivery_man`, **not** via `liable_delivery_man` (which may be unset when the report runs). One row per (date, delivery man) where date is `Purisol Coupon Consumption Entry.posting_date`. The `discrepancy_total` column sums `estimated_amount` across the discrepancies opened by that delivery man's submitted-on-that-date consumption entries.
- **`Discrepancy Rate by Delivery Man` denominator and numerator** (FR-023, Assumption block) — denominator is total coupons submitted by that delivery man in the date range (`COUNT(*)` from `Purisol Coupon Consumption Item` joined to its parent `Purisol Coupon Consumption Entry` filtered by `posting_date` range and `delivery_man`); numerator is the count of `Purisol Coupon Discrepancy` records whose `triggering_consumption_entry`'s `delivery_man` is this employee in the date range. Rate is `100 * num / denom` (rounded to 2 dp), `0` when `denom = 0`. Result includes one row per delivery man who has at least one consumption entry in range; delivery men with zero entries in range are omitted (so the report is non-empty and meaningful — matching the spec's "0% rather than producing a divide-by-zero" guidance).
- **`Customer Consumption Rate` averaging** (FR-030) — `AVG(DATEDIFF(b.depleted_on, b.sold_on))` over `Purisol Coupon Booklet` rows where `b.status = 'Depleted'` AND `b.depleted_on IS NOT NULL` AND `b.sold_on IS NOT NULL`, grouped by `b.customer`. Customers with no Depleted booklets are omitted (the SQL `WHERE` simply produces no rows for them).
- **`Booklet Lifecycle Duration` averaging** (FR-031) — three averages computed in a single Script Report:
  - `avg_generation_to_first_sale` = `AVG(DATEDIFF(b.sold_on, b.creation))` over booklets with `b.status IN ('Sold', 'Depleted')` AND `b.sold_on IS NOT NULL`.
  - `avg_sale_to_depletion` = `AVG(DATEDIFF(b.depleted_on, b.sold_on))` over booklets with `b.status = 'Depleted'`.
  - `avg_full_lifetime` = `AVG(DATEDIFF(b.depleted_on, b.creation))` over booklets with `b.status = 'Depleted'`.
  - Empty datasets (no Depleted booklets yet) produce a single row with `null` averages rather than zero rows, so the report always renders meaningfully — Frappe's report viewer handles `null` as "no data".
- **Day arithmetic semantics** (Assumption block) — every "days …" derived column uses MariaDB's `DATEDIFF(end, start)` (or `frappe.utils.date_diff(end, start)` in Script Reports), which returns whole-day counts in the server's configured timezone. Sub-day precision is not required.
- **`Coupon Consumption Log` row count** (FR-013, US1 acceptance scenario 4) — one row per consumed coupon: `tabPurisol Coupon` joined to its `consumption_entry` via the `consumption_entry` Link field, filtered to `c.status = 'Consumed'` AND `cce.docstatus = 1`. Returns `c.consumed_on`, `c.name AS coupon`, `c.booklet`, `b.customer`, `cce.delivery_man`, `c.consumption_entry`. Date-range filter applies to `c.consumed_on::date`.
- **`Active Booklets per Customer` "active" semantics** (FR-011) — the report includes both `Sold` (in-flight) and `Depleted` (terminal) booklets so the Administrator can see the customer's full purchase history at a glance; the consumed/remaining/days-since-sale columns reveal which are still active. The customer filter is required-when-set; without it the report lists all customer-owned booklets across all customers (useful for global queries). Ordering: customer ASC, sold_on DESC.
- **`Current Custody by Delivery Man` re-use** — the existing Phase-2 Query Report at `cx_purisol/cx_purisol/report/current_custody_by_delivery_man/` already implements FR-012 with the right columns (delivery man, booklet, days_in_custody, customer, plus an extra `batch_id`) and the right `roles` gate (`Purisol Administrator`). Phase 7 does NOT modify this report. The Phase-7 integration test suite does add a smoke-test row that confirms (a) the report continues to render under the Phase-7 seeded dataset and (b) the role gate still rejects a non-administrator user — both are FR-004 reconfirmation rather than new behaviour.
- **Test seeding** (US1/US2/US3 Independent Test) — a new helper module `cx_purisol/cx_purisol/tests/report_seed.py` builds a deterministic, hand-calculable dataset spanning all 10 reports: 3 customers, 4 delivery men, 6 booklets in mixed states (some In Stock, some In Custody assigned 5 days ago / 1 day ago, some Sold today / yesterday / 30/45/60 days ago, some Depleted with known sold_on/depleted_on offsets), several Consumption Entries (some triggering depletions, some triggering Missing-Coupons discrepancies and Unassigned-Booklet discrepancies in different resolution states), Sales Invoices at two price lists, Journal Entries and Payment Entries against the configured liability account for two of the four delivery men. Every per-report test (`test_<report_name>.py`) and every integration test (`tests/test_report_flows.py`) consumes this single seed function, so the dataset is built once per `setUp` and the assertions reference known constants (e.g. "delivery man A's discrepancy rate is 4%"). Helpers reuse and extend Phases 1–6 fixtures (`make_booklet_in_stock`, `submit_assign`, `make_employee`, `seed_open_discrepancy`, `seed_administrator_user`, etc.) — no new low-level fixture is needed beyond `report_seed.py`'s composition layer.
- **Tests**:
  - **Per-report unit tests** in each `report/<name>/test_<name>.py`: seeds a small targeted dataset (often a subset of `report_seed.py` or a hand-built one), invokes either `frappe.db.sql(_REPORT_SQL, params, as_dict=True)` (Query Reports — pattern from Phase-2) or `execute({...})` from the Script Report module (Script Reports), and asserts rows/columns/totals/derived-column values. Each Query Report test mirrors the Phase-2 pattern (in-file `_REPORT_SQL` constant + `_run_report(...)` helper); each Script Report test imports `execute` directly from the report module.
  - **Bundle-level integration tests** in `cx_purisol/cx_purisol/tests/test_report_flows.py`: one test per User Story acceptance scenario from the spec (US1: 5 scenarios → 5 tests; US2: 5 scenarios → 5 tests; US3: 3 scenarios → 3 tests). Each test seeds via `report_seed.py`, runs the relevant report(s), and asserts the exact behaviour the spec calls out (e.g. "delivery man B does not appear in the Current Custody report when they hold zero booklets", "cancelled invoice is excluded from Booklet Sales Report row count").
  - **Permissions test** in `tests/test_report_flows.py`: a parametrised test that, for each of the 10 reports, sets `frappe.set_user(<non_admin_user>)` and asserts that calling Frappe's `get_report_doc` / direct execution returns a permission error or empty result. Confirms FR-004 / SC-005 across all 10.
  - **Cancelled-document test** (one per submittable source): cancel a submitted Sales Invoice → assert it disappears from Booklet Sales Report; cancel a Consumption Entry → assert its rows disappear from Coupon Consumption Log and Daily Delivery Man Summary; cancel a Discrepancy → assert it disappears from Delivery Man Discrepancies and from the Daily Delivery Man Summary's discrepancy_total. Confirms FR-005 / SC-005.
  - **Liability-vs-GL reconciliation test** (SC-003): run `Delivery Man Liability Balance` for a delivery man with mixed liability JEs and offsetting Payment Entries, and assert that `total_owed`, `total_paid`, `open_balance` match the corresponding `frappe.get_all("GL Entry", ...)` aggregate against the same `account` and `party`. Catches drift between the Phase-7 report's logic and the standard GL.
- **No new DocTypes, no new fields, no new client-side JS, no new roles** — Phase 7 is a pure read-only reporting layer over Phase 1–6 data. The only files added are 9 report folders plus one shared seed helper plus the integration test file plus a `__init__.py` in each new folder.
- **Translations** — every `label`, every column header, every Script Report `_("...")` string is translatable. Arabic strings are appended to `cx_purisol/translations/ar.csv` as part of this phase. Filter labels and column labels in the report JSONs are stored in English; Frappe's `_()` machinery translates them at render time using the active user's locale.
- **`patches.txt`** — one new no-op anchor entry `cx_purisol.patches.v0_7_0.add_phase_7_reports` matching the Phase-2/3/4/5/6 pattern. Reports themselves migrate via `bench migrate`'s standard `Report` doctype synchronisation (each report JSON has `is_standard = "Yes"`); the patch exists only to provide a consistent upgrade-version marker for the phase.

## Technical Context

**Language/Version**: Python 3.10+ (Frappe server). No JavaScript is added in this phase — the standard Frappe report viewer renders all ten reports without per-report JS.
**Primary Dependencies**: Frappe Framework 15.x (`Report` DocType, `Notification Log` is unrelated, `frappe.db.sql`, `frappe.utils.date_diff`, `frappe.utils.nowdate`), ERPNext 15.x (`Sales Invoice`, `Sales Invoice Item` with the Phase-3 `purisol_booklet` custom field, `Journal Entry`, `Payment Entry`, `GL Entry`, `Account`, `Customer`, `Employee`, `Price List`). No new third-party libraries. Reuses Phase-1 `Purisol Coupon Booklet` (status, customer, sold_on, depleted_on, consumed_count, remaining_count, current_delivery_man, batch_id, creation), Phase-1 `Purisol Coupon` (status, consumed_on, consumed_by_delivery_man, consumption_entry, booklet), Phase-2 `Purisol Custody Entry` (entry_datetime, docstatus) + `Purisol Custody Entry Booklet` (booklet, parent), Phase-3 `Sales Invoice Item.purisol_booklet` custom field + `Sales Invoice` (posting_date, customer, selling_price_list, status, docstatus), Phase-4 `Purisol Coupon Consumption Entry` (posting_date, delivery_man, docstatus, total_coupons) + `Purisol Coupon Consumption Item` (coupon, booklet, customer), Phase-5 `Purisol Coupon Discrepancy` (discrepancy_type, status, opened_on, triggering_consumption_entry, booklet, customer, liable_delivery_man, estimated_amount, resolution_action, journal_entry, payment_entry, docstatus) + `Purisol Coupon Discrepancy Coupon` (coupon, parent), Phase-1 `Purisol Settings.employee_liability_account` (the GL-account setting). The Phase-2 `Current Custody by Delivery Man` Query Report is reused unmodified.
**Storage**: Frappe DocTypes on MariaDB via `frappe.db.sql` (read-only) and `frappe.db.get_value` / `frappe.get_all` (read-only) only; no `frappe.db.insert` / `frappe.db.set_value` writes are introduced anywhere in Phase 7. Zero new DocTypes, zero schema changes, zero new fields. All Phase-7 code paths are read-only — they never mutate any record.
**Testing**: Frappe test framework (`frappe.tests.utils.FrappeTestCase`), invoked via `bench --site <test-site> run-tests --app cx_purisol`. Per-report tests follow the Phase-2 `test_current_custody_by_delivery_man.py` pattern (in-file `_REPORT_SQL` constant + `_run_report(...)` helper for Query Reports; direct `execute(filters)` import for Script Reports). Bundle-level integration tests live in `cx_purisol/cx_purisol/tests/test_report_flows.py` and consume the new shared seed helper `cx_purisol/cx_purisol/tests/report_seed.py`. Phase 7 tests are read-only over the seeded dataset — no test mutates state mid-test.
**Target Platform**: Linux server running Frappe Bench (gunicorn + RQ workers + MariaDB + Redis). Reports render in the Frappe desk via the built-in report viewer (`/app/query-report/<Report Name>` for Query Reports, same URL for Script Reports — the viewer handles both transparently).
**Project Type**: Frappe custom app (`cx_purisol`) — adds 9 new report folders under `cx_purisol/cx_purisol/report/`, one shared seed-helper module (`tests/report_seed.py`), one new integration-test file (`tests/test_report_flows.py`), and one no-op patch anchor (`patches/v0_7_0/add_phase_7_reports.py` + `__init__.py`). One existing report (`current_custody_by_delivery_man/`) is verified in place but not modified. Zero new DocTypes, zero new fields, zero new roles, zero new client-side JS, zero new custom-field fixtures.
**Performance Goals**:
- **SC-001 target**: Each report renders within 3 seconds at the documented scale (10,000 coupons, 500 booklets, 50 delivery men, 200 customers). All Query Reports use index-friendly predicates: `status` (existing index on the booklet/coupon select-field), `customer` and `current_delivery_man` (Link fields are indexed by Frappe), `posting_date` and `consumed_on` (Date columns on submittable docs are typically indexed; verified at integration-test time and an index is added in the per-report folder if not present — this is the only schema-adjacent action Phase 7 may take, and only if the EXPLAIN plan shows a full table scan).
- **Script Reports** — at the worst-case scale, the `Discrepancy Rate by Delivery Man` script does at most 50 outer-loop iterations (one per delivery man) over two ~200-row aggregate intermediates → trivially under 1 s. The `Daily Delivery Man Summary` does at most 50 × N_days iterations; for a one-week filter that's 350 rows → under 1 s.
- **GL queries** — the `Delivery Man Liability Balance` GL `SUM(...) GROUP BY party` over a single account is well under 1 s at MVP scale (the liability account holds at most a few hundred entries per year).
**Constraints**:
- **Read-only** — Phase 7 introduces zero writes to the operational database. Every code path is `SELECT`-only. The "live data" requirement (FR-041, SC-001 implicit) is satisfied by re-querying on each open/refresh; no caching layer is introduced.
- **No new schema** — Phase 7 introduces zero new DocTypes, zero new fields, zero new roles, zero new fixtures. The only "new" DocType-shaped artefacts are the 9 `Report` JSON files, which are themselves Frappe-native records and migrate via `bench migrate`'s standard report sync.
- **Permission-gated by role** — every report's `roles` block is `[{"role": "Purisol Administrator"}]`. Frappe gates both menu visibility and direct URL access via this list. No additional `permission_query_conditions` hook is needed because the reports do not expose any data the Administrator role cannot already read via the underlying DocTypes (the Administrator already has `read` permission on every Purisol DocType from Phases 1–6).
- **Cancelled-document filter is uniform** — every query that reads a submittable DocType joins on `docstatus = 1`. Phase 7 does NOT show cancelled records, even with explanatory annotation. This matches FR-005 / SC-005 and the spec's "amended replacement is the version reflected in reports, the cancelled original is excluded" rule.
- **Click-through is automatic** — every Link-fieldtype column is rendered as a clickable hyperlink by the standard Frappe report viewer. No custom JS, no custom column formatter is shipped.
- **Excel/PDF export is the platform's** — Phase 7 does not implement export. The standard Frappe report viewer's Menu → "Print" / "Export" / "Download as Excel" actions handle this for both Query and Script Reports.
- **Localisation** — every fixed user-facing string in Script Report Python (column labels, "no data" indicators) is wrapped in `frappe._()`. Query Report column and filter labels in JSON are stored in English; Frappe translates them at render time. Arabic translations land in `cx_purisol/translations/ar.csv` as part of the phase.
- **Bundle independence (SC-007)** — the three bundles share zero report-folder files. A test that exercises only Bundle 2 runs without any Bundle 1 or Bundle 3 file being imported. The shared seed helper (`tests/report_seed.py`) is structured so each bundle's integration tests import only the seed slices they need (e.g. Bundle 3 calls `seed_for_analytics()`; Bundle 1 calls `seed_for_operations()`; the two share underlying primitives but invoke independent top-level entry points).
- **Liability-balance reconciliation (SC-003)** — the `Delivery Man Liability Balance` report sources figures exclusively from `tabGL Entry` filtered to the configured liability account. It does NOT cross-check against the discrepancy records (which would risk drift if a JE is later voided or amended outside the discrepancy flow). This is an explicit design choice for ledger fidelity.

**Scale/Scope**: Single shop. 10 reports. ~10 SQL queries (one per Query Report) + ~3 Python `execute()` functions (one per Script Report). Worst-case dataset (production ceiling): 10,000 coupons, 500 booklets, 50 delivery men, 200 customers, ~3,000 consumption entries, ~500 discrepancies, ~2,000 sales invoices, ~5,000 GL entries against the liability account. All Phase-7 queries are designed to render within 3 s at this scale on a modest server (verified by integration-test EXPLAIN inspection on the 10-record seed and validated manually at the worst-case scale before phase sign-off).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution version: **1.0.0** (10 principles). The plan-template's Constitution Check section is still a placeholder (known TODO in the Sync Impact Report). The 10 principles below are evaluated explicitly for this phase.

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Naming Convention | **PASS** | Phase 7 adds zero new DocTypes, so no `Purisol `-prefix obligation is triggered for entities. The 9 new `Report` records are Frappe-native, not Purisol-domain DocTypes; their `name` field uses Title Case English ("Daily Delivery Man Summary", "Coupon Consumption Log", etc.) per Frappe convention for built-in reports — the prefix rule does not apply. The reports' SQL exclusively reads from already-correctly-prefixed `Purisol …` tables. |
| II | Leverage ERPNext Primitives | **PASS** | Phase 7 is built entirely on Frappe's native `Report` DocType (Query Report + Script Report). No custom report engine, no custom rendering layer, no custom export pipeline, no custom permission filter — every report exposed in this phase is a standard Frappe Report whose JSON migrates via `bench migrate` and whose runtime behaviour is provided by Frappe core. The `Delivery Man Liability Balance` report sources figures from ERPNext's `GL Entry` table — the canonical primitive for ledger balances — rather than building a parallel "delivery_man_balance" custom DocType. The `Booklet Sales Report` reads `Sales Invoice` + `Sales Invoice Item` directly via the Phase-3 custom-field join key, not a custom "Purisol Sale Log" DocType. The reuse of the existing Phase-2 `Current Custody by Delivery Man` report (rather than a Phase-7 rewrite) is itself a Principle-II win. |
| III | State Machine Enforcement | **PASS** | Phase 7 introduces zero new stateful DocTypes and does NOT widen any existing state machine. The reports observe state (booklet status, coupon status, consumption entry docstatus, discrepancy status, invoice docstatus) but never mutate it. The `Current Custody by Delivery Man` query filters by `b.status = 'In Custody'` — read-only inspection. |
| IV | Audit Trail by Default | **PASS** | Phase 7 does not write to any DocType — there is no audit trail to add, because there is nothing to audit. The reports themselves are observation surfaces over the audit trail Phases 1–6 already established (every booklet state change is a submittable Custody/Consumption entry; every discrepancy resolution is a submittable Discrepancy with a linked Journal/Payment entry; every sale is a Sales Invoice). The `cancelled-document filter` (`docstatus = 1` everywhere) ensures the reports reflect the audit trail as it stands — cancelled records are visible in the standard Frappe `Version` audit view but excluded from operational/financial totals, which is the correct "as-of-now" view for an Administrator. |
| V | Error Handling Semantics | **PASS** | Phase 7's only error class is **infrastructure failures** (DB connection lost, malformed filter input from a misconfigured client). These propagate via Frappe's standard exception path — the report viewer shows the error and the user retries. There is no domain rule to enforce in a read-only reporting layer (no "blocking error" for displaying a row, no "warning discrepancy" for an aggregate). The "missing configuration" case for `Delivery Man Liability Balance` (when `Purisol Settings.employee_liability_account` is unset) is handled by returning zero rows with a single info row "Configure employee_liability_account in Purisol Settings to enable this report" — this is a UX pattern, not a domain rule, and it does NOT violate constitution V because no audit/financial/data-integrity concern is at stake. The choice between "raise" and "show info row" was made in research.md §5: showing an info row keeps the report viewer usable (the user can fix the setting and re-run); raising would crash the viewer and provide a worse UX with no safety benefit. |
| VI | Role Model | **PASS** | Zero new roles. Every Phase-7 report's `roles` block is `[{"role": "Purisol Administrator"}]` — the sole MVP role. Delivery men (Employees) are subjects of report rows (they appear as values in delivery-man columns) but not consumers of reports — they have no system access in MVP, consistent with Principle VI. No `permission_query_conditions` hook is added because the Administrator already has read access to every underlying DocType, and the role-gate at the report level is sufficient to satisfy FR-004. |
| VII | Notification Channel | **N/A** | Phase 7 ships zero notifications. The principle is preserved by non-action — Phase 7 does not introduce any notification trigger, channel, or event. The Phase-6 `Purisol Notify` utility is unrelated to this phase. |
| VIII | Background Jobs | **PASS** | Phase 7 reports run synchronously in the request thread because each query returns at most a few hundred rows at MVP-target scale and renders in well under 3 s (SC-001). No `frappe.enqueue` is introduced. Reports do NOT create or update records, so the 100-record-write threshold from Principle VIII is irrelevant. If the data scale grows by orders of magnitude in a future phase, individual reports can opt into Frappe's `prepared_report = 1` flag (a one-line JSON change that re-routes the report through the platform's background-render queue) — no Phase-7 code change required. |
| IX | Localization | **PASS** | Every column label and filter label in the 9 new report JSONs is stored in English; Frappe wraps them in `_()` at render time and substitutes from `cx_purisol/translations/ar.csv`. Every `_("...")` string introduced in Script Report Python (column metadata constructed in `execute(filters)`, the "Configure employee_liability_account" info row) is wrapped in `frappe._()` and translated. Numeric and date formatting in Script Reports uses `frappe.utils.fmt_money` (where currency applies) and `frappe.utils.formatdate` (where date display matters), both of which are locale-aware. The standard Frappe report viewer is RTL-safe out of the box. No hardcoded LTR string concatenation is introduced. |
| X | Testing Discipline | **PASS** | Each of the 9 new reports ships with a per-report unit test (`report/<name>/test_<name>.py`) that seeds a deterministic small dataset and asserts every row, column, and derived value. The existing Phase-2 `Current Custody by Delivery Man` already has its test (`test_current_custody_by_delivery_man.py`) — Phase 7 adds a smoke-test row in the integration suite to confirm it still passes under the Phase-7 seeded dataset. Bundle-level integration tests in `tests/test_report_flows.py` cover every spec acceptance scenario (US1: 5, US2: 5, US3: 3 = 13 integration tests) plus the cross-cutting concerns (permissions per report, cancelled-document filter per source, GL-reconciliation property test). All tests use `FrappeTestCase`. Phases 1–6 tests continue to pass unmodified — Phase 7 is read-only and additive. |

**No violations.** Complexity Tracking table is intentionally empty.

## Project Structure

### Documentation (this feature)

```text
specs/007-reports/
├── plan.md              # This file (/speckit.plan command output)
├── spec.md              # Feature specification (already written)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/
│   └── reports.md       # Phase 1: per-report contract (filters, columns, query semantics, source tables)
├── checklists/
│   └── requirements.md  # Spec quality checklist (already written)
└── tasks.md             # Phase 2 output (/speckit.tasks command — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
cx_purisol/                                                         # Git repo root; Frappe app package
├── cx_purisol/                                                     # Python package root
│   ├── patches.txt                                                 # *** MODIFIED *** — append v0_7_0 anchor
│   ├── patches/
│   │   └── v0_7_0/
│   │       ├── __init__.py                                         # *** NEW ***
│   │       └── add_phase_7_reports.py                              # *** NEW *** — no-op anchor; reports migrate via bench migrate
│   ├── translations/
│   │   └── ar.csv                                                  # *** MODIFIED *** — Arabic strings for column labels and Script Report _()-wrapped phrases
│   └── cx_purisol/                                                 # Module folder ("Cx Purisol")
│       ├── report/
│       │   ├── current_custody_by_delivery_man/                    # *** UNCHANGED *** (Phase-2; Phase-7 verifies via integration test only)
│       │   ├── daily_delivery_man_summary/                         # *** NEW *** Bundle 1, Script Report
│       │   │   ├── __init__.py
│       │   │   ├── daily_delivery_man_summary.json
│       │   │   ├── daily_delivery_man_summary.py                   # execute(filters) -> (columns, data)
│       │   │   └── test_daily_delivery_man_summary.py
│       │   ├── active_booklets_per_customer/                       # *** NEW *** Bundle 1, Query Report
│       │   │   ├── __init__.py
│       │   │   ├── active_booklets_per_customer.json
│       │   │   ├── active_booklets_per_customer.py                 # auto-discovery stub
│       │   │   └── test_active_booklets_per_customer.py
│       │   ├── coupon_consumption_log/                             # *** NEW *** Bundle 1, Query Report
│       │   │   ├── __init__.py
│       │   │   ├── coupon_consumption_log.json
│       │   │   ├── coupon_consumption_log.py
│       │   │   └── test_coupon_consumption_log.py
│       │   ├── delivery_man_discrepancies/                         # *** NEW *** Bundle 2, Query Report
│       │   │   ├── __init__.py
│       │   │   ├── delivery_man_discrepancies.json
│       │   │   ├── delivery_man_discrepancies.py
│       │   │   └── test_delivery_man_discrepancies.py
│       │   ├── delivery_man_liability_balance/                     # *** NEW *** Bundle 2, Script Report
│       │   │   ├── __init__.py
│       │   │   ├── delivery_man_liability_balance.json
│       │   │   ├── delivery_man_liability_balance.py               # execute(filters) — GL-sourced aggregate
│       │   │   └── test_delivery_man_liability_balance.py
│       │   ├── booklet_sales_report/                               # *** NEW *** Bundle 2, Query Report
│       │   │   ├── __init__.py
│       │   │   ├── booklet_sales_report.json
│       │   │   ├── booklet_sales_report.py
│       │   │   └── test_booklet_sales_report.py
│       │   ├── discrepancy_rate_by_delivery_man/                   # *** NEW *** Bundle 2, Script Report
│       │   │   ├── __init__.py
│       │   │   ├── discrepancy_rate_by_delivery_man.json
│       │   │   ├── discrepancy_rate_by_delivery_man.py             # execute(filters) — coupons-submitted ÷ discrepancies-count
│       │   │   └── test_discrepancy_rate_by_delivery_man.py
│       │   ├── customer_consumption_rate/                          # *** NEW *** Bundle 3, Query Report
│       │   │   ├── __init__.py
│       │   │   ├── customer_consumption_rate.json
│       │   │   ├── customer_consumption_rate.py
│       │   │   └── test_customer_consumption_rate.py
│       │   └── booklet_lifecycle_duration/                         # *** NEW *** Bundle 3, Script Report
│       │       ├── __init__.py
│       │       ├── booklet_lifecycle_duration.json
│       │       ├── booklet_lifecycle_duration.py                   # execute(filters) — three averages
│       │       └── test_booklet_lifecycle_duration.py
│       └── tests/
│           ├── report_seed.py                                      # *** NEW *** — deterministic seed used by per-report and integration tests
│           ├── test_report_flows.py                                # *** NEW *** — integration tests covering all US1/US2/US3 acceptance scenarios + permissions + cancelled-doc + GL reconciliation
│           └── (existing fixtures.py, test_*.py from Phases 1–6 unchanged)
└── specs/007-reports/                                              # This plan
```

**Structure Decision**: Standard Frappe custom-app layout, consistent with Phases 1–6. Each of the 9 new reports lives in its own folder under `cx_purisol/cx_purisol/report/` matching the existing Phase-2 pattern. Query Reports embed their SQL in the JSON; Script Reports keep `execute(filters)` in the `.py` file alongside an empty JSON `query` field. Per-report tests sit alongside their report folder; bundle-level integration tests live in `cx_purisol/cx_purisol/tests/test_report_flows.py` and consume the new shared seed helper `cx_purisol/cx_purisol/tests/report_seed.py`. No new DocTypes, no new fields, no new fixtures, no new hooks, no new client-side JS, no new roles. One no-op patches anchor (`v0_7_0/add_phase_7_reports.py`) matches the Phase-2/3/4/5/6 pattern.

## Complexity Tracking

> No constitutional violations; table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
