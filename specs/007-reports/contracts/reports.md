# Phase 1 Contracts — Reports

**Feature**: 007-reports | **Date**: 2026-04-19

This document defines the behavioural contract for each of the 10 reports — the filters, the columns, the filter-to-row semantics, and the exact source-table predicates. Each contract is verifiable by the per-report unit test under `cx_purisol/cx_purisol/report/<name>/test_<name>.py`.

Conventions used throughout:
- **`docstatus = 1`** is shorthand for the uniform "submitted, non-cancelled" filter applied to every join on a submittable DocType.
- **`<filter> IS NULL OR <col> = <filter>`** is the optional-filter idiom used in every Query Report SQL.
- All Date filters are optional. All Link filters are optional. No filter is required across any Phase-7 report.
- All Link-typed columns are clickable in the standard Frappe report viewer (FR-006); no custom JS is shipped.

---

## Bundle 1 — Operational Reports (P1)

### R1. Daily Delivery Man Summary

**Type**: Script Report
**Roles**: `Purisol Administrator`
**Module**: `Cx Purisol`

**Filters**:
| Fieldname | Type | Required | Notes |
|-----------|------|----------|-------|
| `from_date` | Date | No | matches `Purisol Coupon Consumption Entry.posting_date >=` |
| `to_date` | Date | No | matches `Purisol Coupon Consumption Entry.posting_date <=` |
| `delivery_man` | Link → Employee | No | matches `Purisol Coupon Consumption Entry.delivery_man =` |

**Columns** (in display order):
| Fieldname | Label | Type | Options/Notes |
|-----------|-------|------|---------------|
| `posting_date` | Date | Date | grouping key |
| `delivery_man` | Delivery Man | Link | Employee |
| `coupons_submitted` | Coupons Submitted | Int | `SUM(Purisol Coupon Consumption Item.<rows>)` per (date, delivery_man) |
| `booklets_touched` | Booklets Touched | Int | `COUNT(DISTINCT booklet)` per (date, delivery_man) |
| `discrepancies_count` | Discrepancies | Int | `COUNT(Purisol Coupon Discrepancy)` whose `triggering_consumption_entry`'s (date, delivery_man) matches |
| `discrepancy_total` | Discrepancy Total | Currency | `SUM(estimated_amount)` over the same set |

**Aggregation logic** (Python in `execute(filters)`):
1. `coupons_per_pair`: SQL `SELECT cce.posting_date, cce.delivery_man, COUNT(*) AS n FROM tabPurisol Coupon Consumption Item ci JOIN tabPurisol Coupon Consumption Entry cce ON cce.name = ci.parent WHERE cce.docstatus = 1 AND <date-range> AND <delivery-man-filter> GROUP BY cce.posting_date, cce.delivery_man`.
2. `booklets_per_pair`: SQL same but `COUNT(DISTINCT ci.booklet) AS n`.
3. `discrepancies_per_pair`: SQL `SELECT cce.posting_date, cce.delivery_man, COUNT(*) AS n, COALESCE(SUM(d.estimated_amount), 0) AS total FROM tabPurisol Coupon Discrepancy d JOIN tabPurisol Coupon Consumption Entry cce ON cce.name = d.triggering_consumption_entry WHERE d.docstatus = 1 AND cce.docstatus = 1 AND <date-range on cce.posting_date> AND <delivery-man-filter on cce.delivery_man> GROUP BY cce.posting_date, cce.delivery_man`.
4. Python merge: produce one row per (posting_date, delivery_man) appearing in any of the three intermediates; missing values default to 0.

**Acceptance reference**: spec US1 acceptance scenario 1.

---

### R2. Active Booklets per Customer

**Type**: Query Report
**Roles**: `Purisol Administrator`
**Module**: `Cx Purisol`

**Filters**:
| Fieldname | Type | Required | Notes |
|-----------|------|----------|-------|
| `customer` | Link → Customer | No | matches `Purisol Coupon Booklet.customer =` |

**Columns**:
| Fieldname | Label | Type | Notes |
|-----------|-------|------|-------|
| `customer` | Customer | Link → Customer | |
| `booklet` | Booklet | Link → Purisol Coupon Booklet | renders as `b.name` |
| `status` | Status | Data | `b.status` |
| `consumed_count` | Consumed | Int | |
| `remaining_count` | Remaining | Int | |
| `sold_on` | Sold On | Date | from `b.sold_on` (datetime cast to date for display) |
| `days_since_sale` | Days Since Sale | Int | `DATEDIFF(NOW(), b.sold_on)` |

**SQL skeleton**:
```sql
SELECT
    b.customer,
    b.name AS booklet,
    b.status,
    b.consumed_count,
    b.remaining_count,
    b.sold_on,
    DATEDIFF(NOW(), b.sold_on) AS days_since_sale
FROM `tabPurisol Coupon Booklet` b
WHERE b.status IN ('Sold', 'Depleted')
  AND b.customer IS NOT NULL
  AND (%(customer)s IS NULL OR %(customer)s = '' OR b.customer = %(customer)s)
ORDER BY b.customer, b.sold_on DESC
```

**Notes**:
- Includes both `Sold` (in-flight) and `Depleted` (terminal) booklets so the Administrator sees the customer's full purchase history.
- `b.customer IS NOT NULL` excludes booklets that are `In Stock` or `In Custody` (which by definition have no customer yet).

**Acceptance reference**: spec US1 acceptance scenario 2.

---

### R3. Current Custody by Delivery Man  *(EXISTING — Phase 2)*

**Type**: Query Report (already exists at `cx_purisol/cx_purisol/report/current_custody_by_delivery_man/`)
**Roles**: `Purisol Administrator`
**Module**: `Cx Purisol`

**Filters**: `delivery_man` (Link → Employee), `batch_id` (Data) — both optional.

**Columns**: `current_delivery_man`, `booklet`, `days_in_custody`, `customer`, `batch_id`.

**SQL** (verbatim from existing JSON):
```sql
SELECT
    b.current_delivery_man,
    b.name AS booklet,
    COALESCE(DATEDIFF(NOW(), MAX(e.entry_datetime)), 0) AS days_in_custody,
    b.customer,
    b.batch_id
FROM `tabPurisol Coupon Booklet` b
LEFT JOIN `tabPurisol Custody Entry Booklet` eb ON eb.booklet = b.name
LEFT JOIN `tabPurisol Custody Entry` e ON e.name = eb.parent AND e.docstatus = 1
WHERE b.status = 'In Custody'
AND (%(delivery_man)s IS NULL OR b.current_delivery_man = %(delivery_man)s)
AND (%(batch_id)s IS NULL OR b.batch_id = %(batch_id)s)
GROUP BY b.name
ORDER BY b.current_delivery_man, b.name
```

**Phase-7 action**: Verify in place via integration test (no JSON or Python change). The integration test (US1 acceptance scenario 3) seeds two delivery men and confirms the row counts and `days_in_custody` values match.

---

### R4. Coupon Consumption Log

**Type**: Query Report
**Roles**: `Purisol Administrator`
**Module**: `Cx Purisol`

**Filters**:
| Fieldname | Type | Required | Notes |
|-----------|------|----------|-------|
| `from_date` | Date | No | matches `c.consumed_on >=` |
| `to_date` | Date | No | matches `c.consumed_on <=` (inclusive day) |
| `delivery_man` | Link → Employee | No | matches `c.consumed_by_delivery_man =` |
| `customer` | Link → Customer | No | matches `b.customer =` |
| `booklet` | Link → Purisol Coupon Booklet | No | matches `c.booklet =` |

**Columns**:
| Fieldname | Label | Type | Notes |
|-----------|-------|------|-------|
| `consumed_on` | Consumed On | Datetime | from `c.consumed_on` |
| `coupon` | Coupon | Link → Purisol Coupon | from `c.name` |
| `booklet` | Booklet | Link → Purisol Coupon Booklet | from `c.booklet` |
| `customer` | Customer | Link → Customer | from `b.customer` |
| `delivery_man` | Delivery Man | Link → Employee | from `c.consumed_by_delivery_man` |
| `consumption_entry` | Entry | Link → Purisol Coupon Consumption Entry | from `c.consumption_entry` |

**SQL skeleton**:
```sql
SELECT
    c.consumed_on,
    c.name AS coupon,
    c.booklet,
    b.customer,
    c.consumed_by_delivery_man AS delivery_man,
    c.consumption_entry
FROM `tabPurisol Coupon` c
JOIN `tabPurisol Coupon Booklet` b ON b.name = c.booklet
JOIN `tabPurisol Coupon Consumption Entry` cce ON cce.name = c.consumption_entry
WHERE c.status = 'Consumed'
  AND cce.docstatus = 1
  AND (%(from_date)s IS NULL OR DATE(c.consumed_on) >= %(from_date)s)
  AND (%(to_date)s IS NULL OR DATE(c.consumed_on) <= %(to_date)s)
  AND (%(delivery_man)s IS NULL OR c.consumed_by_delivery_man = %(delivery_man)s)
  AND (%(customer)s IS NULL OR b.customer = %(customer)s)
  AND (%(booklet)s IS NULL OR c.booklet = %(booklet)s)
ORDER BY c.consumed_on DESC, c.name
```

**Acceptance reference**: spec US1 acceptance scenario 4.

---

## Bundle 2 — Financial & Oversight Reports (P2)

### R5. Delivery Man Discrepancies

**Type**: Query Report
**Roles**: `Purisol Administrator`
**Module**: `Cx Purisol`

**Filters**:
| Fieldname | Type | Required | Notes |
|-----------|------|----------|-------|
| `from_date` | Date | No | matches `DATE(d.opened_on) >=` |
| `to_date` | Date | No | matches `DATE(d.opened_on) <=` |
| `delivery_man` | Link → Employee | No | matches the delivery_man on `d.triggering_consumption_entry` |
| `status` | Select (`Open`, `Under Review`, `Resolved - Admin Error`, `Resolved - Delivery Man Liable`, `Resolved - Paid`) | No | matches `d.status =` |

**Columns**:
| Fieldname | Label | Type | Notes |
|-----------|-------|------|-------|
| `discrepancy` | Discrepancy ID | Link → Purisol Coupon Discrepancy | `d.name` |
| `opened_on` | Opened On | Datetime | `d.opened_on` |
| `discrepancy_type` | Type | Data | `d.discrepancy_type` |
| `booklet` | Booklet | Link → Purisol Coupon Booklet | `d.booklet` |
| `coupons_count` | Coupons | Int | `COUNT(*) FROM tabPurisol Coupon Discrepancy Coupon WHERE parent = d.name` |
| `estimated_amount` | Amount | Currency | `d.estimated_amount` |
| `status` | Status | Data | `d.status` |
| `resolution_action` | Resolution | Data | `d.resolution_action` |
| `delivery_man` | Delivery Man | Link → Employee | from `cce.delivery_man` (the triggering consumption entry's delivery man) |

**SQL skeleton**:
```sql
SELECT
    d.name AS discrepancy,
    d.opened_on,
    d.discrepancy_type,
    d.booklet,
    (SELECT COUNT(*) FROM `tabPurisol Coupon Discrepancy Coupon` dc WHERE dc.parent = d.name) AS coupons_count,
    d.estimated_amount,
    d.status,
    d.resolution_action,
    cce.delivery_man
FROM `tabPurisol Coupon Discrepancy` d
LEFT JOIN `tabPurisol Coupon Consumption Entry` cce ON cce.name = d.triggering_consumption_entry
WHERE d.docstatus = 1
  AND (cce.name IS NULL OR cce.docstatus = 1)
  AND (%(from_date)s IS NULL OR DATE(d.opened_on) >= %(from_date)s)
  AND (%(to_date)s IS NULL OR DATE(d.opened_on) <= %(to_date)s)
  AND (%(delivery_man)s IS NULL OR cce.delivery_man = %(delivery_man)s)
  AND (%(status)s IS NULL OR %(status)s = '' OR d.status = %(status)s)
ORDER BY d.opened_on DESC
```

**Acceptance reference**: spec US2 acceptance scenario 1.

---

### R6. Delivery Man Liability Balance

**Type**: Script Report
**Roles**: `Purisol Administrator`
**Module**: `Cx Purisol`

**Filters**:
| Fieldname | Type | Required | Notes |
|-----------|------|----------|-------|
| `delivery_man` | Link → Employee | No | optional party filter |

**Columns**:
| Fieldname | Label | Type | Notes |
|-----------|-------|------|-------|
| `delivery_man` | Delivery Man | Link → Employee | the GL `party` |
| `delivery_man_name` | Name | Data | from `Employee.employee_name` (lookup) |
| `total_owed` | Total Owed | Currency | `SUM(debit_in_account_currency)` |
| `total_paid` | Total Paid | Currency | `SUM(credit_in_account_currency)` |
| `open_balance` | Open Balance | Currency | `total_owed - total_paid` |

**Aggregation logic** (Python in `execute(filters)`):
1. `settings = frappe.get_doc("Purisol Settings")`. If `settings.employee_liability_account` is unset, return one row whose `delivery_man_name` is `_("Configure employee_liability_account in Purisol Settings to enable this report")` and whose numeric columns are `null`.
2. SQL: `SELECT party AS delivery_man, SUM(debit_in_account_currency) AS owed, SUM(credit_in_account_currency) AS paid FROM \`tabGL Entry\` WHERE account = %(account)s AND party_type = 'Employee' AND is_cancelled = 0 AND (%(delivery_man)s IS NULL OR party = %(delivery_man)s) GROUP BY party HAVING owed > 0 OR paid > 0 ORDER BY (owed - paid) DESC`.
3. For each row, look up `delivery_man_name` via `frappe.db.get_value("Employee", row.delivery_man, "employee_name")` (or fallback to the party name itself).
4. Compute `open_balance = owed - paid` and return.

**Notes**:
- Sourcing exclusively from `tabGL Entry` (not from discrepancy records) guarantees SC-003 reconciliation.
- The `is_cancelled = 0` filter is the GL's own cancellation marker (separate from `docstatus`).
- The `HAVING owed > 0 OR paid > 0` clause excludes parties whose GL net is exactly zero — they have nothing to report.

**Acceptance reference**: spec US2 acceptance scenario 2.

---

### R7. Booklet Sales Report

**Type**: Query Report
**Roles**: `Purisol Administrator`
**Module**: `Cx Purisol`

**Filters**:
| Fieldname | Type | Required | Notes |
|-----------|------|----------|-------|
| `from_date` | Date | No | matches `si.posting_date >=` |
| `to_date` | Date | No | matches `si.posting_date <=` |
| `customer` | Link → Customer | No | matches `si.customer =` |
| `price_list` | Link → Price List | No | matches `si.selling_price_list =` (the actual price list recorded on the invoice) |

**Columns**:
| Fieldname | Label | Type | Notes |
|-----------|-------|------|-------|
| `posting_date` | Sale Date | Date | `si.posting_date` |
| `booklet` | Booklet | Link → Purisol Coupon Booklet | `sii.purisol_booklet` |
| `customer` | Customer | Link → Customer | `si.customer` |
| `sales_invoice` | Invoice | Link → Sales Invoice | `si.name` |
| `amount` | Amount | Currency | `sii.amount` |
| `status` | Invoice Status | Data | `si.status` |

**SQL skeleton**:
```sql
SELECT
    si.posting_date,
    sii.purisol_booklet AS booklet,
    si.customer,
    si.name AS sales_invoice,
    sii.amount,
    si.status
FROM `tabSales Invoice Item` sii
JOIN `tabSales Invoice` si ON si.name = sii.parent
WHERE si.docstatus = 1
  AND sii.purisol_booklet IS NOT NULL
  AND (%(from_date)s IS NULL OR si.posting_date >= %(from_date)s)
  AND (%(to_date)s IS NULL OR si.posting_date <= %(to_date)s)
  AND (%(customer)s IS NULL OR si.customer = %(customer)s)
  AND (%(price_list)s IS NULL OR %(price_list)s = '' OR si.selling_price_list = %(price_list)s)
ORDER BY si.posting_date DESC, si.name, sii.idx
```

**Acceptance reference**: spec US2 acceptance scenario 3.

---

### R8. Discrepancy Rate by Delivery Man

**Type**: Script Report
**Roles**: `Purisol Administrator`
**Module**: `Cx Purisol`

**Filters**:
| Fieldname | Type | Required | Notes |
|-----------|------|----------|-------|
| `from_date` | Date | No | matches `cce.posting_date >=` |
| `to_date` | Date | No | matches `cce.posting_date <=` |

**Columns**:
| Fieldname | Label | Type | Notes |
|-----------|-------|------|-------|
| `delivery_man` | Delivery Man | Link → Employee | |
| `coupons_submitted` | Coupons Submitted | Int | `COUNT(*)` from Consumption Item |
| `discrepancies_count` | Discrepancies | Int | `COUNT(*)` from Discrepancy via triggering entry |
| `discrepancy_rate` | Rate (%) | Percent | `100 * discrepancies_count / coupons_submitted` (rounded to 2 dp) or `0` if denominator is 0 |
| `discrepancy_total` | Discrepancy Total | Currency | `SUM(estimated_amount)` |

**Aggregation logic** (Python in `execute(filters)`):
1. SQL `coupons`: `SELECT cce.delivery_man, COUNT(*) AS n FROM tabPurisol Coupon Consumption Item ci JOIN tabPurisol Coupon Consumption Entry cce ON cce.name = ci.parent WHERE cce.docstatus = 1 AND <date-range> GROUP BY cce.delivery_man`.
2. SQL `discrepancies`: `SELECT cce.delivery_man, COUNT(*) AS n, COALESCE(SUM(d.estimated_amount), 0) AS total FROM tabPurisol Coupon Discrepancy d JOIN tabPurisol Coupon Consumption Entry cce ON cce.name = d.triggering_consumption_entry WHERE d.docstatus = 1 AND cce.docstatus = 1 AND <date-range on cce.posting_date> GROUP BY cce.delivery_man`.
3. Python merge over the union of delivery_man keys present in `coupons` (a delivery man with zero entries in range is omitted; a delivery man with entries but zero discrepancies appears with rate 0%).
4. For each row: `rate = round(100 * d_count / c_count, 2) if c_count else 0`.
5. Order: rate DESC, then coupons_submitted DESC.

**Acceptance reference**: spec US2 acceptance scenario 4.

---

## Bundle 3 — Analytical Reports (P3)

### R9. Customer Consumption Rate

**Type**: Query Report
**Roles**: `Purisol Administrator`
**Module**: `Cx Purisol`

**Filters**: none.

**Columns**:
| Fieldname | Label | Type | Notes |
|-----------|-------|------|-------|
| `customer` | Customer | Link → Customer | grouping key |
| `booklets_depleted` | Booklets Depleted | Int | count of qualifying rows |
| `avg_days_to_deplete` | Avg Days to Deplete | Float | `AVG(DATEDIFF(b.depleted_on, b.sold_on))`, rounded to 1 dp |

**SQL skeleton**:
```sql
SELECT
    b.customer,
    COUNT(*) AS booklets_depleted,
    ROUND(AVG(DATEDIFF(b.depleted_on, b.sold_on)), 1) AS avg_days_to_deplete
FROM `tabPurisol Coupon Booklet` b
WHERE b.status = 'Depleted'
  AND b.depleted_on IS NOT NULL
  AND b.sold_on IS NOT NULL
  AND b.customer IS NOT NULL
GROUP BY b.customer
ORDER BY avg_days_to_deplete ASC
```

**Notes**:
- Customers with no Depleted booklets are omitted (the `WHERE` produces no rows for them).
- Ordering by `avg_days_to_deplete ASC` surfaces fastest-consuming customers first (most likely to need their next booklet soon).

**Acceptance reference**: spec US3 acceptance scenario 1.

---

### R10. Booklet Lifecycle Duration

**Type**: Script Report
**Roles**: `Purisol Administrator`
**Module**: `Cx Purisol`

**Filters**: none.

**Columns** (single row of three averages):
| Fieldname | Label | Type | Notes |
|-----------|-------|------|-------|
| `avg_generation_to_first_sale` | Avg Days: Generation → Sale | Float | `AVG(DATEDIFF(sold_on, creation))` over `Sold` or `Depleted` booklets with `sold_on IS NOT NULL` |
| `avg_sale_to_depletion` | Avg Days: Sale → Depletion | Float | `AVG(DATEDIFF(depleted_on, sold_on))` over `Depleted` booklets |
| `avg_full_lifetime` | Avg Days: Generation → Depletion | Float | `AVG(DATEDIFF(depleted_on, creation))` over `Depleted` booklets |

**Aggregation logic** (Python in `execute(filters)`):
1. Single SQL with three `AVG(CASE WHEN <condition> THEN DATEDIFF(...) END)` columns over a single scan of `tabPurisol Coupon Booklet`.
2. Result is one dict; convert to single-row report.
3. If a numerator subset is empty (e.g. no Depleted booklets yet), the `AVG` returns `null`; pass through to the report viewer (renders as empty cell — research.md §6).

**SQL skeleton**:
```sql
SELECT
    ROUND(AVG(CASE WHEN b.status IN ('Sold', 'Depleted') AND b.sold_on IS NOT NULL THEN DATEDIFF(b.sold_on, b.creation) END), 1) AS avg_generation_to_first_sale,
    ROUND(AVG(CASE WHEN b.status = 'Depleted' THEN DATEDIFF(b.depleted_on, b.sold_on) END), 1) AS avg_sale_to_depletion,
    ROUND(AVG(CASE WHEN b.status = 'Depleted' THEN DATEDIFF(b.depleted_on, b.creation) END), 1) AS avg_full_lifetime
FROM `tabPurisol Coupon Booklet` b
```

**Acceptance reference**: spec US3 acceptance scenario 2.

---

## Cross-Cutting Contracts

### Permissions (FR-004)

Every Phase-7 report's JSON contains exactly:
```json
"roles": [
    {"role": "Purisol Administrator"}
]
```
Frappe gates both menu visibility and direct URL access via this list. A user without the role sees no Phase-7 report in the menu and gets a permission error on direct URL access.

### Cancelled documents (FR-005, SC-005)

Every join on a submittable DocType includes `<alias>.docstatus = 1`. Cancelled records (`docstatus = 2`) and drafts (`docstatus = 0`) are excluded from every Phase-7 row, count, total, and rate.

### Click-through (FR-006)

Every column whose `fieldtype` is `Link` is automatically rendered as a clickable hyperlink by the standard Frappe report viewer. No per-report JS is shipped.

### Excel/PDF export (FR-003, SC-006)

Provided by the standard Frappe report viewer (Menu → Print / Download as PDF / Download as Excel). Phase 7 does not implement export.

### Live data (FR-041)

Every report runs its query against the operational database on each open/refresh. No caching, no materialised views, no `prepared_report` flag.

### Localisation (FR — implicit from constitution IX)

Column and filter labels are stored in English in the report JSONs; Frappe's `_()` machinery translates them at render time. Script Report Python wraps every fixed user-facing string in `frappe._()`. Arabic translations land in `cx_purisol/translations/ar.csv`.

### Menu group (FR-001)

Every Phase-7 report's `module = "Cx Purisol"`. The standard Reports menu groups them under "Cx Purisol" — same group as the existing Phase-2 `Current Custody by Delivery Man` report.
