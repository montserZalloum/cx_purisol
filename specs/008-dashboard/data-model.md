# Phase 1 Data Model — Dashboard

**Feature**: 008-dashboard | **Date**: 2026-04-19

Phase 8 introduces **zero new persistent domain entities**. Every widget is a read-only projection over data already established in Phases 1–7. The "new records" Phase 8 creates are framework-owned configuration records (Number Card, Dashboard Chart, Quick List fixtures; the extended Workspace; one Query Report) — not business-domain entities. This document catalogues the source tables each widget consumes, the framework-owned records Phase 8 adds, and the implicit invariants the widgets rely on.

---

## Source Entities (no new domain tables)

All entities below already exist. Phase 8 only reads them — never mutates.

### `Purisol Coupon Booklet` (Phase 1)

| Field | Type | Used by |
|-------|------|---------|
| `name` | autoname `WP-#####` | widget 8 (Quick List row identifier), widget 2b / chart sources (visible row) |
| `status` | Select (`In Stock`, `In Custody`, `Sold`, `Depleted`) | widgets 1, 2a, 2b, 3, 8 — each filters on this value |
| `customer` | Link → Customer | widget 4 (via new `customers_low_on_coupons` report), widget 8 (displayed column) |
| `current_delivery_man` | Link → Employee | widget 2b (Group By grouping key) |
| `depleted_on` | Datetime | widget 8 (relative-date filter `[Today - 7d]` and sort key) |
| `remaining_count` | Int | widget 4 (via new report's `SUM(remaining_count)` aggregate) |
| `sold_on` | Datetime | not directly read by Phase 8 widgets (widget 4's aggregate sums `remaining_count`, not days-since-sale) |
| `consumed_count`, `total_coupons` | Int | not read by Phase 8 widgets |

### `Purisol Coupon Discrepancy` (Phase 5) — submittable

| Field | Type | Used by |
|-------|------|---------|
| `name` | autoname `PCD-YYYY-#####` | widget 5b (Quick List row identifier) |
| `status` | Select (`Open`, `Under Review`, `Resolved - *`) | widgets 5a (count filter), 5b (list filter) |
| `opened_on` | Datetime | implicitly ordered via `modified` on Open-status records (research §6) |
| `modified` | Datetime (Frappe-built-in) | widget 5b's default `modified desc` sort — on Open-status records, equals `opened_on` |
| `booklet`, `discrepancy_type` | displayed on the Quick List row card | widget 5b |
| `docstatus` | Int (1 = submitted) | implicit filter on widgets 5a and 5b — `docstatus = 1` excludes drafts and cancelled records |

### `Purisol Coupon Consumption Item` (Phase 4) — child table of Consumption Entry

| Field | Type | Used by |
|-------|------|---------|
| — | — | Not directly read by Phase 8 widgets. The Phase-7 `Daily Delivery Man Summary` report reads this table and widget 7 reuses that report. |

### `Purisol Coupon Consumption Entry` (Phase 4) — submittable

| Field | Type | Used by |
|-------|------|---------|
| `posting_date`, `delivery_man`, `docstatus` | various | indirectly via Phase-7 `Daily Delivery Man Summary` (widget 7) |

### `GL Entry` (ERPNext)

| Field | Type | Used by |
|-------|------|---------|
| `account`, `party_type`, `party`, `debit_in_account_currency`, `credit_in_account_currency`, `is_cancelled` | various | indirectly via Phase-7 `Delivery Man Liability Balance` (widget 6) |

### `Purisol Settings` (Phase 1) — singleton

| Field | Type | Used by |
|-------|------|---------|
| `customer_low_stock_threshold` | Int | widget 4's new `customers_low_on_coupons` report reads this via a correlated subquery: `HAVING total_remaining <= (SELECT value FROM tabSingles WHERE doctype = 'Purisol Settings' AND field = 'customer_low_stock_threshold')` |
| `employee_liability_account` | Link → Account | indirectly via Phase-7 `Delivery Man Liability Balance` (widget 6) |

### Reference / Lookup tables

- **`Employee`** — appears as group-key on widget 2b (chart), as column on widget 6 (via Phase-7 report), as category on widget 7 (via Phase-7 report). Phase 8 reads `name` and `employee_name` (for display).
- **`Customer`** — appears as column on widget 4 (via new report) and widget 8. Phase 8 reads `name` and `customer_name`.

---

## New Records Phase 8 Creates (framework-owned, not domain)

Phase 8 introduces **zero new custom DocTypes** and **zero new fields** on any existing DocType. The records below are all Frappe-framework-owned configuration (Workspace, Number Card, Dashboard Chart, Report) — not new business entities.

### Workspace (existing — extended in place)

Record name: `مياه نبع النعيم` (Arabic — unchanged from Phase 0).

**Fields modified by Phase 8**:
| Field | Change |
|-------|--------|
| `roles` | `[]` → `[{"role": "Purisol Administrator"}]` (gates visibility per FR-003) |
| `number_cards` | `[]` → array of 4 entries, each `{"number_card_name": "Purisol — <Widget>"}` |
| `charts` | `[]` → array of 4 entries, each `{"chart_name": "Purisol — <Widget>"}` |
| `quick_lists` | `[]` → array of 2 inline child-table entries (widgets 5b and 8 — Quick List is a child table of Workspace, not a standalone record) |
| `shortcuts` | may remain `[]` or gain one entry for "Generate Booklets" if the Administrator wants quick access (optional; contracts/dashboard.md decides) |
| `content` | `[{"type":"header","data":{"text":"مياه نبع النعيم"}}]` → restructured three-bundle layout (contracts/dashboard.md §Workspace Content) |
| `icon`, `indicator_color` | unchanged or minor brand tweak; `indicator_color` stays `green` |

**Fields NOT modified**:
- `name` (the Arabic unique identifier)
- `label`, `title`
- `public` (stays `1`)
- `for_user` (stays empty)
- `sequence_id` (stays `40.0`)

### Number Card (new — 4 records)

Standalone Frappe DocType `Number Card`. Fixture file: `cx_purisol/fixtures/number_card.json` (new).

Each record's shape:
```json
{
  "doctype": "Number Card",
  "name": "Purisol — <Widget>",
  "label": "<English widget label>",
  "document_type": "Purisol Coupon Booklet" | "Purisol Coupon Discrepancy",
  "is_public": 1,
  "type": "Document Type",
  "function": "Count",
  "filters_json": "[[\"status\",\"=\",\"<Status>\"]]",
  "color": null | "Red",
  "cache": 0
}
```

Four records:
1. `"Purisol — Booklets In Stock"` — widget 1.
2. `"Purisol — Booklets In Custody"` — widget 2a.
3. `"Purisol — Active Sold Booklets"` — widget 3.
4. `"Purisol — Open Discrepancies"` — widget 5a (adds `"color": "Red"`).

### Dashboard Chart (new — 4 records)

Standalone Frappe DocType `Dashboard Chart`. Fixture file: `cx_purisol/fixtures/dashboard_chart.json` (new).

Each record's shape varies by `chart_type`:
```json
{
  "doctype": "Dashboard Chart",
  "name": "Purisol — <Widget>",
  "chart_name": "<English widget label>",
  "is_public": 1,
  "type": "Bar",
  "chart_type": "Group By" | "Report",
  "document_type": "Purisol Coupon Booklet" | null,
  "group_by_based_on": "current_delivery_man" | null,
  "group_by_type": "Count" | null,
  "report_name": "Customers Low on Coupons" | "Delivery Man Liability Balance" | "Daily Delivery Man Summary" | null,
  "x_field": "<column>",
  "y_axis": [{"y_field": "<column>", "color": "..."}],
  "filters_json": "...",
  "dynamic_filters_json": null | "{\"from_date\":\"Today\",\"to_date\":\"Today\"}",
  "cache": 0
}
```

Four records:
1. `"Purisol — In-Custody Breakdown"` — widget 2b. Group By chart on `Purisol Coupon Booklet.current_delivery_man`, filtered to `status = 'In Custody'`.
2. `"Purisol — Customers Low on Coupons"` — widget 4. Report chart on the new `customers_low_on_coupons` report.
3. `"Purisol — Outstanding Liabilities"` — widget 6. Report chart on Phase-7 `Delivery Man Liability Balance`.
4. `"Purisol — Today's Consumption"` — widget 7. Report chart on Phase-7 `Daily Delivery Man Summary` with dynamic filter `{from_date: Today, to_date: Today}`.

### Quick List (new — 2 inline child-table entries on the workspace)

Quick List is NOT a standalone DocType in Frappe 15; it is a child table of Workspace. The two inline entries live inside `workspace.json` as part of the workspace record.

Entry shape:
```json
{
  "document_type": "Purisol Coupon Discrepancy" | "Purisol Coupon Booklet",
  "label": "<English label>",
  "filters_json": "[[\"status\",\"=\",\"Open\"]]" | "[[\"status\",\"=\",\"Depleted\"],[\"depleted_on\",\">=\",\"[Today - 7d]\"]]"
}
```

Two entries:
1. Open Discrepancies Top 5 — widget 5b.
2. Recent Depleted Booklets (7 days) — widget 8.

### Report (new — 1 Query Report)

Record name: `Customers Low on Coupons`. Standard Frappe Report DocType. Fixture not exported; instead the record ships as a per-report folder under `cx_purisol/cx_purisol/report/customers_low_on_coupons/` with `is_standard = "Yes"` — migrates via `bench migrate`'s report-sync (identical to Phase-7 reports).

Record shape (from the `.json` in the folder):
```json
{
  "doctype": "Report",
  "name": "Customers Low on Coupons",
  "ref_doctype": "Purisol Coupon Booklet",
  "is_standard": "Yes",
  "report_type": "Query Report",
  "module": "Cx Purisol",
  "roles": [{"role": "Purisol Administrator"}],
  "query": "SELECT b.customer, SUM(b.remaining_count) AS total_remaining FROM `tabPurisol Coupon Booklet` b WHERE b.status = 'Sold' AND b.customer IS NOT NULL GROUP BY b.customer HAVING total_remaining <= (SELECT value FROM `tabSingles` WHERE doctype = 'Purisol Settings' AND field = 'customer_low_stock_threshold') ORDER BY total_remaining ASC LIMIT 10",
  "columns": [...]
}
```

The threshold is read via a correlated subquery on the `tabSingles` table — Frappe's standard storage for Single DocType field values — so the live-read property (FR-042) is satisfied without any Python.

---

## Implicit Invariants the Widgets Rely On

These invariants are established and enforced by Phases 1–7. Phase 8 widgets do not enforce them; they read assuming they hold.

1. **`Purisol Coupon Booklet.status` is the source of truth for booklet state** — Phase 1 established this; widgets 1, 2a, 2b, 3, 8 filter on `status`. A booklet with inconsistent status (e.g. `Depleted` with `remaining_count > 0`) is a Phase-4 bug, not a Phase-8 one.

2. **`Purisol Coupon Booklet.current_delivery_man` is non-null iff `status = 'In Custody'`** — Phase 2 established this. Widget 2b filters to `status = 'In Custody'` so every row naturally has a non-null `current_delivery_man`.

3. **`Purisol Coupon Booklet.depleted_on` is set whenever `status = 'Depleted'`** — Phase 4 sets `depleted_on` when the 20th coupon is consumed. Widget 8's `depleted_on >= [Today - 7d]` filter relies on this. A booklet with `Depleted` status and `depleted_on IS NULL` (a Phase-4 bug) would be silently excluded from widget 8 — acceptable, and the defect would surface in Phase 4's tests, not Phase 8.

4. **`Purisol Coupon Booklet.remaining_count` is maintained on every consumption event** — Phase 4 recomputes this in the consumption entry's `on_submit`. Widget 4's aggregate reads `SUM(remaining_count) GROUP BY customer` and relies on this maintenance.

5. **`Purisol Coupon Discrepancy.status = 'Open'` is the canonical "needs attention" filter** — Phase 5 establishes the status transitions. Widget 5a counts and widget 5b lists records where `status = 'Open' AND docstatus = 1`. A "Draft" discrepancy (unlikely in practice because discrepancies are auto-created and auto-submitted) is excluded via the `docstatus = 1` filter.

6. **Phase-7 `Delivery Man Liability Balance` report produces rows with `(delivery_man, open_balance)`** — widget 6 reads this shape. If Phase 7 changes the report's column names, widget 6's chart `x_field` / `y_axis` must be updated to match — this is caught by the Phase-8 integration test that runs the widget's chart query and asserts row shape.

7. **Phase-7 `Daily Delivery Man Summary` report produces rows with `(posting_date, delivery_man, coupons_submitted, ...)` and accepts `from_date` and `to_date` filters** — widget 7 reads this shape with dynamic filters set to today. Same change-detection guard as item 6.

8. **`Purisol Settings.customer_low_stock_threshold` is always set to a non-negative integer** — Phase 1 guarantees this. Widget 4's report reads it via a correlated subquery; if the threshold were `NULL`, the `HAVING` clause would never match (SQL's three-valued logic) and widget 4 would be silently empty. This is a defensible fallback — "customer low-stock watchlist is empty because the threshold is unset" is more helpful than an exception.

9. **Submitted records (`docstatus = 1`) are the source of truth for submittable DocTypes** — uniform `docstatus = 1` filter on every submittable join (widgets 5a, 5b, 6, 7's underlying reports).

10. **`tabSingles`-stored `Purisol Settings` values are read fresh at each widget render** — no Python-side caching. An admin-edited threshold value takes effect on the next widget render (SC-007).

11. **The Phase-0 workspace `مياه نبع النعيم` exists as a singleton fixture with a stable name** — Phase 8 extends it rather than renaming it. Any rename would cascade to `default_workspace_sidebar.json` and any user's personal `home_settings`.

12. **The `Purisol Administrator` role exists as a Phase-0 fixture and is the sole MVP role** — Phase 8 references it in the workspace's `roles` array and in the new report's `roles` array.

---

## Per-Widget Source Mapping (one-line summary)

| Widget | Frappe primitive | Primary source |
|--------|------------------|----------------|
| 1. Booklets In Stock | Number Card | `tabPurisol Coupon Booklet` WHERE `status = 'In Stock'` |
| 2a. Booklets In Custody | Number Card | `tabPurisol Coupon Booklet` WHERE `status = 'In Custody'` |
| 2b. In-Custody Breakdown | Dashboard Chart (Group By) | same, grouped by `current_delivery_man` |
| 3. Active Sold Booklets | Number Card | `tabPurisol Coupon Booklet` WHERE `status = 'Sold'` |
| 4. Customers Low on Coupons | Dashboard Chart (Report) | new `Customers Low on Coupons` Query Report |
| 5a. Open Discrepancies count | Number Card (color=Red) | `tabPurisol Coupon Discrepancy` WHERE `status = 'Open'` AND `docstatus = 1` |
| 5b. Open Discrepancies list | Quick List | same, sorted `modified desc`, limited to 5 |
| 6. Outstanding Liabilities | Dashboard Chart (Report) | Phase-7 `Delivery Man Liability Balance` report |
| 7. Today's Consumption | Dashboard Chart (Report) | Phase-7 `Daily Delivery Man Summary` report with `from_date = to_date = Today` dynamic filter |
| 8. Recent Depleted Booklets | Quick List | `tabPurisol Coupon Booklet` WHERE `status = 'Depleted'` AND `depleted_on >= [Today - 7d]`, sorted `depleted_on desc` |

---

## What Phase 8 Does NOT Add

- **No new domain DocTypes** — zero `Purisol *` Frappe DocTypes are introduced.
- **No new fields on existing DocTypes** — every field a widget needs already exists.
- **No new fixtures for domain data** — only configuration fixtures (Workspace extension, Number Cards, Dashboard Charts) are added.
- **No new roles** — `Purisol Administrator` (Phase-0 fixture) is the sole gate.
- **No new client-side JavaScript** — the standard Frappe Workspace renderer renders every widget.
- **No new custom field on any DocType** — the Phase-3 `Sales Invoice Item-purisol_booklet` fixture is referenced only indirectly via the Phase-7 reports widgets 6 and 7 consume.
- **No new `doc_events` hook** — widgets are read-only; no DocType triggers any Phase-8 code.
- **No new `doctype_js` entry** — no per-DocType client script is added.
- **No new patches beyond a single no-op anchor** — `cx_purisol.patches.v0_8_0.add_dashboard_widgets` is a version marker; it does no schema work.
- **No changes to any Phase 1–7 DocType JSON** — widening, narrowing, or field-adding is out of scope.
- **No changes to the Phase-7 report files** — widget 6 and widget 7 reference Phase-7 reports by name only; the Phase-7 JSON / Python are untouched.
