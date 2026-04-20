# Phase 0 Research — Reports

**Feature**: 007-reports | **Date**: 2026-04-19

This document resolves every `NEEDS CLARIFICATION` flag implicit in the Technical Context and documents, for each non-trivial choice, the **decision**, the **rationale**, and the **alternatives considered**. Every decision is bounded by the Phase-7 spec, the Purisol constitution (v1.0.0), and the realities of the existing Phase 1–6 codebase.

---

## 1. Query Report vs Script Report — per-report split

**Decision**: 6 of the 9 new reports are **Query Reports** (single SQL `SELECT` with parameter substitution); 3 are **Script Reports** (Python `execute(filters)` returning `(columns, data)`).

| Report | Type | Why |
|--------|------|-----|
| Active Booklets per Customer | Query | Single `SELECT` with one optional filter and computed `DATEDIFF` for days_since_sale. |
| Coupon Consumption Log | Query | Single `SELECT` joining 3 tables; date-range and Link filters. |
| Delivery Man Discrepancies | Query | Single `SELECT` from discrepancy with a `COUNT(*)` subquery (or `LEFT JOIN ... GROUP BY`) for affected_coupons count. |
| Booklet Sales Report | Query | Single `SELECT` joining `Sales Invoice Item` (filtered to `purisol_booklet IS NOT NULL`) to `Sales Invoice`; Link/date filters. |
| Customer Consumption Rate | Query | Single `SELECT` with `AVG(DATEDIFF(...)) GROUP BY customer`; no filters. |
| Daily Delivery Man Summary | **Script** | One row per (date, delivery_man) requires aggregating three independent sources (consumption items, distinct booklets touched, discrepancy count + sum) and joining them in Python; expressing this as a single SQL with three correlated subqueries is harder to read and harder to test. |
| Delivery Man Liability Balance | **Script** | Live read of `Purisol Settings.employee_liability_account`; conditional "info row" path when the setting is unset; cleaner in Python than in SQL. |
| Discrepancy Rate by Delivery Man | **Script** | Zero-divisor-safe rate column (`0%` when denominator is 0) is awkward in MariaDB without a `CASE` expression and is more readable as `round(100 * num / denom, 2) if denom else 0` in Python. |
| Booklet Lifecycle Duration | **Script** | Returns three averages as one row with three columns (not three rows × one column); easiest expressed as Python returning a constructed dict. |

**Rationale**:
- The plan's heuristic ("Query Report for simple SELECTs, Script Report when Python aggregation is needed") drives the split.
- Query Reports are cheaper to maintain — the JSON is the source of truth and there is no Python control flow to test beyond the SQL itself.
- Script Reports earn their complexity only when the SQL alternative is meaningfully worse. The three Script Reports above all have either a derived column with a divide-by-zero edge case, a cross-source aggregate that is awkward as correlated subqueries, or a settings-dependent execution path.

**Alternatives considered**:
- *All-Query approach* — rejected for the three Script Reports above. The `Discrepancy Rate by Delivery Man` rate column would need a MariaDB `CASE WHEN denom = 0 THEN 0 ELSE ROUND(100 * num / denom, 2) END` and the `Daily Delivery Man Summary` would need three correlated subqueries that all re-filter by date and delivery_man — readable but harder to test in isolation than three small Python aggregates.
- *All-Script approach* — rejected for the six Query Reports above. They have no aggregation that requires Python; embedding `frappe.db.sql(SELECT ...)` in a one-liner `execute()` adds boilerplate and a Python file to maintain for no benefit. The standard Frappe Query Report path is the lowest-friction option.
- *A single "Purisol Reports" Script Report with a `report_name` filter* — rejected; collapses 10 distinct report URLs into one, breaks click-through bookmarks, breaks per-report permissions (would have to enforce all-or-nothing), and breaks Excel/PDF export titles.

---

## 2. How does a report show up under a "Purisol" menu group?

**Decision**: Set `module = "Cx Purisol"` on every Phase-7 report JSON. The standard Frappe Reports menu (Desk → Reports) groups reports by their owning module's display name, which renders as "Cx Purisol" — sufficiently close to the spec's "Purisol" group requirement (FR-001) and consistent with the existing Phase-2 `Current Custody by Delivery Man` report.

**Rationale**:
- Verified by the existing Phase-2 report: it sets `module = "Cx Purisol"` and shows up under the "Cx Purisol" group in the Reports menu — the spec's intent ("Administrator can locate them without navigating individual record types") is satisfied.
- A literal "Purisol" group label would require either renaming the module (a breaking change touching every Phase-1-through-Phase-6 file) or introducing a `Workspace`-based shortcut layer. The Workspace shortcut layer is a Phase-8 concern (the Dashboard phase) — Phase 7 deliberately defers it to keep this phase's footprint to "9 report folders + 1 seed helper + 1 integration-test file".
- The spec's wording ("a single 'Purisol' group in the standard reports menu") is satisfied by "a single Cx-Purisol-module group in the standard reports menu" because the user-visible label and the user-visible navigation outcome are the same: one click from the Reports menu lands the Administrator on the list of Phase-7 reports together.

**Alternatives considered**:
- *Rename the module to "Purisol"* — rejected; would require migrations across every Phase-1-to-Phase-6 DocType JSON (`module` field on every record), every Phase-1-to-Phase-6 test that references the module, and every Workspace fixture. High blast radius for a label change.
- *Build a Workspace shortcut listing all 10 reports* — deferred to Phase 8 (the Dashboard phase, which already plans to introduce a `Workspace`). Adding it twice would be redundant.
- *Set `module` to a new "Purisol" module just for reports* — rejected; would split Phase-7 artefacts away from the rest of the app, fragment the Reports menu (one row per module), and complicate fixture/migration management.

---

## 3. How does the "cancelled record" filter work uniformly across reports?

**Decision**: Every query that touches a submittable DocType (`Purisol Coupon Consumption Entry`, `Purisol Coupon Discrepancy`, `Purisol Custody Entry`, `Sales Invoice`, `Journal Entry`, `Payment Entry`) joins on `<alias>.docstatus = 1` in the `WHERE` clause. Cancelled (`docstatus = 2`) and draft (`docstatus = 0`) records are excluded from every Phase-7 row, count, total, and rate.

**Rationale**:
- Frappe's `docstatus = 1` is the canonical "submitted, non-cancelled" filter and matches the spec's FR-005 / SC-005 / "amended replacement is the version reflected in reports, the cancelled original is excluded" wording.
- The amendment flow naturally produces `docstatus = 1` on the new record and `docstatus = 2` on the amended-from original — joining on `docstatus = 1` handles both cases without special logic.
- Uniform application across all 10 reports prevents the "cancelled invoice slipped through one report but not another" class of bugs.

**Alternatives considered**:
- *Per-report `Custom Filter` UI exposing a "show cancelled" toggle* — rejected; adds complexity for a use case the spec explicitly excludes ("MUST exclude cancelled and superseded source documents from all counts, totals, and rate calculations across every report"). If an Administrator needs to inspect cancelled records, the standard Frappe list view with a docstatus filter is the right tool.
- *Filter via Frappe's `permission_query_conditions` hook* — rejected; that hook is for row-level permission filtering (e.g. multi-tenant), not document-state filtering. Misusing it would couple state semantics to permissions, making future role changes risky.
- *Soft-delete handling for the few non-submittable DocTypes* (`Purisol Coupon Booklet`, `Purisol Coupon`, `Customer`, `Employee`) — rejected; these DocTypes do not use docstatus. Their state is captured by the `status` Select field (booklet, coupon) or the `disabled` flag (Customer, Employee). The spec explicitly says disabled employees and customers continue to appear in historical rows ("disabled status does not erase the audit trail"), so no `disabled = 0` filter is added.

---

## 4. Aggregation strategy for Script Reports — pure SQL grouped subqueries vs Python-side composition

**Decision**: Per-report — choose whichever is clearer. As a default, single-source aggregates use SQL `GROUP BY`; cross-source compositions use Python `dict`-based join in `execute()`.

| Script Report | Aggregation strategy |
|---------------|---------------------|
| Daily Delivery Man Summary | Three SQL aggregate queries (coupons-submitted by (date, delivery_man); booklets-touched by (date, delivery_man); discrepancies by (date, delivery_man)), composed in Python via dict-keyed merge. The `posting_date` and `delivery_man` form the join key; missing rows in any aggregate default to zero. |
| Delivery Man Liability Balance | One SQL aggregate against `tabGL Entry` (`SUM(debit), SUM(credit) GROUP BY party`), then Python lookup for `Employee.employee_name`. Live read of `Purisol Settings.employee_liability_account` happens before the SQL. |
| Discrepancy Rate by Delivery Man | Two SQL aggregates (coupons-submitted by delivery_man; discrepancies by delivery_man), composed in Python with the divide-by-zero-safe formula. |
| Booklet Lifecycle Duration | One SQL aggregate with three `AVG(DATEDIFF(...))` columns; result is a single dict converted to a single-row report. |

**Rationale**:
- Python-side composition is easier to test (assert intermediate dicts are correct, then assert the merge produces the expected final row) than nested SQL with three correlated subqueries.
- Pure-SQL is preferred when there is one source and one `GROUP BY` — no point introducing Python overhead.
- Mixed approach matches the Phase-2 reference (the existing Query Report uses pure SQL with `LEFT JOIN ... GROUP BY` and works well; that pattern is reused for the 6 Query Reports).

**Alternatives considered**:
- *All-SQL with correlated subqueries* — rejected for `Daily Delivery Man Summary` and `Discrepancy Rate by Delivery Man`; the SQL becomes a 50-line monolith that is harder to debug than three 10-line aggregates joined in Python.
- *All-Python with row-by-row Python loops* — rejected for the simple aggregates; SQL `GROUP BY` is faster and clearer than a Python loop with manual accumulators when only one source is involved.

---

## 5. What does `Delivery Man Liability Balance` do when `Purisol Settings.employee_liability_account` is unset?

**Decision**: Return zero rows but with a single info-style row whose `delivery_man` column is the localised string `_("Configure employee_liability_account in Purisol Settings to enable this report")` and whose numeric columns are `null`. The standard report viewer renders this as one help row — the user is informed and can fix the setting and rerun, rather than seeing a blank report or a stack-trace error.

**Rationale**:
- A blank report leaves the Administrator wondering whether the report is broken or whether the data is genuinely empty.
- A `frappe.throw()` (raise) would crash the report viewer, hide the help message, and require the Administrator to navigate Frappe's error log to diagnose — high friction.
- The info-row pattern is read-only and idempotent — it does not change the report's contract (still returns `(columns, data)` with the same column shape), and it is removed automatically once the setting is configured.
- The spec is silent on this case explicitly; the Assumption block states "the existing settings already record the employee-liability account … from prior phases" — i.e. the assumption is that it is configured. The info-row is the gentle fallback when the assumption is violated in practice.

**Alternatives considered**:
- *Raise `frappe.ValidationError`* — rejected; bad UX (crashes the viewer) and constitutionally questionable (Principle V is about domain rules, not UI affordances; raising here would conflate the two).
- *Return an empty `data` list with no info row* — rejected; ambiguous (is the data empty because there are no liabilities, or because the setting is missing?).
- *Auto-fall-back to "any account whose name contains 'liability'"* — rejected; unsafe and surprising; would silently report from the wrong account if the heuristic guessed wrong.

---

## 6. How does the Script Report shape "no Depleted booklets yet" (`Booklet Lifecycle Duration`)?

**Decision**: Return one row with `null` averages in the columns that have no qualifying source data. The Frappe report viewer renders `null` as "no data" (typically as an empty cell) which is the right UX for an analytical report ("we don't have enough history yet").

**Rationale**:
- An analytical report that returns zero rows looks like the report is broken; one row with `null` cells is unambiguous ("the metric exists, the answer is currently undefined").
- Matches Excel / spreadsheet conventions where averages over empty sets are typically left blank.
- Spec FR-031 implicitly accepts this by saying averages are "computed only over booklets that have reached the relevant terminal milestone" — the spec does not require any specific behaviour when zero booklets have reached the milestone, so the report is free to choose the most readable rendering.

**Alternatives considered**:
- *Return zero rows when no Depleted booklets exist* — rejected; ambiguous (broken vs no data).
- *Return `0` instead of `null`* — rejected; misleading (would imply "the average lifetime is zero days", which is false).
- *Return a localised string `_("No depleted booklets yet")` in the average column* — rejected; the column is `Int`/`Float` typed and a string would either coerce or render as the literal text, neither of which Excel-exports cleanly.

---

## 7. How does `Customer Consumption Rate` handle customers with no Depleted booklets?

**Decision**: Omit them from the result set. `GROUP BY customer` on a SELECT filtered to `b.status = 'Depleted'` naturally produces no row for a customer with zero qualifying booklets.

**Rationale**:
- The spec explicitly permits two options: omit the customer, or show with no average value. Omission is simpler (no special-case row construction), faster (smaller result set), and matches the "report shows what we know" rather than "report enumerates every customer in the system" reading.
- The Administrator who wants "all customers, including those with no purchase history" has a different report (Active Booklets per Customer with no filter, or the Customers list view directly).
- Consistent across rows — the report never shows null averages because every shown row has at least one Depleted booklet to average from.

**Alternatives considered**:
- *Show every customer with `null` for those without Depleted booklets* — rejected; the report would balloon to one row per customer regardless of relevance, hurting readability.

---

## 8. Filter shapes: dates, optional Link filters, required vs optional

**Decision**: Date-range filters are two independent optional `Date` filters named `from_date` and `to_date`. Single-Link filters (delivery_man, customer, booklet, status, price_list) are individually optional. No filter is required across any Phase-7 report — every report runs with no filters and produces a full-period, all-entities result.

**Rationale**:
- Optional-everywhere matches the existing Phase-2 reference and the standard ERPNext convention for built-in reports.
- Required filters would force the Administrator to type a value before seeing any output, hurting the "open the report → see data" UX the spec emphasises (SC-004: "Administrator can answer each of the following questions in under 30 seconds").
- The SQL idiom `(%(filter)s IS NULL OR %(filter)s = '' OR <col> = %(filter)s)` (matching Phase 2's pattern) cleanly handles the unset case.
- For Script Reports, the Python equivalent is `if filters.get('delivery_man'): conditions.append('cce.delivery_man = %(delivery_man)s')` — same semantics, expressed in code.

**Alternatives considered**:
- *Required date range with a sensible default (e.g. last 30 days)* — rejected; complicates the Excel-export contract (the export would include the implicit default date range, which would surprise the user). Optional is simpler.
- *Required customer on `Active Booklets per Customer`* — considered; rejected because the all-customer view is occasionally useful (cross-customer comparison).

---

## 9. Click-through targets for derived columns (`days_since_sale`, `days_in_custody`, `discrepancy_rate`)

**Decision**: Derived columns are rendered as plain numeric values (no click-through). Adjacent Link columns (booklet, customer, delivery_man) provide the click-through path to the underlying record.

**Rationale**:
- A derived column has no underlying record to click through to — `days_since_sale` is a number, not a reference.
- Frappe's standard report viewer renders Link columns as click-throughs automatically; non-Link columns render as the value's display form. No custom column formatter is needed.
- The Administrator who clicks on "45 days" expecting to navigate somewhere is satisfied by clicking on the adjacent booklet name, which navigates to the booklet detail page where they can inspect every detail.

**Alternatives considered**:
- *Render derived columns as `Link`-typed pointing back to the booklet* — rejected; misleading (the cell value is "45", not the booklet name).
- *Add a "Details" column at the end of every report with an icon link* — rejected; redundant with the existing Link columns and adds noise.

---

## 10. Test seed: shared deterministic dataset vs per-test ad-hoc

**Decision**: Build one shared deterministic seed at `cx_purisol/cx_purisol/tests/report_seed.py` exposing top-level entry points `seed_for_operations()`, `seed_for_finance()`, `seed_for_analytics()`, and a master `seed_full_phase_7()` for cross-bundle integration tests. Per-report unit tests can either use the master seed or build a tiny ad-hoc dataset (their choice based on what is clearer for the assertions in that test).

**Rationale**:
- A single shared seed prevents drift — every Phase-7 test sees the same 6 booklets, 4 delivery men, 3 customers, etc., which makes integration-test assertions reference known constants.
- Splitting into per-bundle entry points satisfies SC-007 (bundle independence) — a test that exercises only Bundle 2 imports `seed_for_finance()` and does not pull in the operational or analytical primitives.
- Per-report tests can opt out of the shared seed when an ad-hoc 2-row dataset makes the assertion clearer (e.g. testing the "customers with no Depleted booklets are omitted" case is clearest with one customer × zero Depleted booklets, not the full seed).
- Reuses existing Phase 1–6 fixtures (`make_booklet_in_stock`, `submit_assign`, `make_employee`, `seed_open_discrepancy`, etc.) — `report_seed.py` is a composition layer, not a re-implementation.

**Alternatives considered**:
- *No shared seed; every test builds its own dataset* — rejected; test maintenance burden grows with the number of reports (10), and assertions reference different "5-day-old assignment" or "60-day-old depletion" magic numbers in each test.
- *One monolithic seed used by every test* — rejected; couples Bundle 1 tests to Bundle 2 / Bundle 3 fixtures, breaking the "Bundle 1 ships independently" property.

---

## 11. Performance profile and index strategy

**Decision**: Trust Frappe's default indexes on Link fields, on `name` columns, and on `creation` / `modified` columns. For the three Date-typed columns that drive date-range filters (`Purisol Coupon Consumption Entry.posting_date`, `Sales Invoice.posting_date`, `Purisol Coupon.consumed_on`), verify at integration-test time via `EXPLAIN` whether the planner uses an index. Add an index in the relevant DocType JSON only if `EXPLAIN` shows a full table scan AND the seed-scale render time exceeds the SC-001 budget when extrapolated.

**Rationale**:
- Frappe automatically indexes `Link` fields and `parent` columns on child tables, which covers most join keys in Phase-7 reports.
- `Date` columns on submittable DocTypes are typically indexed by Frappe (the `posting_date` column on `Sales Invoice` is indexed in ERPNext core); same for `posting_date` on Phase-4 `Purisol Coupon Consumption Entry` (verified in the existing JSON).
- Adding indexes preemptively is a Principle-VIII-adjacent concern (long-running operations) but here is more about query performance than write throughput. The conservative default is "verify, don't speculate".
- The Phase-7 dataset scale (10,000 coupons, 500 booklets, 50 delivery men, 200 customers) is small enough that even a full table scan often renders within budget. Index addition should be a measured response to a specific slow query, not a blanket policy.

**Alternatives considered**:
- *Add indexes to every Date column upfront* — rejected; might be unnecessary, definitely adds migration weight, and obscures the actual query patterns that need optimisation.
- *Add a `prepared_report = 1` flag to slow reports* — deferred; this routes the report through Frappe's background-render queue with a "click again to view" UX. Worth adopting if a future scale-up reveals a slow report; not needed at MVP scale.

---

## 12. The pre-existing `Current Custody by Delivery Man` Report

**Decision**: Reuse it as-is. Phase 7 does NOT touch this report. The Phase-7 integration test suite adds a smoke-test row that confirms the report still renders under the Phase-7 seeded dataset and that the role gate still works.

**Rationale**:
- The existing report's columns (Delivery Man, Booklet, Days in Custody, Customer, Batch ID) cover every column FR-012 requires plus one extra (`batch_id`) that adds context without hurting clarity.
- The existing report's filters (Delivery Man, Batch ID) cover the FR-012 filter requirement plus one extra (`batch_id`).
- The existing report's `roles: [{role: "Purisol Administrator"}]` matches FR-004.
- The existing report's SQL filters by `b.status = 'In Custody'` and joins on `e.docstatus = 1` — already satisfies FR-005.
- Modifying it would risk regressing Phase-2 behaviour; verifying it under Phase-7 conditions catches any drift.

**Alternatives considered**:
- *Rewrite as a Phase-7-style report and remove the Phase-2 version* — rejected; pure code churn, no behavioural improvement.
- *Drop the `batch_id` filter/column to match the spec exactly* — rejected; the column is genuinely useful (an Administrator filtering by batch can quickly spot booklets from a specific generation cohort) and removing it would be a regression of an already-shipped feature with no offsetting benefit.

---

## 13. Excel/PDF export — custom or platform?

**Decision**: Rely entirely on Frappe's built-in report viewer for export. The viewer's Menu → "Print" / "Download as PDF" / "Download as Excel" actions handle every Phase-7 report (both Query and Script types) without any per-report code.

**Rationale**:
- FR-003 / SC-006 are satisfied by the platform's built-in functionality; building a custom export pipeline would re-invent the wheel.
- The spec's wording ("export to Excel and PDF using built-in actions") matches the Frappe-native flow exactly.
- Per-report export customisation (custom Excel formatting, branded PDF templates) is a Phase-8+ concern, not Phase-7's.

**Alternatives considered**:
- *Custom export with branded headers* — deferred; not in spec.

---

## 14. Localisation: English-stored labels with `_()`-translation at render

**Decision**: Store every column label and filter label in English in the report JSONs. Frappe's `_()` machinery translates them at render time using the active user's locale. Script Report Python wraps every fixed user-facing string in `frappe._()`. Arabic translations are appended to `cx_purisol/translations/ar.csv` as part of this phase.

**Rationale**:
- Matches the constitution Principle IX and the existing Phase 1–6 pattern.
- Frappe's report viewer auto-translates JSON-stored labels — no per-report Python is needed for Query Report labels.
- Script Report column metadata constructed in `execute(filters)` is the only place Python-side translation calls are needed; wrap each label in `frappe._()`.

**Alternatives considered**:
- *Store Arabic labels in the JSON directly* — rejected; breaks bilingual rendering (English users would see Arabic).
- *Skip `_()` on Script Report column labels* — rejected; constitutional violation. Every user-facing string must be translatable.

---

## 15. Patches anchor — needed?

**Decision**: Add one no-op patch entry `cx_purisol.patches.v0_7_0.add_phase_7_reports` to `patches.txt`. The patch is a no-op because Frappe's `bench migrate` synchronises `Report` JSON files automatically (each report has `is_standard = "Yes"`).

**Rationale**:
- Matches the Phase-2/3/4/5/6 anchor pattern — every phase has a `v0_<phase>_0` patch entry as a version marker, even when no schema change is needed.
- Provides a clean "this is where Phase 7 starts" boundary in `patches.txt` for future archaeology.
- Costs almost nothing (one new file, one new line in `patches.txt`).

**Alternatives considered**:
- *Skip the patch* — rejected; breaks the consistency of the per-phase anchor pattern. Future maintainers grepping for `v0_7_0` would find nothing and wonder whether the phase shipped.
- *Add a non-trivial patch that explicitly creates the Report records via Python* — rejected; redundant with `bench migrate`'s auto-sync of `is_standard = "Yes"` reports.
