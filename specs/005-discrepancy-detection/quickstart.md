# Quickstart — Phase 5: Discrepancy Detection & Resolution

**Feature**: 005-discrepancy-detection | **Date**: 2026-04-18

This quickstart walks through the four core workflows Phase 5 enables, in the order an administrator would exercise them on a fresh install that has already been migrated through Phase 4.

---

## 0. One-time setup (Administrator)

1. Navigate to `Purisol Settings` → Accounts section.
2. Set **Employee Liability Account** to an existing `Account` (e.g., `"Employee Liability - Co"`).
3. Set **Discrepancy Offset Account** to an existing `Account` (e.g., `"Sales Adjustment - Co"`).
4. Set **Default Cash Account** to an existing `Account` (e.g., `"Cash - Co"`).
5. Save.

These three accounts are required for the two financial resolution paths. Without them set, the admin can still detect discrepancies and resolve via `None` (Admin Error), but `Add to Liability Ledger` and `Immediate Cash Payment` will fail with a clear error at submit time.

---

## 1. Trigger a Missing Coupons discrepancy

### Preconditions

- Booklet `WP-00001` is `Sold` to customer `CUST-0001`, with all 20 coupons `Available`.
- Delivery man `EMP-0001` has been issued the booklet (optional; just sets a custody holder for the related-men auto-populate).

### Steps

1. Create a new `Purisol Coupon Consumption Entry`.
2. Set `delivery_man = EMP-0001`, `posting_date = today`.
3. Add two rows to `coupons`: `CP-00007` (page 7 of WP-00001), `CP-00008` (page 8).
4. Submit.

### Observed outcomes

- The entry commits. `CP-00007` and `CP-00008` flip to `Consumed`.
- **But** `CP-00003`–`CP-00006` are still `Available`, so detection computes the gap `{3, 4, 5, 6}`.
- A new `Purisol Coupon Discrepancy` (e.g. `PCD-2026-00001`) is created with:
  - `discrepancy_type = "Missing Coupons"`, `status = "Open"`.
  - `booklet = WP-00001`, `customer = CUST-0001`.
  - `affected_coupons` = four rows (`CP-00003`..`CP-00006`).
  - `related_delivery_men` = the custody holder (if the booklet is `In Custody`) + `EMP-0001` (the triggering entry's delivery man, as an `Submitted Adjacent Coupons` row).
  - `estimated_amount` = `4 × coupon_unit_price` where unit price is derived from the Sales Invoice of the booklet divided by 20.
- A non-blocking modal appears on the entry's form listing the new discrepancy with a clickable link.
- The entry's `has_warnings = 1` and its `discrepancies_detected` table has one row pointing at `PCD-2026-00001`.

---

## 2. Trigger an Unassigned Booklet discrepancy

### Preconditions

- Booklet `WP-00002` is `In Stock` (never sold), all coupons `Available`.

### Steps

1. Create a new `Purisol Coupon Consumption Entry`.
2. Set `delivery_man = EMP-0001`.
3. Add one row: `CP-00025` (from `WP-00002`).
4. Submit.

### Observed outcomes

- `CP-00025` flips to `Consumed`.
- A new `Purisol Coupon Discrepancy` (e.g. `PCD-2026-00002`) is created with:
  - `discrepancy_type = "Unassigned Booklet"`, `status = "Open"`.
  - `booklet = WP-00002`, `customer = null`.
  - `affected_coupons` = one row (`CP-00025`).
  - `related_delivery_men` = `EMP-0001` (as `Submitted Adjacent Coupons`).
  - `estimated_amount` = either 0 (if no Item Price is configured for the coupon item in the default price list) or `coupon_item_price / 20`.
- Modal fires as in §1.

---

## 3. Resolve a discrepancy as Admin Error

### Preconditions

- `PCD-2026-00002` exists with `status = "Open"`.

### Steps

1. Navigate to `PCD-2026-00002` from the "Open Discrepancies" list view.
2. (Optional) Set `resolution_notes = "Booklet was handed out without running the sale — retroactive sale pending."`.
3. Set `resolution_action = "None"`.
4. Submit.

### Observed outcomes

- `status` becomes `Resolved - Admin Error`.
- `resolved_on` is stamped with the current datetime.
- `journal_entry` and `payment_entry` remain null.
- No `Journal Entry` or `Payment Entry` is created anywhere in ERPNext.
- The record is locked — any subsequent edit is rejected by Frappe; the Amend button does not appear.

---

## 4. Resolve a discrepancy by adding to the Liability Ledger

### Preconditions

- `PCD-2026-00001` exists with `status = "Open"`, `estimated_amount = 40.00` (4 coupons × 10 per coupon).
- `Purisol Settings` has the three accounts configured (§0).
- `EMP-0001` exists in ERPNext.

### Steps

1. Navigate to `PCD-2026-00001`.
2. (Optional) Edit `estimated_amount` to a different value, e.g., `35.00`.
3. Set `liable_delivery_man = EMP-0001`.
4. Set `resolution_action = "Add to Liability Ledger"`.
5. (Optional) `resolution_notes = "Delivery man admitted to losing the coupons during the route."`.
6. Submit.

### Observed outcomes

- A `Journal Entry` is created and submitted:
  - Debit line: `Employee Liability - Co`, party_type = `Employee`, party = `EMP-0001`, amount = `35.00` (or whatever `estimated_amount` is at submit).
  - Credit line: `Sales Adjustment - Co`, amount = `35.00`.
- `PCD-2026-00001.journal_entry` holds the JE's name.
- `PCD-2026-00001.status = "Resolved - Delivery Man Liable"`.
- `PCD-2026-00001.resolved_on` is stamped.
- The amount now appears on `EMP-0001`'s Employee Ledger balance (standard ERPNext report).
- The record is locked.

### Failure modes (things that correctly throw)

- Submitting without `liable_delivery_man` set → `"Liable Delivery Man is required for 'Add to Liability Ledger'."`
- Submitting without the two required settings accounts → error identifying the missing setting.

---

## 5. Resolve a discrepancy via Immediate Cash Payment

### Preconditions

- `PCD-2026-00003` (a different Open discrepancy) exists.
- `Purisol Settings.discrepancy_offset_account` and `.default_cash_account` both configured.

### Steps

1. Navigate to `PCD-2026-00003`.
2. Set `liable_delivery_man = EMP-0002`.
3. Set `resolution_action = "Immediate Cash Payment"`.
4. Submit.

### Observed outcomes

- A `Payment Entry` is created and submitted:
  - `payment_type = "Receive"`.
  - `paid_from = Sales Adjustment - Co` (discrepancy offset).
  - `paid_to = Cash - Co` (default cash).
  - `paid_amount = received_amount = <estimated_amount>`.
  - `party_type = "Employee"`, `party = EMP-0002`.
  - references row: `reference_doctype = "Purisol Coupon Discrepancy"`, `reference_name = "PCD-2026-00003"`, `allocated_amount = <estimated_amount>`.
- `PCD-2026-00003.payment_entry` holds the PE's name.
- `PCD-2026-00003.status = "Resolved - Paid"`.
- `PCD-2026-00003.resolved_on` is stamped.
- The PE appears in standard ERPNext cash-flow reports.

---

## 6. List and audit

### Steps

1. Navigate to `Purisol Coupon Discrepancy` list view.
2. The list loads with a default filter `status = "Open"` (the saved list-view behaviour).
3. Sort is `opened_on desc`.
4. Clear the filter to see every discrepancy including resolved ones, grouped naturally by status.

### What each resolved discrepancy retains

- `status`, `resolution_action`, `resolved_on`, `liable_delivery_man` (if applicable), `estimated_amount`, `resolution_notes`, and the link to `journal_entry` or `payment_entry`.
- The detection-time fields (`discrepancy_type`, `triggering_consumption_entry`, `booklet`, `customer`, `affected_coupons`, `related_delivery_men`, `opened_on`).

Every piece of the narrative — from "what was detected" through "what was decided" through "what was posted" — is recoverable from the discrepancy record alone (FR-019, constitution IV).

---

## 7. Cancel path

Cancellation is explicitly disabled on resolved discrepancies. The `on_cancel` throw message tells the admin to use a reversing JE/PE instead. This matches FR-017 and keeps the audit trail intact.

Cancellation of the triggering `Purisol Coupon Consumption Entry` does **not** cancel its linked discrepancies automatically (spec Assumption: out of scope for MVP). The admin handles those manually.

---

## 8. Running the tests

```bash
bench --site <test-site> run-tests --app cx_purisol
```

The Phase-5 suite extends Phase 4's clean-database run. A green run is the phase's definition of done.

Focused runs:

```bash
# Discrepancy DocType-local tests
bench --site <test-site> run-tests --app cx_purisol --module cx_purisol.cx_purisol.doctype.purisol_coupon_discrepancy.test_purisol_coupon_discrepancy

# Detection service tests
bench --site <test-site> run-tests --app cx_purisol --module cx_purisol.cx_purisol.api.test_discrepancy

# Integration tests
bench --site <test-site> run-tests --app cx_purisol --module cx_purisol.cx_purisol.tests.test_discrepancy_flows
```
