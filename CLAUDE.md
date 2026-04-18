# cx_purisol Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-18

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
- 005-discrepancy-detection: Added Python 3.10+ (Frappe server), JavaScript (Frappe client scripts). + Frappe Framework 15.x, ERPNext 15.x (`Employee`, `Customer`, `Sales Invoice`, `Sales Invoice Item`, `Journal Entry`, `Payment Entry`, `Account`, `Price List`, `Item Price`). No new third-party libraries. Reuses Phase-1 reserved account fields on `Purisol Settings` (`employee_liability_account`, `discrepancy_offset_account`, `default_cash_account`), Phase-2 `Purisol Custody Entry` for custody-holder lookup, Phase-3 `Sales Invoice Item.purisol_booklet` custom field for price-line lookup, Phase-4 `Purisol Coupon Consumption Entry` + `Purisol Coupon Discrepancy Item` stub.
- 004-consumption-recording: Added Python 3.10+ (Frappe server), JavaScript (Frappe client scripts). + Frappe Framework 15.x, ERPNext 15.x (`Employee`, `Customer`, `User`). No new third-party libraries. Reuses Phase 1 DocTypes (`Purisol Coupon Booklet`, `Purisol Coupon`) and their existing reserved fields.
- 003-sales-integration: Added Python 3.10+ (Frappe server), JavaScript (Frappe client scripts). + Frappe Framework 15.x, ERPNext 15.x (`Sales Invoice`, `Sales Invoice Item`, `Customer`, `Item`, `Price List`, `Employee`). No new third-party libraries.


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
<!-- SPECKIT END -->
