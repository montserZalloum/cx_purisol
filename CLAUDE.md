# cx_purisol Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-19

## Implementation Status
- 001-core-data-model: ✓ IMPLEMENTED
- 002-custody-management: ✓ IMPLEMENTED
- 003-sales-integration: ✓ IMPLEMENTED
- 004-consumption-recording: ✓ IMPLEMENTED
- 005-discrepancy-detection: ✓ IMPLEMENTED (all 6 user stories: Missing Coupons, Unassigned Booklet, Admin Error, Liability Ledger, Cash Payment, Investigation UX)

## Active Technologies
- Python 3.10+ (Frappe server), JavaScript (Frappe client scripts). + Frappe Framework 15.x, ERPNext 15.x (Employee link). No new third-party libraries. (002-custody-management)
- Frappe DocTypes on MariaDB via `frappe.db` / `frappe.get_doc`; no raw SQL writes. (002-custody-management)
- Python 3.10+ (Frappe server), JavaScript (Frappe client scripts). + Frappe Framework 15.x, ERPNext 15.x (`Sales Invoice`, `Sales Invoice Item`, `Customer`, `Item`, `Price List`, `Employee`). No new third-party libraries. (003-sales-integration)
- Frappe DocTypes on MariaDB via `frappe.db` / `frappe.get_doc`; no raw SQL writes. The custom field on `Sales Invoice Item` is managed as a `Custom Field` fixture — no core ERPNext schema edits. (003-sales-integration)
- Python 3.10+ (Frappe server), JavaScript (Frappe client scripts). + Frappe Framework 15.x, ERPNext 15.x (`Employee`, `Customer`, `User`). No new third-party libraries. Reuses Phase 1 DocTypes (`Purisol Coupon Booklet`, `Purisol Coupon`) and their existing reserved fields. (004-consumption-recording)
- Frappe DocTypes on MariaDB via `frappe.db` / `frappe.get_doc`; no raw SQL writes. Two new custom DocTypes (one submittable parent + one child table) plus a reserved-empty discrepancy child-table stub. No changes to existing Purisol DocType JSON — only the controllers widen. (004-consumption-recording)
- Python 3.10+ (Frappe server), JavaScript (Frappe client scripts). + Frappe Framework 15.x, ERPNext 15.x (`Employee`, `Customer`, `Sales Invoice`, `Sales Invoice Item`, `Journal Entry`, `Payment Entry`, `Account`, `Price List`, `Item Price`). No new third-party libraries. Reuses Phase-1 reserved account fields on `Purisol Settings` (`employee_liability_account`, `discrepancy_offset_account`, `default_cash_account`), Phase-2 `Purisol Custody Entry` for custody-holder lookup, Phase-3 `Sales Invoice Item.purisol_booklet` custom field for price-line lookup, Phase-4 `Purisol Coupon Consumption Entry` + `Purisol Coupon Discrepancy Item` stub. (005-discrepancy-detection)
- Frappe DocTypes on MariaDB via `frappe.db` / `frappe.get_doc` / `frappe.get_all`; no raw SQL writes. Three new custom DocTypes (one submittable parent + two child tables) and one minor JSON widening of the Phase-4 discrepancy stub (one new Link field). No schema change to any Phase 1/2/3/4 DocType beyond the `Purisol Coupon Discrepancy Item` widening. (005-discrepancy-detection)
- Python 3.10+ (Frappe server), JavaScript (Frappe client scripts — not used in this phase; zero client-side code is added). + Frappe Framework 15.x (`Notification Log`, `Has Role`, `User`), ERPNext 15.x (`Sales Invoice`, `Customer`, `Employee`). No new third-party libraries. Reuses Phase-1 `Purisol Settings` thresholds (`customer_low_stock_threshold`, `warehouse_low_stock_threshold`), Phase-1 `Purisol Coupon Booklet` aggregates (`remaining_count`, `status`, `customer`), Phase-4 `Purisol Coupon Consumption Entry` controller (widened in place), Phase-5 `Purisol Coupon Discrepancy` controller (widened in place with `after_insert`), Phase-3 `sales_invoice_hooks.py` module (adds one new function). Constitution role `Purisol Administrator` already exists as a Phase-0 fixture. (006-notifications)
- Frappe DocTypes on MariaDB via `frappe.db` / `frappe.get_doc` / `frappe.db.count` / `frappe.db.sql` / `frappe.db.set_single_value`; no raw SQL writes. Zero new custom DocTypes. One field added to `Purisol Settings` (`last_warehouse_low_stock_notified_on`). All Phase-6 writes are inserts on the framework-owned `Notification Log` DocType, plus the one single-value update on `Purisol Settings`. (006-notifications)
- Python 3.10+ (Frappe server). No JavaScript is added in this phase — the standard Frappe report viewer renders all ten reports without per-report JS. + Frappe Framework 15.x (`Report` DocType, `Notification Log` is unrelated, `frappe.db.sql`, `frappe.utils.date_diff`, `frappe.utils.nowdate`), ERPNext 15.x (`Sales Invoice`, `Sales Invoice Item` with the Phase-3 `purisol_booklet` custom field, `Journal Entry`, `Payment Entry`, `GL Entry`, `Account`, `Customer`, `Employee`, `Price List`). No new third-party libraries. Reuses Phase-1 `Purisol Coupon Booklet` (status, customer, sold_on, depleted_on, consumed_count, remaining_count, current_delivery_man, batch_id, creation), Phase-1 `Purisol Coupon` (status, consumed_on, consumed_by_delivery_man, consumption_entry, booklet), Phase-2 `Purisol Custody Entry` (entry_datetime, docstatus) + `Purisol Custody Entry Booklet` (booklet, parent), Phase-3 `Sales Invoice Item.purisol_booklet` custom field + `Sales Invoice` (posting_date, customer, selling_price_list, status, docstatus), Phase-4 `Purisol Coupon Consumption Entry` (posting_date, delivery_man, docstatus, total_coupons) + `Purisol Coupon Consumption Item` (coupon, booklet, customer), Phase-5 `Purisol Coupon Discrepancy` (discrepancy_type, status, opened_on, triggering_consumption_entry, booklet, customer, liable_delivery_man, estimated_amount, resolution_action, journal_entry, payment_entry, docstatus) + `Purisol Coupon Discrepancy Coupon` (coupon, parent), Phase-1 `Purisol Settings.employee_liability_account` (the GL-account setting). The Phase-2 `Current Custody by Delivery Man` Query Report is reused unmodified. (007-reports)
- Frappe DocTypes on MariaDB via `frappe.db.sql` (read-only) and `frappe.db.get_value` / `frappe.get_all` (read-only) only; no `frappe.db.insert` / `frappe.db.set_value` writes are introduced anywhere in Phase 7. Zero new DocTypes, zero schema changes, zero new fields. All Phase-7 code paths are read-only — they never mutate any record. (007-reports)

- Python 3.10+ (Frappe server), JavaScript (Frappe client scripts). + Frappe Framework 15.x, ERPNext 15.x (Item, Price List, Account links on Settings). No new third-party libraries. (001-core-data-model)

## Project Structure

```text
src/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python 3.10+ (Frappe server), JavaScript (Frappe client scripts).: Follow standard conventions

## Recent Changes
- 007-reports: Added Python 3.10+ (Frappe server). No JavaScript is added in this phase — the standard Frappe report viewer renders all ten reports without per-report JS. + Frappe Framework 15.x (`Report` DocType, `Notification Log` is unrelated, `frappe.db.sql`, `frappe.utils.date_diff`, `frappe.utils.nowdate`), ERPNext 15.x (`Sales Invoice`, `Sales Invoice Item` with the Phase-3 `purisol_booklet` custom field, `Journal Entry`, `Payment Entry`, `GL Entry`, `Account`, `Customer`, `Employee`, `Price List`). No new third-party libraries. Reuses Phase-1 `Purisol Coupon Booklet` (status, customer, sold_on, depleted_on, consumed_count, remaining_count, current_delivery_man, batch_id, creation), Phase-1 `Purisol Coupon` (status, consumed_on, consumed_by_delivery_man, consumption_entry, booklet), Phase-2 `Purisol Custody Entry` (entry_datetime, docstatus) + `Purisol Custody Entry Booklet` (booklet, parent), Phase-3 `Sales Invoice Item.purisol_booklet` custom field + `Sales Invoice` (posting_date, customer, selling_price_list, status, docstatus), Phase-4 `Purisol Coupon Consumption Entry` (posting_date, delivery_man, docstatus, total_coupons) + `Purisol Coupon Consumption Item` (coupon, booklet, customer), Phase-5 `Purisol Coupon Discrepancy` (discrepancy_type, status, opened_on, triggering_consumption_entry, booklet, customer, liable_delivery_man, estimated_amount, resolution_action, journal_entry, payment_entry, docstatus) + `Purisol Coupon Discrepancy Coupon` (coupon, parent), Phase-1 `Purisol Settings.employee_liability_account` (the GL-account setting). The Phase-2 `Current Custody by Delivery Man` Query Report is reused unmodified.
- 006-notifications: Added Python 3.10+ (Frappe server), JavaScript (Frappe client scripts — not used in this phase; zero client-side code is added). + Frappe Framework 15.x (`Notification Log`, `Has Role`, `User`), ERPNext 15.x (`Sales Invoice`, `Customer`, `Employee`). No new third-party libraries. Reuses Phase-1 `Purisol Settings` thresholds (`customer_low_stock_threshold`, `warehouse_low_stock_threshold`), Phase-1 `Purisol Coupon Booklet` aggregates (`remaining_count`, `status`, `customer`), Phase-4 `Purisol Coupon Consumption Entry` controller (widened in place), Phase-5 `Purisol Coupon Discrepancy` controller (widened in place with `after_insert`), Phase-3 `sales_invoice_hooks.py` module (adds one new function). Constitution role `Purisol Administrator` already exists as a Phase-0 fixture.
- 005-discrepancy-detection: Added Python 3.10+ (Frappe server), JavaScript (Frappe client scripts). + Frappe Framework 15.x, ERPNext 15.x (`Employee`, `Customer`, `Sales Invoice`, `Sales Invoice Item`, `Journal Entry`, `Payment Entry`, `Account`, `Price List`, `Item Price`). No new third-party libraries. Reuses Phase-1 reserved account fields on `Purisol Settings` (`employee_liability_account`, `discrepancy_offset_account`, `default_cash_account`), Phase-2 `Purisol Custody Entry` for custody-holder lookup, Phase-3 `Sales Invoice Item.purisol_booklet` custom field for price-line lookup, Phase-4 `Purisol Coupon Consumption Entry` + `Purisol Coupon Discrepancy Item` stub.


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan at
`specs/008-dashboard/plan.md`.
<!-- SPECKIT END -->
