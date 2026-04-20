# Phase 1 Data Model — Reports

**Feature**: 007-reports | **Date**: 2026-04-19

Phase 7 introduces **zero new persistent entities**. Every report is a read-only projection over data already established in Phases 1–6. This document catalogues the source tables each report consumes, the join keys between them, and the implicit invariants the reports rely on.

---

## Source Entities (no new tables)

All entities below already exist. Phase 7 only reads.

### `Purisol Coupon Booklet` (Phase 1)

| Field | Type | Used by |
|-------|------|---------|
| `name` | autoname `WP-#####` | every booklet-touching report |
| `status` | Select (`In Stock`, `In Custody`, `Sold`, `Depleted`) | filters across most reports |
| `customer` | Link → Customer | Customer Consumption Rate, Active Booklets per Customer, Coupon Consumption Log |
| `current_delivery_man` | Link → Employee | Current Custody by Delivery Man |
| `sold_on` | Datetime | Active Booklets per Customer, Customer Consumption Rate, Booklet Lifecycle Duration, Booklet Sales Report |
| `depleted_on` | Datetime | Customer Consumption Rate, Booklet Lifecycle Duration |
| `consumed_count`, `remaining_count`, `total_coupons` | Int | Active Booklets per Customer |
| `creation` | Datetime (Frappe-built-in) | Booklet Lifecycle Duration (`avg_generation_to_first_sale`, `avg_full_lifetime`) |
| `batch_id` | Data | optional context column on Current Custody |
| `sales_invoice` | Link → Sales Invoice | not directly read by reports (the sales report goes the other direction) |

### `Purisol Coupon` (Phase 1)

| Field | Type | Used by |
|-------|------|---------|
| `name` | autoname `CP-#####` | Coupon Consumption Log |
| `status` | Select (`Available`, `Consumed`) | Coupon Consumption Log filter (`status = 'Consumed'`) |
| `consumed_on` | Datetime | Coupon Consumption Log (date column + range filter) |
| `consumed_by_delivery_man` | Link → Employee | Coupon Consumption Log (delivery_man column + filter) |
| `consumption_entry` | Link → Purisol Coupon Consumption Entry | Coupon Consumption Log (entry-ref column) |
| `booklet` | Link → Purisol Coupon Booklet | Coupon Consumption Log join key |

### `Purisol Coupon Consumption Entry` (Phase 4) — submittable

| Field | Type | Used by |
|-------|------|---------|
| `name` | autoname `PCC-YYYY-#####` | Coupon Consumption Log (entry-ref column), Daily Delivery Man Summary |
| `posting_date` | Date | Daily Delivery Man Summary (date column + filter), Discrepancy Rate by Delivery Man (date-range filter) |
| `delivery_man` | Link → Employee | Daily Delivery Man Summary, Discrepancy Rate by Delivery Man |
| `total_coupons` | Int | Daily Delivery Man Summary's coupons-submitted column |
| `docstatus` | Int (1 = submitted) | filter (`= 1`) on every join from this table |

### `Purisol Coupon Consumption Item` (Phase 4) — child table of Consumption Entry

| Field | Type | Used by |
|-------|------|---------|
| `parent` | parent name (Frappe built-in) | join back to Consumption Entry for date+delivery_man |
| `coupon` | Link → Purisol Coupon | (not directly used by reports — coupon is the source of consumption rows) |
| `booklet` | Link → Purisol Coupon Booklet | Daily Delivery Man Summary (distinct booklets touched per (date, delivery_man)) |
| `customer` | Link → Customer | (denormalised; not read by Phase-7 reports — they go via booklet → customer) |

### `Purisol Coupon Discrepancy` (Phase 5) — submittable

| Field | Type | Used by |
|-------|------|---------|
| `name` | autoname `PCD-YYYY-#####` | Delivery Man Discrepancies (ID column) |
| `discrepancy_type` | Select (`Missing Coupons`, `Unassigned Booklet`) | Delivery Man Discrepancies (type column) |
| `status` | Select (`Open`, `Under Review`, `Resolved - Admin Error`, `Resolved - Delivery Man Liable`, `Resolved - Paid`) | Delivery Man Discrepancies (status filter + column) |
| `opened_on` | Datetime | Delivery Man Discrepancies (date column + range filter) |
| `triggering_consumption_entry` | Link → Purisol Coupon Consumption Entry | join key for delivery-man attribution: discrepancy → consumption entry → delivery_man (used by Daily Delivery Man Summary, Discrepancy Rate by Delivery Man, Delivery Man Discrepancies) |
| `booklet` | Link → Purisol Coupon Booklet | Delivery Man Discrepancies (booklet column) |
| `liable_delivery_man` | Link → Employee | NOT USED for attribution (may be unset); exposed indirectly via the resolution column |
| `estimated_amount` | Currency | Delivery Man Discrepancies (amount column), Daily Delivery Man Summary (discrepancy_total), Discrepancy Rate by Delivery Man (total discrepancy value) |
| `resolution_action` | Select | Delivery Man Discrepancies (resolution column) |
| `docstatus` | Int (1 = submitted) | filter on every join from this table |

### `Purisol Coupon Discrepancy Coupon` (Phase 5) — child table of Discrepancy

| Field | Type | Used by |
|-------|------|---------|
| `parent` | parent name | join back to Discrepancy for `affected_coupons_count` |
| `coupon` | Link → Purisol Coupon | Delivery Man Discrepancies (counted via `COUNT(*) … GROUP BY parent`) |

### `Purisol Custody Entry` (Phase 2) — submittable

| Field | Type | Used by |
|-------|------|---------|
| `entry_datetime` | Datetime | Current Custody by Delivery Man (`MAX(entry_datetime)` per booklet → days_in_custody) |
| `docstatus` | Int (1 = submitted) | filter on join |

### `Purisol Custody Entry Booklet` (Phase 2) — child table of Custody Entry

| Field | Type | Used by |
|-------|------|---------|
| `parent` | parent name | join back to Custody Entry |
| `booklet` | Link → Purisol Coupon Booklet | Current Custody by Delivery Man join key |

### `Sales Invoice` (ERPNext) — submittable

| Field | Type | Used by |
|-------|------|---------|
| `name` | autoname | Booklet Sales Report (invoice-ref column) |
| `posting_date` | Date | Booklet Sales Report (date column + range filter) |
| `customer` | Link → Customer | Booklet Sales Report (customer column + filter) |
| `selling_price_list` | Link → Price List | Booklet Sales Report (price-list filter) |
| `status` | Select | Booklet Sales Report (status column) |
| `docstatus` | Int (1 = submitted) | filter on join |

### `Sales Invoice Item` (ERPNext) — child table of Sales Invoice

| Field | Type | Used by |
|-------|------|---------|
| `parent` | parent name | join back to Sales Invoice |
| `purisol_booklet` | Link → Purisol Coupon Booklet (custom field, Phase-3 fixture `Sales Invoice Item-purisol_booklet`) | Booklet Sales Report — restricts rows to invoice lines that sold a Purisol booklet |
| `amount` | Currency | Booklet Sales Report (amount column) |

### `GL Entry` (ERPNext)

| Field | Type | Used by |
|-------|------|---------|
| `account` | Link → Account | filter to `Purisol Settings.employee_liability_account` |
| `party_type` | Data | filter to `'Employee'` |
| `party` | Dynamic Link → Employee | join key (the delivery man) |
| `debit_in_account_currency` | Currency | `total_owed = SUM(...)` for Delivery Man Liability Balance |
| `credit_in_account_currency` | Currency | `total_paid = SUM(...)` for Delivery Man Liability Balance |
| `is_cancelled` | Int (0/1) | filter (`= 0`); the GL has its own cancellation marker |

### `Purisol Settings` (Phase 1) — singleton

| Field | Type | Used by |
|-------|------|---------|
| `employee_liability_account` | Link → Account | live read at each `Delivery Man Liability Balance` execution; if unset → info-row fallback (research.md §5) |

### Reference / Lookup tables

- **`Customer`** — appears as filter and column on multiple reports. Phase 7 reads `name` (the link target) and `customer_name` (the human label, optional read for nicer display).
- **`Employee`** — same pattern; Phase 7 reads `name` and `employee_name`.
- **`Price List`** — used as a filter target on Booklet Sales Report. Phase 7 reads `name` only.
- **`Account`** — used as filter target on the GL query. Phase 7 reads `name` only.

---

## Implicit Invariants the Reports Rely On

These invariants are established and enforced by Phases 1–6. Phase 7 reports do not enforce them; they read assuming they hold.

1. **`Purisol Coupon Booklet.depleted_on` is set whenever `status = 'Depleted'`** — Phase 4 sets `depleted_on` when the 20th coupon is consumed. Customer Consumption Rate and Booklet Lifecycle Duration both rely on this. If a booklet is `Depleted` with `depleted_on IS NULL` (a Phase-4 bug), the report's `WHERE b.depleted_on IS NOT NULL` clause defensively excludes it.

2. **`Purisol Coupon Booklet.sold_on` is set whenever `status IN ('Sold', 'Depleted')`** — Phase 3 sets `sold_on` on Sales Invoice submit. Same defensive `WHERE b.sold_on IS NOT NULL` is added to Booklet Lifecycle Duration's `avg_generation_to_first_sale` aggregate.

3. **`Purisol Coupon.consumption_entry` is set whenever `status = 'Consumed'`** — Phase 4 sets it inside the consumption entry's `on_submit`. Coupon Consumption Log relies on this for the entry-ref column.

4. **`Purisol Coupon Discrepancy.triggering_consumption_entry` is always set** — Phase 5 sets it during detection. Daily Delivery Man Summary and Discrepancy Rate by Delivery Man use it as the join key for delivery-man attribution.

5. **Custom field `Sales Invoice Item.purisol_booklet` is non-null exactly for booklet-selling lines** — Phase 3 establishes this. Booklet Sales Report filters `WHERE sii.purisol_booklet IS NOT NULL` to isolate the relevant lines.

6. **GL entries against `Purisol Settings.employee_liability_account` use `party_type = 'Employee'` and `party = <delivery_man.name>`** — Phase 5 establishes this when the discrepancy resolution creates a Journal Entry with the configured employee_liability_account on the Debit side and the Employee party. Delivery Man Liability Balance relies on this convention to attribute owed amounts to a specific delivery man.

7. **Submitted records (`docstatus = 1`) are the source of truth; cancelled records (`docstatus = 2`) and drafts (`docstatus = 0`) are excluded from every Phase-7 report** — uniform `docstatus = 1` filter on every submittable join.

8. **`tabSingles`-stored `Purisol Settings` values are read fresh at each report execution** — no Python-side caching. An admin-edited liability account value takes effect on the next report run.

---

## Per-Report Source Mapping (one-line summary)

| Report | Primary tables | Aggregation key |
|--------|----------------|-----------------|
| Daily Delivery Man Summary | `Purisol Coupon Consumption Entry`, `Purisol Coupon Consumption Item`, `Purisol Coupon Discrepancy` | (posting_date, delivery_man) |
| Active Booklets per Customer | `Purisol Coupon Booklet` | per booklet |
| Current Custody by Delivery Man | `Purisol Coupon Booklet`, `Purisol Custody Entry`, `Purisol Custody Entry Booklet` | per booklet (filtered to `status = In Custody`) |
| Coupon Consumption Log | `Purisol Coupon`, `Purisol Coupon Booklet`, `Purisol Coupon Consumption Entry` | per coupon (filtered to `status = Consumed`) |
| Delivery Man Discrepancies | `Purisol Coupon Discrepancy`, `Purisol Coupon Discrepancy Coupon` (count), `Purisol Coupon Consumption Entry` (delivery_man lookup) | per discrepancy |
| Delivery Man Liability Balance | `GL Entry` (filtered to `account = settings.employee_liability_account, party_type = 'Employee'`), `Employee` | per delivery man (party) |
| Booklet Sales Report | `Sales Invoice Item` (filtered to `purisol_booklet IS NOT NULL`), `Sales Invoice` | per invoice line (one row per booklet sold) |
| Discrepancy Rate by Delivery Man | `Purisol Coupon Consumption Item` (counts), `Purisol Coupon Discrepancy` (counts), `Purisol Coupon Consumption Entry` (delivery_man join) | per delivery man |
| Customer Consumption Rate | `Purisol Coupon Booklet` (filtered to `status = Depleted`) | per customer (`AVG(DATEDIFF(depleted_on, sold_on))`) |
| Booklet Lifecycle Duration | `Purisol Coupon Booklet` | global (3 averages, single row) |

---

## What Phase 7 Does NOT Add

- **No new DocTypes** — zero `Purisol *` Frappe DocTypes are introduced.
- **No new fields on existing DocTypes** — every field a report needs already exists.
- **No new fixtures** — the 9 new `Report` records migrate via `bench migrate`'s standard report sync (each has `is_standard = "Yes"`), not via Frappe's fixture mechanism.
- **No new roles** — `Purisol Administrator` (Phase-0 fixture) is the sole gate.
- **No new client-side JavaScript** — the standard Frappe report viewer renders every report.
- **No new custom field on Sales Invoice / Sales Invoice Item** — the Phase-3 `Sales Invoice Item-purisol_booklet` fixture is reused as-is.
- **No new patches beyond a single no-op anchor** — `cx_purisol.patches.v0_7_0.add_phase_7_reports` is a version marker; it does no schema work.
