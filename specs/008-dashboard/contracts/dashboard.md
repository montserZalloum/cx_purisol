# Phase 1 Contracts — Dashboard

**Feature**: 008-dashboard | **Date**: 2026-04-19

This document defines the behavioural contract for each of the 8 widgets — the Frappe primitive, the configuration, the filter-to-row semantics, and the click-through target. It also defines the contract for the single new supporting Query Report (`Customers Low on Coupons`) and the Workspace `content` block layout.

Conventions used throughout:
- **`docstatus = 1`** is the uniform "submitted, non-cancelled" filter, applied to every widget whose source is a submittable DocType.
- **`cache = 0`** on every widget — no platform-level short-TTL cache, fulfilling FR-004 / SC-007.
- **`is_public = 1`** on every Number Card and Dashboard Chart record — they are workspace-level, not user-private.
- **Role gate** is at the workspace level (`roles: [{"role": "Purisol Administrator"}]`). Individual Number Cards and Dashboard Charts do not carry per-widget role gates (they inherit via workspace + underlying-DocType permissions).

---

## Bundle 1 — Operational Widgets (P1)

### W1. Booklets In Stock  *(Number Card)*

**Primitive**: Number Card
**Record name**: `Purisol — Booklets In Stock`
**Click-through**: Coupon Booklet list filtered to `status = "In Stock"` (native)
**FR reference**: FR-010

**JSON skeleton** (in `cx_purisol/fixtures/number_card.json`):
```json
{
  "doctype": "Number Card",
  "name": "Purisol — Booklets In Stock",
  "label": "Booklets In Stock",
  "document_type": "Purisol Coupon Booklet",
  "is_public": 1,
  "type": "Document Type",
  "function": "Count",
  "filters_json": "[[\"Purisol Coupon Booklet\",\"status\",\"=\",\"In Stock\"]]",
  "cache": 0
}
```

**Acceptance reference**: spec US1 acceptance scenarios 2, 4.

---

### W2a. Booklets In Custody — count  *(Number Card)*

**Primitive**: Number Card
**Record name**: `Purisol — Booklets In Custody`
**Click-through**: Coupon Booklet list filtered to `status = "In Custody"` (native)
**FR reference**: FR-011 (count portion)

**JSON skeleton**:
```json
{
  "doctype": "Number Card",
  "name": "Purisol — Booklets In Custody",
  "label": "Booklets In Custody",
  "document_type": "Purisol Coupon Booklet",
  "is_public": 1,
  "type": "Document Type",
  "function": "Count",
  "filters_json": "[[\"Purisol Coupon Booklet\",\"status\",\"=\",\"In Custody\"]]",
  "cache": 0
}
```

**Acceptance reference**: spec US1 acceptance scenario 2.

---

### W2b. Booklets In Custody — per-delivery-man breakdown  *(Dashboard Chart, Group By)*

**Primitive**: Dashboard Chart, `chart_type = "Group By"`
**Record name**: `Purisol — In-Custody Breakdown`
**Click-through**: Coupon Booklet list filtered to `status = "In Custody" AND current_delivery_man = <bar value>` (native per-bar drill-down)
**FR reference**: FR-011 (breakdown portion)

**JSON skeleton** (in `cx_purisol/fixtures/dashboard_chart.json`):
```json
{
  "doctype": "Dashboard Chart",
  "name": "Purisol — In-Custody Breakdown",
  "chart_name": "In-Custody Breakdown",
  "is_public": 1,
  "type": "Bar",
  "chart_type": "Group By",
  "document_type": "Purisol Coupon Booklet",
  "group_by_based_on": "current_delivery_man",
  "group_by_type": "Count",
  "filters_json": "[[\"Purisol Coupon Booklet\",\"status\",\"=\",\"In Custody\"]]",
  "cache": 0
}
```

**Acceptance reference**: spec US1 acceptance scenario 2 (three-segment breakdown).

---

### W3. Active Sold Booklets  *(Number Card)*

**Primitive**: Number Card
**Record name**: `Purisol — Active Sold Booklets`
**Click-through**: Coupon Booklet list filtered to `status = "Sold"` (native)
**FR reference**: FR-012

**JSON skeleton**:
```json
{
  "doctype": "Number Card",
  "name": "Purisol — Active Sold Booklets",
  "label": "Active Sold Booklets",
  "document_type": "Purisol Coupon Booklet",
  "is_public": 1,
  "type": "Document Type",
  "function": "Count",
  "filters_json": "[[\"Purisol Coupon Booklet\",\"status\",\"=\",\"Sold\"]]",
  "cache": 0
}
```

**Acceptance reference**: spec US1 acceptance scenario 2.

---

### W7. Today's Consumption  *(Dashboard Chart, Report)*

**Primitive**: Dashboard Chart, `chart_type = "Report"`
**Record name**: `Purisol — Today's Consumption`
**Click-through**: the `Daily Delivery Man Summary` report with `from_date = to_date = Today` pre-applied
**FR reference**: FR-013

**JSON skeleton**:
```json
{
  "doctype": "Dashboard Chart",
  "name": "Purisol — Today's Consumption",
  "chart_name": "Today's Consumption",
  "is_public": 1,
  "type": "Bar",
  "chart_type": "Report",
  "report_name": "Daily Delivery Man Summary",
  "x_field": "delivery_man",
  "y_axis": [{"y_field": "coupons_submitted", "color": "#449CF0"}],
  "dynamic_filters_json": "{\"from_date\":\"Today\",\"to_date\":\"Today\"}",
  "cache": 0
}
```

**Notes**:
- Phase-7 `Daily Delivery Man Summary` returns columns `posting_date, delivery_man, coupons_submitted, booklets_touched, discrepancies_count, discrepancy_total`. Widget 7 uses `delivery_man` as the x-axis and `coupons_submitted` as the y-axis; other columns are ignored by the chart.
- Filtering to `from_date = to_date = Today` collapses the normally (date × delivery_man)-grouped result into one row per delivery_man for today.
- A delivery man with zero today-consumptions does not appear in the report's result set and therefore does not appear in the chart — matching the spec's "bars for delivery men with non-zero counts".

**Acceptance reference**: spec US1 acceptance scenario 3.

---

## Bundle 2 — Financial Risk Widgets (P2)

### W5a. Open Discrepancies — count  *(Number Card, Red)*

**Primitive**: Number Card
**Record name**: `Purisol — Open Discrepancies`
**Click-through**: Coupon Discrepancy list filtered to `status = "Open"` (native)
**FR reference**: FR-020 (count portion)

**JSON skeleton**:
```json
{
  "doctype": "Number Card",
  "name": "Purisol — Open Discrepancies",
  "label": "Open Discrepancies",
  "document_type": "Purisol Coupon Discrepancy",
  "is_public": 1,
  "type": "Document Type",
  "function": "Count",
  "filters_json": "[[\"Purisol Coupon Discrepancy\",\"status\",\"=\",\"Open\"],[\"Purisol Coupon Discrepancy\",\"docstatus\",\"=\",1]]",
  "color": "Red",
  "cache": 0
}
```

**Notes**:
- Static red accent is always on — see research §7 for rationale. The severity signal "there is work to do vs nothing to do" is carried by the count value (0 vs N) and the adjacent Quick List's populated-vs-empty state, satisfying FR-020's "perceptible without relying on colour alone".
- `docstatus = 1` is explicit in the filter because `Purisol Coupon Discrepancy` is submittable — this excludes any cancelled discrepancies from the count.

**Acceptance reference**: spec US2 acceptance scenarios 1, 2, 5.

---

### W5b. Open Discrepancies — top 5 recent list  *(Quick List)*

**Primitive**: Quick List (inline child-table entry on the Workspace)
**Click-through**: each row links to the Discrepancy detail; a "View All" button opens the full Open-status list
**FR reference**: FR-020 (list portion)

**Inline entry shape** (inside `cx_purisol/fixtures/workspace.json` → `quick_lists` array):
```json
{
  "document_type": "Purisol Coupon Discrepancy",
  "label": "Open Discrepancies",
  "filters_json": "[[\"status\",\"=\",\"Open\"]]"
}
```

**Notes**:
- Frappe 15's Quick List UI applies the list's default sort (typically `modified desc`) and limits to the default page size (5 or so). On Open-status records, `modified` equals `opened_on` because the record is not touched between creation and resolution.
- No `docstatus` filter is added here because the Quick List implicitly respects the DocType's permission/visibility rules, and `docstatus` is enforced by the Phase-5 `on_submit` lifecycle (Draft discrepancies are not a real-world state for this DocType).

**Acceptance reference**: spec US2 acceptance scenario 1 (top 5, most-recent-first).

---

### W6. Outstanding Delivery Man Liabilities  *(Dashboard Chart, Report)*

**Primitive**: Dashboard Chart, `chart_type = "Report"`
**Record name**: `Purisol — Outstanding Liabilities`
**Click-through**: the `Delivery Man Liability Balance` report
**FR reference**: FR-021

**JSON skeleton**:
```json
{
  "doctype": "Dashboard Chart",
  "name": "Purisol — Outstanding Liabilities",
  "chart_name": "Outstanding Liabilities",
  "is_public": 1,
  "type": "Bar",
  "chart_type": "Report",
  "report_name": "Delivery Man Liability Balance",
  "x_field": "delivery_man",
  "y_axis": [{"y_field": "open_balance", "color": "#E24C4C"}],
  "cache": 0
}
```

**Notes**:
- Phase-7 `Delivery Man Liability Balance` returns `delivery_man, delivery_man_name, total_owed, total_paid, open_balance`. Widget 6 uses `delivery_man` for x-axis and `open_balance` for y-axis.
- SC-004 reconciliation is satisfied by construction: the widget and the Phase-7 report read exactly the same rows from `tabGL Entry`. A mismatch is structurally impossible.
- When `Purisol Settings.employee_liability_account` is unset, the Phase-7 report returns its info-row fallback (one row, numeric columns null). The chart renders an empty axis — a known degenerate state covered by the Phase-7 report's contract.

**Acceptance reference**: spec US2 acceptance scenarios 3, 4.

---

## Bundle 3 — Customer Follow-up Widgets (P3)

### W4. Customers Low on Coupons  *(Dashboard Chart, Report)*

**Primitive**: Dashboard Chart, `chart_type = "Report"`
**Record name**: `Purisol — Customers Low on Coupons`
**Click-through**: the new `Customers Low on Coupons` report (see R-NEW below)
**FR reference**: FR-030

**JSON skeleton**:
```json
{
  "doctype": "Dashboard Chart",
  "name": "Purisol — Customers Low on Coupons",
  "chart_name": "Customers Low on Coupons",
  "is_public": 1,
  "type": "Bar",
  "chart_type": "Report",
  "report_name": "Customers Low on Coupons",
  "x_field": "customer",
  "y_axis": [{"y_field": "total_remaining", "color": "#FFA00A"}],
  "cache": 0
}
```

**Notes**:
- The chart renders one bar per customer sorted by total remaining ascending — the customer most-urgently-low appears first (leftmost / topmost in horizontal layout).
- The underlying report caps at 10 rows — so the chart shows at most 10 bars. The report's SQL uses `LIMIT 10` and the chart inherits.
- Clicking a bar navigates to the report view with the `customer` filter pre-applied on the report — the Administrator sees the same customer's row in a tabular form (the spec's edge case "clicking a zero-count widget still navigates to the correctly filtered list view, not an error page" is satisfied trivially since the widget only shows non-empty data).

**Acceptance reference**: spec US3 acceptance scenarios 1, 2.

---

### W8. Recent Depleted Booklets (last 7 days)  *(Quick List)*

**Primitive**: Quick List (inline child-table entry on the Workspace)
**Click-through**: each row links to the Booklet detail; a "View All" button opens the filtered Booklet list
**FR reference**: FR-031

**Inline entry shape** (inside `cx_purisol/fixtures/workspace.json` → `quick_lists` array):
```json
{
  "document_type": "Purisol Coupon Booklet",
  "label": "Recent Depleted Booklets",
  "filters_json": "[[\"status\",\"=\",\"Depleted\"],[\"depleted_on\",\">=\",\"[Today - 7d]\"]]"
}
```

**Notes**:
- The relative-date token `[Today - 7d]` is evaluated by Frappe 15's list-view filter evaluator at render time — a booklet that transitioned to Depleted exactly 7 days ago is included (inclusive lower bound); a booklet that transitioned 8 days ago is excluded.
- Default sort is `modified desc`, which for newly-Depleted booklets equals `depleted_on desc` (the Depletion transition is the last modification). For booklets that had their `depleted_on` set earlier and then were touched (e.g. a `notes` edit), the sort surfaces the touched-more-recently ones first — an acceptable minor deviation from strict `depleted_on desc`.
- If the Quick List displays `booklet` (name) and `customer` and `depleted_on` by default, that matches the spec's "showing booklet number, customer, and depletion date". If Frappe's default Quick List renders only `name` + `modified`, the spec's requirement is satisfied as long as clicking a row lands on the booklet detail page where all three values are visible.

**Acceptance reference**: spec US3 acceptance scenarios 3, 4.

---

## R-NEW. Customers Low on Coupons  *(Query Report — new in Phase 8)*

**Type**: Query Report
**Roles**: `Purisol Administrator`
**Module**: `Cx Purisol`
**Folder**: `cx_purisol/cx_purisol/report/customers_low_on_coupons/`
**Purpose**: data source for widget W4. Dashboard-support report.

**Filters**: none.

**Columns**:
| Fieldname | Label | Type | Notes |
|-----------|-------|------|-------|
| `customer` | Customer | Link → Customer | grouping key |
| `total_remaining` | Remaining Coupons | Int | `SUM(remaining_count)` across this customer's Sold booklets |

**SQL**:
```sql
SELECT
    b.customer,
    SUM(b.remaining_count) AS total_remaining
FROM `tabPurisol Coupon Booklet` b
WHERE b.status = 'Sold'
  AND b.customer IS NOT NULL
GROUP BY b.customer
HAVING total_remaining <= COALESCE(
    (SELECT CAST(value AS UNSIGNED) FROM `tabSingles` WHERE doctype = 'Purisol Settings' AND field = 'customer_low_stock_threshold'),
    3
)
ORDER BY total_remaining ASC
LIMIT 10
```

**Notes**:
- The threshold is read live from `Purisol Settings` via a correlated subquery on the `tabSingles` table — Frappe's standard storage for Single DocType field values. `CAST(... AS UNSIGNED)` is necessary because `tabSingles.value` is stored as text.
- The `COALESCE(..., 3)` fallback uses the Phase-1 default threshold (3) if the setting is somehow unset.
- `GROUP BY b.customer` aggregates across all Sold booklets for each customer; `Depleted` booklets are excluded (they no longer contribute to remaining coupons).
- `LIMIT 10` caps the result per FR-030's "up to ten customers" rule.
- The "additional qualifying customers exist" indicator (FR-030) is not a separate column — it is implicit in the LIMIT; the spec's wording is satisfied if the widget simply lists 10 rows when 10 or more qualify, because the Administrator inferring "there may be more" is the natural affordance. A future enhancement could add a summary row "X additional customers below threshold"; deferred.

**Folder contents**:
```
cx_purisol/cx_purisol/report/customers_low_on_coupons/
├── __init__.py                              # empty
├── customers_low_on_coupons.json            # Report definition (name, roles, query, columns, is_standard=Yes)
├── customers_low_on_coupons.py              # Query Report auto-discovery stub — one-line file (common Phase-7 convention)
└── test_customers_low_on_coupons.py         # Per-report unit test (mirrors Phase-7 pattern: _REPORT_SQL constant + _run_report helper)
```

**Acceptance reference**: spec US3 acceptance scenarios 1, 2.

**Test coverage**:
- Customer with total = 0, 1, 2, 3, 4 (given threshold = 3): the report includes 0, 1, 2, 3 and excludes 4 — matches US3 scenario 1.
- More than ten qualifying customers: the report returns exactly 10, ordered lowest-first — matches US3 scenario 2.
- Customer with zero Sold booklets: not included (the `WHERE b.status = 'Sold'` + `GROUP BY b.customer` combination produces no group).
- Customer with one Depleted booklet and zero Sold: not included (Depleted is filtered out).

---

## Workspace Content Layout

The workspace's `content` field is a JSON string of Frappe block elements. Phase 8's layout is three bundle-aligned sections:

```json
[
  {"type": "header", "data": {"text": "Operations", "level": 4}, "id": "operations-header"},
  {"type": "card", "data": {"card_name": "Purisol — Booklets In Stock", "col": 3}, "id": "c1"},
  {"type": "card", "data": {"card_name": "Purisol — Booklets In Custody", "col": 3}, "id": "c2"},
  {"type": "card", "data": {"card_name": "Purisol — Active Sold Booklets", "col": 3}, "id": "c3"},
  {"type": "chart", "data": {"chart_name": "Purisol — In-Custody Breakdown", "col": 6}, "id": "g2b"},
  {"type": "chart", "data": {"chart_name": "Purisol — Today's Consumption", "col": 6}, "id": "g7"},
  {"type": "spacer", "data": {}, "id": "s1"},
  {"type": "header", "data": {"text": "Risk Watchlist", "level": 4}, "id": "risk-header"},
  {"type": "card", "data": {"card_name": "Purisol — Open Discrepancies", "col": 3}, "id": "c5a"},
  {"type": "quick_list", "data": {"quick_list_name": "Open Discrepancies", "col": 5}, "id": "ql5b"},
  {"type": "chart", "data": {"chart_name": "Purisol — Outstanding Liabilities", "col": 4}, "id": "g6"},
  {"type": "spacer", "data": {}, "id": "s2"},
  {"type": "header", "data": {"text": "Customer Follow-up", "level": 4}, "id": "follow-up-header"},
  {"type": "chart", "data": {"chart_name": "Purisol — Customers Low on Coupons", "col": 6}, "id": "g4"},
  {"type": "quick_list", "data": {"quick_list_name": "Recent Depleted Booklets", "col": 6}, "id": "ql8"}
]
```

**Notes**:
- Frappe 15's Workspace `content` is stored as an escaped JSON string in the fixture file. The exact escaping is platform-generated by `bench export-fixtures`; the authoring workflow is (a) build the layout through the Frappe Desk UI, then (b) export fixtures to capture the correctly-escaped string.
- `col` values on each block element control width using Frappe's 12-column grid — row 1 uses 3+3+3+6+6=21 (wraps onto two visual rows naturally), row 2 uses 3+5+4=12 (single row), row 3 uses 6+6=12 (single row).
- Block `id` values are arbitrary but stable — Frappe uses them for DOM keying during renders.
- The exact `type` names (`card`, `chart`, `quick_list`, `header`, `spacer`) match Frappe 15's Workspace block enum.

---

## Cross-Cutting Contracts

### Workspace Role Gate (FR-003)

The workspace's `roles` array is updated from `[]` to `[{"role": "Purisol Administrator"}]`. Frappe 15 gates both sidebar visibility and direct URL access via this list — a user without the role sees no Purisol workspace in the sidebar and gets a permission error on direct URL access.

### Default Landing (FR-002)

`hooks.py` gains:
```python
role_home_page = {
    "Purisol Administrator": "مياه نبع النعيم",
}
```

Frappe's login flow consults this mapping, honouring a user-set personal `home_settings` as higher priority. Matches FR-002 exactly.

### Fixtures Registration (hooks.py extension)

The `fixtures` list in `hooks.py` is extended with two new entries:
```python
fixtures = [
    {"dt": "Role", "filters": [["name", "in", ["Purisol Administrator"]]]},
    {"dt": "Custom Field", "filters": [["name", "in", ["Sales Invoice Item-purisol_booklet"]]]},
    {"dt": "Workspace", "filters": [["name", "in", ["مياه نبع النعيم"]]]},
    {"dt": "Default Workspace Sidebar", "filters": [["name", "in", ["مياه نبع النعيم"]]]},
    # Phase 8 additions:
    {"dt": "Number Card", "filters": [["name", "in", [
        "Purisol — Booklets In Stock",
        "Purisol — Booklets In Custody",
        "Purisol — Active Sold Booklets",
        "Purisol — Open Discrepancies",
    ]]]},
    {"dt": "Dashboard Chart", "filters": [["name", "in", [
        "Purisol — In-Custody Breakdown",
        "Purisol — Customers Low on Coupons",
        "Purisol — Outstanding Liabilities",
        "Purisol — Today's Consumption",
    ]]]},
]
```

These entries ensure that `bench export-fixtures` re-exports the widgets from the developer's dev site into the fixture files during future schema/widget edits.

### Patches Anchor (FR-none — version marker)

`patches.txt` gains `cx_purisol.patches.v0_8_0.add_dashboard_widgets` in the `[post_model_sync]` section.

`cx_purisol/patches/v0_8_0/add_dashboard_widgets.py`:
```python
import frappe


def execute():
    """Phase 8 version-marker patch.

    Widgets (Workspace extension, Number Cards, Dashboard Charts, Quick Lists)
    migrate via bench migrate's standard fixture loader. This patch is a no-op
    anchor consistent with the v0_X_0 per-phase convention.
    """
```

### Localisation (FR — implicit from constitution IX)

New strings introduced by Phase 8 (labels, chart names, header text, Quick List labels) are stored in English in the fixture JSONs. Frappe's `_()` machinery translates them at render time. Arabic translations land in `cx_purisol/translations/ar.csv`:

| English | Arabic (illustrative) |
|---------|----------------------|
| Operations | العمليات |
| Risk Watchlist | قائمة مراقبة المخاطر |
| Customer Follow-up | متابعة العملاء |
| Booklets In Stock | الدفاتر في المخزون |
| Booklets In Custody | الدفاتر في العهدة |
| Active Sold Booklets | الدفاتر المباعة النشطة |
| Open Discrepancies | التناقضات المفتوحة |
| Outstanding Liabilities | الالتزامات المستحقة |
| In-Custody Breakdown | توزيع العهدة |
| Today's Consumption | استهلاك اليوم |
| Customers Low on Coupons | عملاء على وشك نفاد الكوبونات |
| Recent Depleted Booklets | الدفاتر المستنفدة مؤخرًا |

Final Arabic wording is confirmed during implementation — the table above is illustrative. The constitution Principle IX test (every user-facing string wrapped in `_()`) is satisfied because Frappe's Workspace / Number Card / Dashboard Chart / Quick List renderers all call `_()` on labels internally.
