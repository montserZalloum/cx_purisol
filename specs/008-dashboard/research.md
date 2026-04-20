# Phase 0 Research — Dashboard

**Feature**: 008-dashboard | **Date**: 2026-04-19

This document resolves every `NEEDS CLARIFICATION` flag implicit in the Technical Context and documents, for each non-trivial choice, the **decision**, the **rationale**, and the **alternatives considered**. Every decision is bounded by the Phase-8 spec, the Purisol constitution (v1.0.0), the realities of the existing Phase 0–7 codebase (the Phase-0 Arabic workspace `مياه نبع النعيم` is already a tracked fixture, and Phase 7 has shipped ten reports under `cx_purisol/cx_purisol/report/`), and Frappe 15's native Workspace widget model.

---

## 1. Extend the existing workspace vs. create a new "Purisol Dashboard" workspace

**Decision**: Extend the existing Phase-0 workspace `مياه نبع النعيم` in place. Its `name` field stays identical; its `charts`, `number_cards`, `quick_lists`, `content`, and `roles` arrays are populated as part of Phase 8.

**Rationale**:
- A rename would cascade: every user's personal sidebar bookmark, every `User.home_settings` entry that pins this workspace, any cross-fixture reference (`default_workspace_sidebar.json` already references the Arabic name), and any link target would need to be rewritten.
- The spec's wording ("a single Purisol dashboard view") is satisfied by "a single Purisol-branded workspace view" — the existing workspace is already the Purisol workspace; it just happens to be empty of widgets so far.
- Frappe 15 supports extending a workspace's widget arrays without any structural change — workspaces are designed to be grown over time.
- The existing Phase-0 workspace is `public: 1` with empty `roles: []`. Adding `roles: [{"role": "Purisol Administrator"}]` tightens visibility to admins only (FR-003) while keeping `public: 1`, which is the Frappe-idiomatic way to gate a public workspace to a role (a private workspace `public: 0` would additionally require a `for_user` owner — wrong semantics for a shared landing page).

**Alternatives considered**:
- *Rename workspace to "Purisol Dashboard"* — rejected; high blast radius for a label change, breaks existing bookmarks, requires cross-fixture updates.
- *Create a second workspace alongside `مياه نبع النعيم`* — rejected; two workspaces named "Purisol" (in different languages) would confuse users and require the `role_home_page` mapping to choose one. Simpler to have one.
- *Keep the workspace public and gate widgets individually by role* — rejected; widget-level role gating doesn't exist in Frappe's Number Card / Dashboard Chart model, and even if it did, non-admin users would still see the empty workspace shell. Workspace-level `roles` is the only fully-hiding mechanism.

---

## 2. Widget 4 (Customers Low on Coupons) — reuse Phase-7 report vs new tiny Report

**Decision**: Create a new tiny Query Report `customers_low_on_coupons` at `cx_purisol/cx_purisol/report/customers_low_on_coupons/`, following the Phase-7 per-report folder pattern. Widget 4 is a Dashboard Chart of `chart_type = "Report"` referencing this new report.

**Rationale**:
- Phase-7's `Active Booklets per Customer` lists booklets per customer without threshold filtering or per-customer aggregation — a single customer with three Sold booklets produces three rows, which is useless as a "customers low on coupons" signal.
- The spec (FR-030) requires *aggregated* totals per customer, filtered to those at or below the low-stock threshold, ordered ascending, capped at ten.
- Native Frappe primitives cannot deliver this aggregated view:
  - **Quick List** shows raw DocType records with a static filter — no cross-record aggregation.
  - **Dashboard Chart `chart_type = "Group By"`** on `Purisol Coupon Booklet` grouped by `customer` would show SUM of remaining across Sold booklets, but does not support a `HAVING total <= threshold` filter and does not support reading the threshold from Settings live.
  - **Dashboard Chart `chart_type = "Custom"`** with a Python callback could produce the aggregated data — but "Custom" charts are a less-documented escape hatch and do not offer native click-through to a filtered list view.
- A dedicated Query Report is the most Frappe-native path: 15 lines of SQL, tests naturally fit the Phase-7 pattern, click-through lands on the report (which is useful as a drill-down), and the threshold is read live from `Purisol Settings` via a correlated subquery.

**Alternatives considered**:
- *Dashboard Chart `chart_type = "Custom"` with Python callback that reuses Phase-6's `compute_customer_total_remaining` function* — rejected; Custom charts have awkward click-through semantics (they link to the chart's own detail page, not to a filtered list of customers), and a drill-down report is more useful for the Administrator.
- *Quick List on `Purisol Coupon Booklet` with `[["remaining_count","<=",3],["status","=","Sold"]]`* — rejected; this shows individual low-remaining booklets, not customers with aggregated low remaining. Semantically wrong per FR-030.
- *Wrap the Phase-6 `Purisol Notify` customer-low-stock detection function as a Script Report* — rejected; introduces a Python control-flow path for what is naturally one SQL query, and couples reporting to the notification module's side-effectful internals.
- *Leave Phase 8's widget 4 as a bare shortcut to `Active Booklets per Customer`* — rejected; the user-facing wording ("Customers Low on Coupons") does not match the linked report's contents, violating the spec's widget description.

**Note on report count**: Phase 7 delivers ten user-navigable reports under the `Cx Purisol` menu group. The `customers_low_on_coupons` Report added in Phase 8 is a *dashboard-support* report — a data source for a widget — and is technically discoverable in the reports menu. Whether to hide it from the reports menu (via a hypothetical future `show_in_menu = 0` attribute) is deferred; for MVP it appears in the menu, consistent with every other Frappe Report. This is a minor cosmetic concern, not a correctness one.

---

## 3. Number Card and Dashboard Chart record-naming convention

**Decision**: Record `name` field on Number Cards and Dashboard Charts uses the pattern `"Purisol — <Widget Name>"` (em-dash separator). Example: `"Purisol — Booklets In Stock"`, `"Purisol — Today's Consumption"`.

**Rationale**:
- Number Card and Dashboard Chart are Frappe-core DocTypes, not `Purisol ` domain DocTypes, so the constitutional Principle I prefix rule does not mandatorily apply to their records.
- However, a convention that makes Purisol-owned records distinguishable in the global Number Card / Dashboard Chart list views is useful for maintenance — an Administrator scrolling through `/app/number-card` can immediately see which cards are Purisol's.
- The em-dash separator (` — `) is visually distinctive and works in both LTR and RTL rendering (MDN's "em-dash" handling is bidi-safe; Frappe's list view renders it correctly in Arabic locale).
- The `"Purisol "` prefix (capital P, lowercase remainder, single trailing space) matches the constitutional Principle I convention even though it is not required here — this is a convenience consistency, not a mandate.

**Alternatives considered**:
- *No prefix; record names are just the widget label* — rejected; Purisol records would blend in with any future ERPNext dashboard records in the same DocType.
- *Uppercase `"PURISOL"` prefix* — rejected; inconsistent with the constitutional Title Case convention.
- *Colon separator (`"Purisol: Booklets In Stock"`)* — rejected; colons have special meaning in some Frappe URL paths, risking routing edge cases.

---

## 4. Dashboard Chart `chart_type = "Group By"` for widget 2b (In-Custody per delivery man)

**Decision**: Use Frappe 15's native Group By Dashboard Chart. JSON skeleton: `{"chart_type": "Group By", "document_type": "Purisol Coupon Booklet", "group_by_based_on": "current_delivery_man", "group_by_type": "Count", "filters_json": "[[\"Purisol Coupon Booklet\",\"status\",\"=\",\"In Custody\"]]", "type": "Bar"}`.

**Rationale**:
- Group By charts are the simplest primitive for "count the records of DocType X, grouped by field Y, filtered by Z". No supporting Report, no Python callback.
- Frappe 15's Group By chart produces one bar per distinct group value; clicking a bar opens the filtered list (`current_delivery_man = <value>` AND `status = "In Custody"`) — native click-through satisfies FR-005.
- `group_by_type = "Count"` counts rows per group (not sum of a column) — matches the spec's "count of booklets per delivery man".
- No `aggregate_function_based_on` is needed because Count does not aggregate over a field.

**Alternatives considered**:
- *Dashboard Chart `chart_type = "Custom"` with a Python callback* — rejected; needless complexity; Group By is the native fit.
- *Dashboard Chart `chart_type = "Report"` with a new tiny Script Report* — rejected; Group By does this without any Python.

---

## 5. Dashboard Chart `chart_type = "Report"` for widgets 4, 6, 7

**Decision**: Report-typed Dashboard Charts for the three widgets whose source is either a new dashboard-support report (widget 4) or a Phase-7 report (widgets 6, 7). Each widget's chart JSON sets `chart_type = "Report"`, `report_name = "<Report>"`, `x_field = "<grouping column>"`, `y_axis = [{"y_field": "<numeric column>", "color": "..."}]`, and (for widget 7) `dynamic_filters_json = {"from_date": "Today", "to_date": "Today"}`.

**Rationale**:
- Report charts let a Dashboard Chart reuse an existing Report's query without duplicating SQL. Widgets 6 and 7 are two reports that Phase 7 already built — widgets reuse them verbatim.
- `dynamic_filters_json` is resolved at render time against the current server clock — "today" on Monday means Monday, on Tuesday means Tuesday — no stale cache.
- `x_field` + `y_axis` together specify which Report columns feed the chart's visual axes. Report columns outside these two are ignored.
- Click-through on a Report chart navigates to the underlying report URL with the dynamic filters applied — the Administrator sees the tabular report view as the drill-down.

**Alternatives considered**:
- *One new Script Report per widget (three new reports)* — rejected; widgets 6 and 7 should reuse Phase-7 reports (that was the entire point of ordering the phases sequentially), and widget 4 only needs one new small Query Report.
- *Hardcode today's date in the fixture's `filters_json`* — rejected; the filter would be a fixed calendar date, stale after one day.

---

## 6. Quick List for widgets 5b and 8 — relative-date filter support

**Decision**: Frappe 15 Quick Lists support relative date tokens in their `filters_json`. Widget 8 uses `[["status","=","Depleted"],["depleted_on",">=","[Today - 7d]"]]`. Widget 5b uses `[["status","=","Open"]]` (no date token needed).

**Rationale**:
- Frappe 15's list-view filter evaluator (`frappe.desk.reportview`) accepts the `[Today ± Nd]` token form — documented in the Frappe 15 changelog under "Relative date filters in list views".
- If the token form is rejected in a future Frappe version or a non-standard deployment, the fallback is to switch widget 8 to a Dashboard Chart of `chart_type = "Report"` backed by a tiny new Query Report — same approach as widget 4. Integration testing catches any relative-date evaluation regression.
- Quick List's built-in sort (default `modified desc`) surfaces the most-recently-depleted booklets first for widget 8, and the most-recently-touched open discrepancies first for widget 5b (on Open-status records, `modified` equals `opened_on` because Open records are not edited between creation and resolution).

**Alternatives considered**:
- *Widget 8 as a Dashboard Chart of `chart_type = "Report"` with a new report* — deferred; preferred if the relative-date token fails in practice. Not adopted by default to keep the fixture count down.
- *Server-side cron that materializes a "recent depletions" table daily* — rejected; violates the read-only / zero-schema-change constraints of Phase 8.

**Test coverage**: the Phase-8 integration test explicitly calls `frappe.get_list("Purisol Coupon Booklet", filters=[["status","=","Depleted"],["depleted_on",">=","[Today - 7d]"]])` in a dedicated test method and asserts the result matches a hand-constructed expected set — catching any relative-date-token regression.

---

## 7. Open Discrepancies severity signal without conditional colour

**Decision**: Widget 5a's Number Card has a static `color = "Red"` attribute. The severity signal (count > 0 vs count = 0) is carried by (a) the displayed count value itself (0 vs N) and (b) the adjacent Quick List (widget 5b) being empty vs populated. The Red accent is always on.

**Rationale**:
- Frappe 15 Number Cards have a static `color` attribute (values: `Green`, `Red`, `Blue`, `Orange`, etc.) but no conditional/computed color.
- The spec (FR-020) mandates "a visual severity indicator that clearly distinguishes count > 0 (work to do) from count = 0 (healthy). The severity distinction MUST be perceptible without relying on colour alone." — the count value and the list state together satisfy this.
- Always-Red reads as "this is a risk widget; pay attention" even when the count is 0 — it is the correct long-term orientation for a risk widget (you always want the Administrator to glance at it every morning, not only when there is a problem).
- The spec's secondary "green if 0, red if > 0" dynamic-colour guidance in the PRD is aspirational — the spec itself retreats to "perceptible without relying on colour alone" as the enforceable criterion. The Phase-8 implementation satisfies the enforceable criterion without needing a custom widget.

**Alternatives considered**:
- *Ship a Custom Block (HTML) for widget 5 with conditional CSS* — rejected; introduces non-standard widget code, makes click-through routing manual, requires custom JavaScript, and violates Principle II (Leverage ERPNext Primitives).
- *Number Card with `color = "Green"` and rely on the count value alone* — rejected; a "0" on a green card reads "fine, nothing to see" which is misleading — a Red card on "0" reads "this is a watchlist; today it's empty, tomorrow check again".
- *A future Frappe conditional-colour feature (speculative)* — deferred; if Frappe adds conditional colour in a later version, this widget can adopt it without a spec change.

---

## 8. Default landing via `role_home_page` vs `Role.home_page` vs personal `home_settings`

**Decision**: Add `role_home_page = {"Purisol Administrator": "مياه نبع النعيم"}` to `cx_purisol/hooks.py`. Do not set `Role.home_page` in the `role.json` fixture.

**Rationale**:
- Frappe's login flow consults (in order): (1) user-specific `User.home_settings`, (2) `role_home_page` mapping from `hooks.py`, (3) `Role.home_page` from the Role record, (4) system default. Precedence yields the correct spec behaviour (user preference wins over role default, FR-002).
- `role_home_page` from hooks.py is the documented Frappe pattern for per-app default landing — it is read fresh on every login, so changing it doesn't require a migration.
- `Role.home_page` would work but sits on the role record. Since a user may have multiple roles, Frappe picks one via an internal priority rule — less predictable than `role_home_page` which explicitly lists the role.
- Setting `User.home_settings` would override on a per-user basis — wrong for a default.

**Alternatives considered**:
- *Set `Role.home_page = "مياه نبع النعيم"` in `cx_purisol/fixtures/role.json`* — rejected; per-role-single-value semantics is less clear than the per-hook explicit mapping.
- *Skip default landing; require users to navigate manually* — rejected; fails FR-002.

---

## 9. Disabled employees in widget 2b breakdown

**Decision**: The Group By chart on `current_delivery_man` does not pre-filter for `Employee.disabled = 0`. Disabled delivery men who still appear as `current_delivery_man` on `In Custody` booklets still show in the breakdown.

**Rationale**:
- The spec edge case explicitly requires this: "Disabled delivery man still holding a booklet — continues to attribute the booklet to that (disabled) delivery man so the audit picture is accurate".
- An audit-accurate dashboard reflects reality: if the data shows a disabled employee holding a booklet, the dashboard shows that. The disablement is a future-oriented flag, not a historical erasure.
- Native Group By charts don't support a joined pre-filter on `Employee.disabled` anyway — doing so would require a Custom chart.

**Alternatives considered**:
- *Custom chart with a pre-filter to active employees only* — rejected; violates the spec edge case.

---

## 10. Chart readability when many delivery men hold booklets (widget 2b)

**Decision**: Rely on Frappe's default chart rendering — Frappe Charts auto-rotates labels, truncates long labels, and does not have an automatic "top-N + Other" bucketing built in. If the number of distinct holders exceeds ~8 and the workspace renders poorly, Phase 8 accepts the readability trade-off and the Administrator can click through to the full list for clarity.

**Rationale**:
- At the documented scale (50 delivery men), only a subset will hold In-Custody booklets at any time. Typical operational reality: 5–10 delivery men with booklets, each holding a handful. The bar chart renders cleanly.
- Implementing a "top N + Other" bucket would require a Script chart — violates Principle II's preference for native primitives.
- The spec edge case accepts "truncating to the top holders with an indication that more exist, or by using a compact presentation" — the native chart's auto-truncation is a compact presentation.
- A deferred readability improvement (post-MVP): switch to a Script chart if a real deployment shows > 20 active holders and the default rendering is confusing.

**Alternatives considered**:
- *Script-backed chart with top-8 + Other bucket* — deferred; not needed at the documented scale.

---

## 11. Cache vs live data trade-off

**Decision**: Every Number Card, Dashboard Chart, and Quick List has `cache = 0` (no cache) set explicitly in the fixture. Quick Lists have no cache field; they always re-query on render.

**Rationale**:
- Spec FR-004 requires fresh data on every open/refresh. Even a short TTL cache (e.g. 60 s) would fail SC-007 verification in CI (the test "create a booklet → reopen dashboard → expect count + 1" would pass on first reopen but possibly fail immediately after if the cache refresh is scheduled).
- The widgets' queries are all indexed and return bounded small result sets — the performance cost of no-cache is negligible (< 500 ms per widget, well within SC-001).
- Frappe's platform-level short-TTL cache on Number Cards can be disabled per-record via `cache = 0`; the default for new Number Cards varies by Frappe version — explicit `cache = 0` is safest.

**Alternatives considered**:
- *Leave platform default (short TTL)* — rejected; introduces a subtle "stale data on refresh" bug class that the spec explicitly forbids.
- *Manual refresh button per widget* — rejected; every click requires user action, and the whole point of the dashboard is one-glance live data.

---

## 12. Workspace `content` JSON — block layout and bundle grouping

**Decision**: The workspace's `content` field is a JSON string of Frappe block elements. Phase 8's layout is three header-delimited sections, one per bundle:

```
header: "Operations" (Bundle 1)
number_card: Booklets In Stock | number_card: Booklets In Custody | chart: In-Custody Breakdown | number_card: Active Sold | chart: Today's Consumption
---
header: "Risk Watchlist" (Bundle 2)
number_card: Open Discrepancies (Red) | quick_list: Open Discrepancies | chart: Outstanding Liabilities
---
header: "Customer Follow-up" (Bundle 3)
chart: Customers Low on Coupons | quick_list: Recent Depleted Booklets
```

**Rationale**:
- The three-section layout maps directly to the spec's three User Stories — the workspace is self-documenting as the bundle structure.
- Placing the count Number Card (5a) immediately before the Quick List (5b) pairs them visually — the "0 open / no rows in list" vs "3 open / three rows" severity signal reads immediately.
- Frappe 15's `content` block language supports `header`, `card-break` (layout break), and element references by record name — all native, no custom rendering.
- The row ordering (Operations → Risk → Follow-up) mirrors the daily-morning workflow: first see operational health, then glance at risks, then pick up sales follow-up actions.

**Alternatives considered**:
- *Single flat row of all eight widgets* — rejected; visually overwhelming, no grouping cue.
- *Four rows (split Risk into two, one per widget)* — rejected; widgets 5a and 5b belong together visually.

**Concrete JSON** is captured in `contracts/dashboard.md` under §Workspace Content.

---

## 13. Phase-7 dependency timing

**Decision**: Phase 8 assumes Phase 7's `Delivery Man Liability Balance` and `Daily Delivery Man Summary` reports are merged to master before Phase 8's PR merges. Phase 8's integration test suite imports the Phase-7 `cx_purisol/cx_purisol/tests/report_seed.py` helper and extends it.

**Rationale**:
- The plan.md roadmap (docs/plan.md §"Dependency rule") orders Phases 6, 7, 8 with "Phase 7 before Phase 8" as the recommended shipping order.
- On the current `008-dashboard` branch, the Phase-7 reports exist only on the `007-reports` branch and are not yet on master. The implementation PR for Phase 8 will rebase on the post-Phase-7 master.
- If Phase 7 does not ship first, widgets 6 and 7 become broken references and the Phase-8 tests fail — this is desirable (CI catches the ordering mistake).

**Alternatives considered**:
- *Duplicate Phase-7's liability / daily-summary SQL inside Phase 8* — rejected; violates DRY and creates a drift risk.
- *Defer widgets 6 and 7 to a hypothetical Phase 8.1* — rejected; the spec requires all eight widgets in this phase.

---

## 14. Localisation: English-stored labels with `_()`-translation at render

**Decision**: Store every Number Card `label`, Dashboard Chart `chart_name`, Quick List `label`, and Workspace widget-header text in English in the fixture JSONs. Frappe's `_()` machinery translates them at render time using the active user's locale. Append Arabic translations to `cx_purisol/translations/ar.csv`.

**Rationale**:
- Matches constitution Principle IX and the existing Phase 1–7 pattern.
- Frappe's Number Card / Dashboard Chart / Quick List renderers auto-translate labels via `_()` without per-widget Python.
- The workspace `name` stays as `مياه نبع النعيم` (Arabic) — this is the unique identifier, not a display string; Frappe tolerates non-ASCII names.
- Arabic translations for the widget labels ("Booklets In Stock" → "دفاتر في المخزون", etc.) land in the same `ar.csv` that already holds Phase 1–7 translations.

**Alternatives considered**:
- *Store Arabic labels directly in the fixture JSONs* — rejected; breaks bilingual rendering (English users would see Arabic).
- *Skip `_()` on widget labels* — rejected; constitutional violation.

---

## 15. Patches anchor

**Decision**: Add one no-op patch entry `cx_purisol.patches.v0_8_0.add_dashboard_widgets` to `patches.txt`. The patch is a no-op because Workspace, Number Card, and Dashboard Chart fixtures migrate via `bench migrate`'s standard fixture loader.

**Rationale**:
- Matches the Phase-2/3/4/5/6/7 anchor pattern — every phase has a `v0_<phase>_0` patch entry as a version marker, even when no schema change is needed.
- Provides a clean "this is where Phase 8 starts" boundary in `patches.txt` for future archaeology.
- Costs almost nothing (one new file, one new line in `patches.txt`).

**Alternatives considered**:
- *Skip the patch* — rejected; breaks the consistency of the per-phase anchor pattern.
- *Add a non-trivial patch that explicitly creates the widget records via Python* — rejected; redundant with `bench migrate`'s fixture-sync.

---

## 16. Test seed reuse

**Decision**: Reuse Phase-7's `cx_purisol/cx_purisol/tests/report_seed.py` as the primary data seed for Phase-8 integration tests. Add one Phase-8-specific extension (a handful of In-Custody booklets distributed across delivery men, a handful of Depleted booklets with `depleted_on` spanning the last-7-days window, a handful of Customer × Sold-booklet combinations at/below the low-stock threshold) — these extensions live in `test_dashboard.py` itself rather than bloating `report_seed.py`.

**Rationale**:
- Reuses Phase-7's deterministic dataset so assertions use known constants.
- Avoids re-seeding the whole schema from scratch.
- Phase-8-specific data is inline-scoped to the test file that needs it — bundle independence (SC-009) is preserved because bundle-scoped tests can opt into only the data they need.

**Alternatives considered**:
- *Separate `dashboard_seed.py` helper* — rejected; duplicates Phase-7 primitives.
- *Ad-hoc per-test seeding without reuse* — rejected; assertions reference different magic numbers in each test, maintenance burden.

---

## 17. Non-admin user access — quickstart verification path

**Decision**: The Phase-8 integration test explicitly creates a non-admin user (plain desk user with no Purisol role) and asserts that (a) `frappe.get_doc("Workspace", "مياه نبع النعيم")` raises `frappe.PermissionError` when called as that user, and (b) `frappe.get_list("Workspace", filters=[["name","=","مياه نبع النعيم"]])` returns an empty list when called as that user.

**Rationale**:
- FR-003 requires the workspace to be unreachable by non-admin users — verified programmatically, not just by manual smoke.
- Frappe 15 gates Workspace access via the workspace's `roles` list; verifying the gate in an integration test catches any future regression from a fixture edit or permission model change.

**Alternatives considered**:
- *Manual smoke test only* — rejected; regressions silently slip through without an automated check.

---

## 18. Workspace `content` JSON escaping in the fixture file

**Decision**: The `content` field of the workspace is a JSON-serialised-as-string blob inside the fixture JSON, with embedded double quotes escaped. Example: `"content": "[{\"type\":\"header\",\"data\":{\"text\":\"Operations\"}},{\"type\":\"card-break\"},...]"`.

**Rationale**:
- Frappe's Workspace DocType stores `content` as a Long Text field holding JSON — not a nested object in the fixture. `bench import-fixtures` expects the serialised string.
- Writing the fixture by hand is tedious; the Phase-8 implementation will use a one-shot script (`bench execute` one-liner) to build the workspace through the UI, then export via `bench export-fixtures` to generate the correctly-escaped JSON string automatically.
- Alternatively, a small Python helper in `patches/v0_8_0/add_dashboard_widgets.py` could programmatically construct the `content` and write to `Workspace.db_set` — but this would be a non-no-op patch, violating §15's no-op convention. Better to build via UI + export.

**Alternatives considered**:
- *Hand-write the escaped `content` string directly in `workspace.json`* — acceptable but error-prone; mismatched escaping produces a broken workspace at load time.
- *Do the content build inside the patch* — rejected per §15; the patch is a version marker, not an active setup step.

---

## 19. Which Number Card `function` value to use

**Decision**: Every Phase-8 Number Card uses `function = "Count"`. No Number Card uses `Sum`, `Average`, `Min`, `Max`, or `Custom`.

**Rationale**:
- Widgets 1, 2a, 3, 5a all ask "how many records match this filter" — Count is the native fit.
- Sum-based widgets (outstanding liabilities) are handled by Dashboard Charts, not Number Cards, because Phase-8 pulls from a Report (widget 6) rather than a single DocType column.
- Custom-function Number Cards require a whitelisted Python function — avoidable complexity.

**Alternatives considered**:
- *Custom Number Card for widget 6 (outstanding total from GL)* — rejected; Dashboard Chart with chart_type = "Report" + x_field = "delivery_man" + y_axis = "open_balance" gives both the total (implicit in the chart's sum) and the per-delivery-man breakdown in one widget.

---

## 20. Widget-rendering failure modes under empty data

**Decision**: Each widget is tested with zero-data state (fresh install, no booklets / no discrepancies / no consumption / no depletions / no liabilities / no customers) and is expected to render:
- Number Cards: value = 0, no error.
- Dashboard Charts: empty chart frame with an axis and a "no data" subtitle rendered by Frappe's chart library.
- Quick Lists: empty list with a "no records" message rendered by Frappe.

**Rationale**:
- The spec explicitly requires graceful empty-state rendering (multiple edge cases: "no booklets exist yet", "no open discrepancies", "no depletions in last 7 days", etc.).
- Frappe 15's primitives handle empty state natively — no custom code required.
- The integration test sets up a fresh test site (effectively empty) and asserts every widget renders without raising — one test method per widget.

**Alternatives considered**:
- *Special-case "no data" placeholder widgets with custom copy* — rejected; Frappe's defaults are adequate and consistent with the rest of the desk UX.
