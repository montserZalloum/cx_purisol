# Quickstart — Reports (Phase 7)

**Feature**: 007-reports | **Date**: 2026-04-19

A reviewer or QA engineer can verify Phase 7 end-to-end in roughly 15 minutes using the steps below.

---

## Prerequisites

- A Frappe Bench site with `cx_purisol` installed and Phases 1–6 already migrated.
- A user with the `Purisol Administrator` role (Phase 0 fixture).
- A user without that role (any vanilla `User` will do — the quickstart calls them "non-admin").
- A non-empty `Purisol Settings.employee_liability_account` (configured in Phase 1 setup).

---

## Step 1 — Migrate

```bash
bench --site <site> migrate
```

Expected: `bench migrate` synchronises the 9 new `Report` JSON files (each `is_standard = "Yes"`). The `v0_7_0/add_phase_7_reports.py` patch runs as a no-op. Existing Phases 1–6 are untouched.

---

## Step 2 — Verify the reports menu

In the desk, navigate to **Tools → Reports** (or the analogous "Reports" menu).

Expected: under the **Cx Purisol** group you see **10 entries**:
- Active Booklets per Customer
- Booklet Lifecycle Duration
- Booklet Sales Report
- Coupon Consumption Log
- Current Custody by Delivery Man  *(pre-existing — Phase 2)*
- Customer Consumption Rate
- Daily Delivery Man Summary
- Delivery Man Discrepancies
- Delivery Man Liability Balance
- Discrepancy Rate by Delivery Man

(Order may vary by Frappe's default sort.)

---

## Step 3 — Permission gate

Log in as the **non-admin** user. Open the same Reports menu.

Expected: the **Cx Purisol** group either does not appear, or appears empty. Direct URL access (`/app/query-report/Daily%20Delivery%20Man%20Summary`) returns a permission error.

Log back in as the **administrator** user before the next step.

---

## Step 4 — Bundle 1 (Operational) smoke

Open each of the four operational reports in turn. Each should load within 3 seconds against any production-shaped dataset (SC-001).

### 4a. Daily Delivery Man Summary
- No filter set: shows one row per (date, delivery_man) pair seen in any Consumption Entry.
- Set `from_date` = today, `to_date` = today, `delivery_man` = a specific delivery man — observe rows narrow accordingly.
- Discrepancy total cell ties to the sum of `estimated_amount` of discrepancies opened by that delivery man on that date.

### 4b. Active Booklets per Customer
- No filter: shows one row per (customer, booklet) for every booklet in `Sold` or `Depleted` status.
- Set `customer` filter — rows narrow to that customer.
- `days_since_sale` increases by 1 each calendar day.

### 4c. Current Custody by Delivery Man
- Lists every booklet currently `In Custody`.
- Set `delivery_man` filter — only that delivery man's booklets remain.

### 4d. Coupon Consumption Log
- Lists one row per consumed coupon.
- Set a date range — rows narrow.
- Click any row's coupon, booklet, or entry link — navigates to the underlying record.

---

## Step 5 — Bundle 2 (Financial / Oversight) smoke

### 5a. Delivery Man Discrepancies
- Lists every submitted discrepancy.
- Set `status = Open` — rows narrow to open discrepancies.
- The `delivery_man` column shows the delivery man whose Consumption Entry triggered the discrepancy (not necessarily the liable party).

### 5b. Delivery Man Liability Balance
- Reads `Purisol Settings.employee_liability_account` live. Shows one row per delivery man with non-zero GL activity against that account.
- `total_owed`, `total_paid`, `open_balance` tie to the standard GL report for the same account (SC-003 reconciliation property).
- **Failure mode**: temporarily clear `Purisol Settings.employee_liability_account` (or set a non-existent account); rerun — the report shows one info row prompting configuration. Restore the value before continuing.

### 5c. Booklet Sales Report
- Lists one row per Sales Invoice line that sold a Purisol booklet.
- Set `price_list` — only invoices recorded against that selling price list appear (the filter matches the invoice's `selling_price_list`, not the customer's default).
- Cancel a Sales Invoice (in a test environment) — its rows disappear from this report on next refresh (FR-005 / SC-005).

### 5d. Discrepancy Rate by Delivery Man
- Lists one row per delivery man who submitted at least one Consumption Entry in the date range.
- A delivery man with submissions but zero discrepancies appears with `discrepancy_rate = 0%` (no divide-by-zero).
- Rate ties to `100 * discrepancies_count / coupons_submitted` rounded to 2 dp.

---

## Step 6 — Bundle 3 (Analytical) smoke

### 6a. Customer Consumption Rate
- Lists one row per customer who has at least one `Depleted` booklet.
- `avg_days_to_deplete` ties to the arithmetic mean of `(depleted_on - sold_on)` in days across that customer's Depleted booklets.
- Customers with zero Depleted booklets do not appear.

### 6b. Booklet Lifecycle Duration
- Single row of three averages.
- Cells show `null` (rendered as empty) if no booklet has reached the relevant terminal milestone yet.
- Verify against a hand-calculation: if your dataset has booklets generated 30 / 45 / 60 days ago, sold 10 / 20 / 30 days ago, depleted 0 / 5 / 10 days ago, then `avg_full_lifetime = (30 + 40 + 50) / 3 = 40` days.

---

## Step 7 — Export

For any open report, choose **Menu → Print → Download as PDF** and **Menu → Download as Excel**.

Expected: both files download and contain the same rows and columns currently displayed, in the same order, with the same applied filter values.

---

## Step 8 — Run the test suite

```bash
bench --site <site> run-tests --app cx_purisol --module cx_purisol.cx_purisol.tests.test_report_flows
bench --site <site> run-tests --app cx_purisol --module cx_purisol.cx_purisol.report.daily_delivery_man_summary.test_daily_delivery_man_summary
# ... and one per report folder
```

Or simply:

```bash
bench --site <site> run-tests --app cx_purisol
```

Expected: all Phase 1–7 tests pass on a clean test database. The new Phase-7 tests cover:
- One per spec acceptance scenario (US1: 5, US2: 5, US3: 3 = 13 integration tests).
- Per-report unit tests (one folder × one test file × multiple test methods).
- Permissions test (parametrised over all 10 reports — non-admin user is rejected).
- Cancelled-document test (cancel each submittable source type → verify rows disappear).
- GL-reconciliation property test (Delivery Man Liability Balance ties to standard GL aggregate).

---

## Step 9 — Localisation spot-check

Switch the user's interface language to Arabic (`ar`) in **My Settings → Language**. Reload any report.

Expected: column labels, filter labels, and any Script-Report-emitted strings render in Arabic. Numeric and date cells render in the locale-appropriate format (RTL-safe).

---

## Definition of Done

Phase 7 is shipped when:

1. `bench migrate` on a fresh checkout creates all 10 Report records under the `Cx Purisol` module.
2. The Reports menu shows 10 entries under the `Cx Purisol` group for the Administrator and zero entries for non-admin users.
3. Every report's per-report unit test passes (`bench run-tests --app cx_purisol`).
4. The bundle-level integration tests (`tests/test_report_flows.py`) pass — every spec acceptance scenario, every cross-cutting concern.
5. The GL-reconciliation property test passes — `Delivery Man Liability Balance` ties exactly to the standard GL report for the configured account.
6. The cancelled-document test passes — cancelling a Sales Invoice / Consumption Entry / Discrepancy removes its rows from every affected report on next refresh.
7. Excel and PDF exports work for every report (manual smoke).
8. Arabic UI renders correctly (manual smoke).
9. No regression in any Phase 1–6 test (the full suite is green on a clean database).
