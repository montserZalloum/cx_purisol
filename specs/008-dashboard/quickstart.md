# Quickstart — Dashboard (Phase 8)

**Feature**: 008-dashboard | **Date**: 2026-04-19

A reviewer or QA engineer can verify Phase 8 end-to-end in roughly 10 minutes using the steps below.

---

## Prerequisites

- A Frappe Bench site with `cx_purisol` installed and Phases 1–7 already migrated.
- A user with the `Purisol Administrator` role (Phase-0 fixture). The user MUST NOT have a personal `home_settings` preference set (or, if they do, reset it for this verification so the role-default landing applies).
- A user without that role (any vanilla `User` will do — the quickstart calls them "non-admin").
- The Phase-1 `Purisol Settings` configured with a non-zero `customer_low_stock_threshold` (default is 3) and a non-empty `employee_liability_account`.
- A modest seeded dataset including: at least 5 booklets across all four statuses, at least 2 delivery men each holding some In-Custody booklets, at least 2 customers each with 1–3 Sold booklets of varying remaining counts, at least 1 Open discrepancy, at least 1 liability journal entry and matching payment entry, at least 1 depleted-in-the-last-7-days booklet, and at least 3 consumption entries today across different delivery men.

---

## Step 1 — Migrate

```bash
bench --site <site> migrate
```

Expected:
- `bench migrate` synchronises the new `Customers Low on Coupons` Query Report (`is_standard = "Yes"`).
- `bench migrate` synchronises the four new Number Cards, four new Dashboard Charts, and the updated Workspace `مياه نبع النعيم` with its populated widgets from the fixture files.
- The `v0_8_0/add_dashboard_widgets.py` patch runs as a no-op.
- Existing Phase 1–7 fixtures and data are untouched.

---

## Step 2 — Verify default-landing for Administrator

Log in as the **administrator** user. On login (or by clicking the home icon), the active sidebar item should be the Purisol workspace `مياه نبع النعيم`.

Expected: the browser lands on `/app/مياه%20نبع%20النعيم` without any additional navigation.

If the administrator has a personal home page preference set (from a prior session), this step will not pass — clear the preference via **My Settings → Home Settings → Default Workspace = (none)** and retry.

---

## Step 3 — Verify role gate for non-admin

Log in as the **non-admin** user. Observe the sidebar.

Expected: the `مياه نبع النعيم` workspace does NOT appear in the sidebar. Direct URL access (`/app/مياه%20نبع%20النعيم`) returns a permission error or redirects to a non-Purisol workspace.

Log back in as the **administrator** user before the next step.

---

## Step 4 — Bundle 1 (Operational) smoke

With the dashboard open, inspect the Operations row. Each widget must render within 3 seconds (SC-001).

### 4a. Booklets In Stock number card
- Value matches `SELECT COUNT(*) FROM tabPurisol Coupon Booklet WHERE status = 'In Stock'`.
- Clicking the card opens the Coupon Booklet list filtered to `status = "In Stock"`.

### 4b. Booklets In Custody number card + In-Custody Breakdown chart
- Card value matches `status = "In Custody"` count.
- Chart shows one bar per unique `current_delivery_man` among `In Custody` booklets.
- Clicking a bar opens the Coupon Booklet list filtered to `status = "In Custody"` and that `current_delivery_man`.

### 4c. Active Sold Booklets number card
- Value matches `status = "Sold"` count.
- Clicking the card opens the filtered Coupon Booklet list.

### 4d. Today's Consumption chart
- Shows one bar per delivery man who submitted at least one consumption entry today.
- Bar heights match the `coupons_submitted` column from the `Daily Delivery Man Summary` report filtered to today.
- Clicking the chart opens the `Daily Delivery Man Summary` report with `from_date = today`, `to_date = today`.

---

## Step 5 — Bundle 2 (Financial Risk) smoke

### 5a. Open Discrepancies number card
- Card is red-accented always.
- Value matches `SELECT COUNT(*) FROM tabPurisol Coupon Discrepancy WHERE status = 'Open' AND docstatus = 1`.
- Clicking the card opens the Coupon Discrepancy list filtered to `status = "Open"`.

### 5b. Open Discrepancies Quick List
- Lists up to 5 most-recently-opened discrepancies in status `Open` (sort: `modified desc`, which for Open records equals `opened_on desc`).
- Each row shows the discrepancy's key fields; clicking a row opens that discrepancy's detail.
- "View All" button opens the full Open-status list.

### 5c. Outstanding Liabilities chart
- Shows one bar per delivery man with a non-zero GL open balance against the configured liability account.
- Bar heights match the `open_balance` column from the Phase-7 `Delivery Man Liability Balance` report.
- SC-004 reconciliation: run the Phase-7 report side by side; every delivery man's `open_balance` in the report equals the bar height for that delivery man in the chart. Confirm via a hand-spot-check of one row.
- Clicking the chart opens the `Delivery Man Liability Balance` report.

---

## Step 6 — Bundle 3 (Customer Follow-up) smoke

### 6a. Customers Low on Coupons chart
- Shows up to 10 bars, one per customer whose aggregated remaining across Sold booklets is ≤ `Purisol Settings.customer_low_stock_threshold`.
- Bars are sorted ascending by remaining — the customer in most urgent need appears first.
- Clicking the chart opens the `Customers Low on Coupons` report (the new Phase-8 dashboard-support report).

### 6b. Recent Depleted Booklets Quick List
- Lists every Booklet whose `depleted_on` is within the last 7 days, sorted most-recent-first.
- Each row shows the booklet name, customer (if displayed), and depletion date.
- Clicking a row opens the booklet detail.

---

## Step 7 — Threshold live-read verification (SC-007)

While keeping the dashboard open in one tab:

1. Open `Purisol Settings` in another tab and change `customer_low_stock_threshold` from 3 to 5.
2. Save.
3. Go back to the dashboard tab and refresh.

Expected: the Customers Low on Coupons widget now includes customers whose total remaining is 4 or 5 (additional customers appear if any qualify at the new threshold). No code change, no restart, no cache invalidation required.

Change the threshold back to 3 before continuing.

---

## Step 8 — Empty-state verification

(Do this on a fresh test site or after cleaning the dataset.)

Load the dashboard on a site with zero Purisol records.

Expected:
- Number Cards display `0` (not a broken state).
- Dashboard Charts render empty frames with Frappe's default "No data" subtitle.
- Quick Lists show Frappe's default "No records" message.
- No widget fails to render; no error is thrown.

---

## Step 9 — Cancelled-document filter (implicit — relies on underlying queries)

In a test environment:

1. Create and submit one consumption entry that triggers a discrepancy.
2. Note the current Open Discrepancies count on the dashboard.
3. Cancel the discrepancy.
4. Refresh the dashboard.

Expected: the Open Discrepancies count decreases by one; the Quick List drops the cancelled row. `docstatus = 1` filter is doing its job.

---

## Step 10 — Run the test suite

```bash
bench --site <site> run-tests --app cx_purisol --module cx_purisol.cx_purisol.tests.test_dashboard
bench --site <site> run-tests --app cx_purisol --module cx_purisol.cx_purisol.report.customers_low_on_coupons.test_customers_low_on_coupons
```

Or simply:

```bash
bench --site <site> run-tests --app cx_purisol
```

Expected: all Phase 1–8 tests pass on a clean test database. The new Phase-8 tests cover:
- Workspace exists and has the four widget arrays populated.
- Each of the 4 Number Cards and 4 Dashboard Charts exists as a fixture record.
- Workspace role gate: non-admin user cannot open the workspace (PermissionError asserted).
- Default-landing mapping: admin user's login flow resolves to `مياه نبع النعيم`.
- Each widget's underlying query produces the expected row count on the seeded dataset (one test per widget — 8 tests minimum).
- Relative-date token in Quick List evaluates correctly (widget 8 filter `depleted_on >= [Today - 7d]` returns the expected booklets).
- `Customers Low on Coupons` report: acceptance-scenario tests (threshold edge cases, LIMIT 10 cap, Depleted-excluded, Settings-threshold live read).
- US1/US2/US3 acceptance scenarios (5 + 5 + 5 = 15 integration tests).
- Cancelled-document filter verification on the Open Discrepancies widgets.

---

## Step 11 — Localisation spot-check

Switch the user's interface language to Arabic (`ar`) in **My Settings → Language**. Reload the dashboard.

Expected:
- Row headers ("Operations", "Risk Watchlist", "Customer Follow-up") render in Arabic.
- Widget labels render in Arabic.
- Number Card values render in Arabic digits if the locale's `number_format` is configured that way.
- Currency values on the Outstanding Liabilities chart render with Arabic locale numbering.
- Workspace navigation is RTL-safe — no text overflow or broken layout.

---

## Definition of Done

Phase 8 is shipped when:

1. `bench migrate` on a fresh checkout creates the one new Report and populates the extended Workspace with all eight widgets, all four Number Cards, and all four Dashboard Charts from fixtures.
2. The dashboard is the default landing page for the Administrator user (with no personal `home_settings` override) — verified manually and by integration test.
3. Non-admin users cannot see the workspace in the sidebar and get a permission error on direct URL — verified manually and by integration test.
4. Every one of the eight widgets renders within 3 seconds against the seeded dataset — measured manually.
5. Every widget's click-through lands on the correct filtered list, report, or record detail — verified by clicking each.
6. The SC-004 reconciliation property passes — the Outstanding Liabilities widget's bar heights match the Phase-7 Delivery Man Liability Balance report's `open_balance` column exactly.
7. The SC-007 live-refresh property passes — changing `customer_low_stock_threshold` in Settings and refreshing updates the Customers Low on Coupons widget.
8. The cancelled-document filter test passes — cancelling a discrepancy removes its row from the Open Discrepancies widgets on next refresh.
9. The empty-state smoke passes — a fresh test site renders every widget cleanly with zero data.
10. Arabic UI renders correctly (manual smoke).
11. No regression in any Phase 1–7 test (the full suite is green on a clean database).
12. Every new user-facing string is present in `cx_purisol/translations/ar.csv` with an Arabic translation.
