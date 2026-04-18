# Phase 1 Contract — Discrepancy Detection & Resolution

**Feature**: 005-discrepancy-detection | **Date**: 2026-04-18

This document defines the observable contracts Phase 5 exposes and consumes. All contracts are server-side Python interfaces; none are HTTP/REST endpoints. The only new whitelisted surface Phase 5 could conceivably add is "create a discrepancy manually", but the spec has no such requirement and the MVP deliberately omits it.

---

## 1. `Purisol Coupon Consumption Entry` submit — behavioural contract (widened)

### 1.1. Preconditions

Unchanged from Phase 4:

- Administrator session holds `Purisol Administrator` role.
- `self.coupons` non-empty (FR-030 from Phase 4).
- No duplicate `coupon` within `self.coupons` (FR-032 from Phase 4).
- Every listed coupon exists with `status = "Available"` at submit time (FR-031, FR-033 from Phase 4).

### 1.2. Postconditions — if zero discrepancies detected

- All Phase-4 postconditions hold verbatim (coupons flipped to `Consumed` with metadata, booklet aggregates recomputed, auto-depletion as applicable).
- `self.has_warnings == 0`.
- `self.discrepancies_detected` is empty.
- No `Purisol Coupon Discrepancy` records created.
- Zero UI modal.

### 1.3. Postconditions — if ≥1 discrepancy detected

- All Phase-4 postconditions hold verbatim (FR-002: detection is non-blocking).
- `self.has_warnings == 1`.
- `self.discrepancies_detected` contains one row per created discrepancy, each referencing the discrepancy via its `discrepancy` link field. The child table is ordered in creation order (Missing Coupons entries per booklet in iteration order, then Unassigned Booklet entries per coupon).
- N new `Purisol Coupon Discrepancy` records exist in the DB with `docstatus = 0, status = "Open"`, each:
  - `opened_on` = `now_datetime()` at the moment of detection (not `entry.posting_datetime` — the spec distinguishes "when the entry was posted" from "when the anomaly was detected", though at single-shop single-session operation they coincide).
  - `triggering_consumption_entry = self.name`.
  - `booklet = <the affected booklet>`.
  - `customer = booklet.customer` (null for Unassigned Booklet discrepancies).
  - `affected_coupons` populated per detection rule.
  - `related_delivery_men` populated per `_auto_populate_related_delivery_men` (including at minimum one row per touchpoint — may be empty only if the booklet is neither In Custody nor has any adjacent-30-days consumption entries, which is implausible given the entry itself is adjacent, so in practice always ≥ 1 row).
  - `estimated_amount` = computed per the fallback cascade; may be `0.0` if neither invoice nor price list resolves a rate.
  - `resolution_action = ""` (empty), `resolved_on = None`, `journal_entry = None`, `payment_entry = None`, `liable_delivery_man = None`, `resolution_notes = ""` (all blank; admin fills at resolution time).
- After the submit transaction commits, the client's `frm.after_save` handler fires the non-blocking modal listing each new discrepancy.

### 1.4. Atomicity failure modes

- Any `frappe.throw` from Phase-4 validation (empty, duplicate, unknown coupon, already-consumed) rolls back before any detection runs. Zero discrepancies created.
- Any `frappe.throw` from within the detection service (infrastructure failure) rolls back the entire submit. The Consumption Entry itself is not persisted; the coupons keep their pre-submit `Available` state; no discrepancy records exist.
- A crash after `db_update` but before the transaction commit: standard Frappe/MariaDB transaction semantics — nothing persists.

### 1.5. What this contract does NOT guarantee

- **Order of discrepancy names**: Missing Coupons discrepancies are created before Unassigned Booklet ones in the current implementation, but callers must not depend on this ordering.
- **Exact `estimated_amount`**: derived from live settings + invoice/price-list data; if those change between runs, the computed value changes. No snapshotting happens before submit.
- **Timezone of `opened_on`**: uses Frappe's configured timezone via `now_datetime()`. Integration tests should not hard-compare to wall-clock times; they should assert `opened_on >= t0_before_submit`.

---

## 2. Discrepancy detection service — `cx_purisol.cx_purisol.api.discrepancy`

### 2.1. Public entrypoint

```python
def detect_for_entry(entry: "PurisolCouponConsumptionEntry") -> list[str]:
    """
    Run Missing Coupons and Unassigned Booklet detection against `entry`.
    Assumes Phase-4 side effects are already applied (coupons of `entry`
    have status = "Consumed"; booklet aggregates are current).
    Returns the names of every Purisol Coupon Discrepancy created,
    possibly empty. Does NOT mutate `entry` or any of its downstream
    records.
    """
```

### 2.2. Guarantees

- **No mutation**: Never updates an existing `Purisol Coupon`, `Purisol Coupon Booklet`, `Purisol Coupon Consumption Entry`, or any other pre-existing record (FR-021). Only inserts fresh `Purisol Coupon Discrepancy` + child rows.
- **Idempotence for Missing Coupons**: If called twice in succession (hypothetically — in practice called exactly once per submit), the second call returns `[]` because the dedup filter excludes coupons already listed in Open Missing Coupons discrepancies for the same booklet.
- **Non-idempotence for Unassigned Booklet**: A coupon handed in a second time (only possible after a cancel of the first entry) would trigger a second Unassigned Booklet discrepancy for it — this is intended; each separate submission is an independent anomaly.
- **Transaction scope**: Uses the caller's current transaction. Any `frappe.throw` propagates out.

### 2.3. Error contract

- **`frappe.ValidationError`** only via DocType-level validations firing on insert (e.g., a required field missing, which would indicate a bug in the service). Not raised as an application concern.
- **DB errors** (e.g., `pymysql.err.OperationalError` from a constraint violation) propagate. Again, not expected in correct operation — the caller's transaction rolls back.

---

## 3. `Purisol Coupon Discrepancy` submit — behavioural contract

### 3.1. Preconditions

- Administrator session holds `Purisol Administrator` role.
- Discrepancy is in draft (`docstatus == 0`) with `status ∈ {"Open", "Under Review"}`.
- `resolution_action` is set to one of `"None"`, `"Add to Liability Ledger"`, `"Immediate Cash Payment"`.
- For `"Add to Liability Ledger"` and `"Immediate Cash Payment"`: `liable_delivery_man` is set to an existing `Employee`.
- For `"Add to Liability Ledger"`: `Purisol Settings.employee_liability_account` and `.discrepancy_offset_account` are both set and resolvable to existing `Account` records.
- For `"Immediate Cash Payment"`: `Purisol Settings.discrepancy_offset_account` and `.default_cash_account` are both set and resolvable.

### 3.2. Postconditions — `resolution_action = "None"`

- `docstatus == 1`, `status == "Resolved - Admin Error"`, `resolved_on` stamped.
- `journal_entry`, `payment_entry` both null.
- Zero financial documents created.
- Record is locked (subsequent edits / cancels rejected).

### 3.3. Postconditions — `resolution_action = "Add to Liability Ledger"`

- `docstatus == 1`, `status == "Resolved - Delivery Man Liable"`, `resolved_on` stamped.
- `journal_entry` holds the name of a newly-created submitted `Journal Entry` whose:
  - `posting_date` = today.
  - `voucher_type` = `"Journal Entry"`.
  - `user_remark` = localized `"Discrepancy {name} — liable {employee}"`.
  - Exactly two rows in `accounts`:
    - `[0]`: `account = Purisol Settings.employee_liability_account`, `party_type = "Employee"`, `party = self.liable_delivery_man`, `debit_in_account_currency = self.estimated_amount`, credit = 0.
    - `[1]`: `account = Purisol Settings.discrepancy_offset_account`, `credit_in_account_currency = self.estimated_amount`, debit = 0, no party.
  - JE's `total_debit == total_credit == self.estimated_amount`.
- `payment_entry` is null.
- Standard ERPNext GL reports show the debit line with the Employee's party attached.

### 3.4. Postconditions — `resolution_action = "Immediate Cash Payment"`

- `docstatus == 1`, `status == "Resolved - Paid"`, `resolved_on` stamped.
- `payment_entry` holds the name of a newly-created submitted `Payment Entry` whose:
  - `payment_type = "Receive"`.
  - `posting_date` = today.
  - `paid_from = Purisol Settings.discrepancy_offset_account`.
  - `paid_to = Purisol Settings.default_cash_account`.
  - `paid_amount = received_amount = self.estimated_amount`.
  - `party_type = "Employee"`, `party = self.liable_delivery_man`.
  - Exactly one `references` row: `reference_doctype = "Purisol Coupon Discrepancy"`, `reference_name = self.name`, `allocated_amount = self.estimated_amount`.
- `journal_entry` is null.
- Standard ERPNext cash-flow reports show the receive payment against the offset account.

### 3.5. Error contract — aggregated blocking errors

`before_submit` aggregates precondition failures and raises a single `frappe.ValidationError` joining them with `<br>`:

- Missing `resolution_action`: `"Please choose a resolution action before submitting."`
- `Add to Liability Ledger` missing `liable_delivery_man`: `"Liable Delivery Man is required for 'Add to Liability Ledger'."`
- `Add to Liability Ledger` missing `employee_liability_account`: `"Employee liability account is not configured in Purisol Settings."`
- `Add to Liability Ledger` missing `discrepancy_offset_account`: `"Discrepancy offset account is not configured in Purisol Settings."`
- `Immediate Cash Payment` missing `liable_delivery_man`: `"Liable Delivery Man is required for 'Immediate Cash Payment'."`
- `Immediate Cash Payment` missing `discrepancy_offset_account`: `"Discrepancy offset account is not configured in Purisol Settings."`
- `Immediate Cash Payment` missing `default_cash_account`: `"Default cash account is not configured in Purisol Settings."`

On any such raise: the submit rolls back, the discrepancy stays at `docstatus = 0, status = "Open"` (or whatever it was), no JE/PE is created.

### 3.6. Atomicity

- JE/PE `.insert()` + `.submit()` run inside the discrepancy's `before_submit`. A Frappe-native failure inside ERPNext's own validation (e.g., `Account` does not exist, or a `Journal Entry` debit/credit mismatch) propagates out; the whole resolution submit rolls back; neither the discrepancy nor the primitive persists.
- The discrepancy's `journal_entry` / `payment_entry` field holds a real name that maps to a real submitted document iff the resolution submit itself committed.

### 3.7. Lock contract (FR-017)

- Any write to a submitted (`docstatus = 1`) discrepancy is rejected by Frappe's built-in "Cannot edit submitted document" error.
- Cancellation (`docstatus → 2`) is rejected by our `on_cancel` throw.
- Amendment is disabled via `amend = 0` in permissions; the Amend button is not rendered.

---

## 4. `Purisol Coupon Discrepancy Coupon` — contract

Empty behavioural contract beyond Frappe's default for Link integrity. Link to `Purisol Coupon` is validated on save.

## 5. `Purisol Coupon Discrepancy Related Person` — contract

Empty behavioural contract. The parent-level auto-populate is the only path that writes these rows in Phase 5.

---

## 6. Post-submit modal — client contract

### 6.1. Trigger

`frappe.ui.form.on("Purisol Coupon Consumption Entry", "after_save")` — or more precisely `refresh` after a submit success, since `after_save` fires on every save including drafts. The actual hook is `refresh` gated by `frm.doc.docstatus === 1 && !frm.__discrepancy_modal_shown`.

### 6.2. Behaviour

If `frm.doc.has_warnings === 1 && frm.doc.discrepancies_detected.length > 0`:

1. Build an HTML `<ul>` where each `<li>` is `<a href="/app/purisol-coupon-discrepancy/{name}" target="_blank">{name}</a> — {discrepancy_type} — {booklet}`.
2. Call `frappe.msgprint({ title: __("Discrepancies detected"), message: html, indicator: "orange", wide: true })`.
3. Set `frm.__discrepancy_modal_shown = true` to prevent re-firing on further refreshes.

### 6.3. Non-blocking guarantee

- `frappe.msgprint` is non-blocking — the submit has already committed by the time the modal renders, and dismissing the modal does not affect state.
- The modal does **not** render for draft saves, non-warning submits, or for non-admin users (the latter is academic since only admins can submit the entry).

---

## 7. List view saved filter — client contract

### 7.1. Behaviour

On list load of `Purisol Coupon Discrepancy` without an explicit filter in the URL:

1. `listview_settings["Purisol Coupon Discrepancy"].onload = (listview) => { if (listview.filter_area.is_empty()) listview.filter_area.add("Purisol Coupon Discrepancy", "status", "=", "Open") }`.
2. Sort order: `opened_on desc` (default from DocType JSON `sort_field = opened_on, sort_order = DESC`).
3. Columns in list view: `discrepancy_type`, `booklet`, `customer`, `estimated_amount`, `opened_on`, plus the default `name`.

### 7.2. Override

If the admin navigates with an explicit URL filter (e.g., `/app/purisol-coupon-discrepancy?status=Resolved - Paid`), the explicit filter wins.

---

## 8. Test-contract summary

Every contract above must have at least one test that exercises both the success and the failure path. Specifically:

- `tests/test_discrepancy_flows.py::test_missing_coupons_detection_creates_one_open` — §1.3 success.
- `tests/test_discrepancy_flows.py::test_detection_idempotence` — §1.3 plus §2.2 second-call returns `[]`.
- `tests/test_discrepancy_flows.py::test_unassigned_booklet_per_coupon` — §1.3 for multiple unassigned coupons.
- `tests/test_discrepancy_flows.py::test_admin_error_resolution` — §3.2.
- `tests/test_discrepancy_flows.py::test_liability_resolution_creates_je` — §3.3.
- `tests/test_discrepancy_flows.py::test_cash_payment_resolution_creates_pe` — §3.4.
- `tests/test_discrepancy_flows.py::test_resolution_missing_preconditions` — §3.5 (parametrized).
- `doctype/purisol_coupon_discrepancy/test_purisol_coupon_discrepancy.py::test_locked_after_submit` — §3.7.
- `doctype/purisol_coupon_discrepancy/test_purisol_coupon_discrepancy.py::test_amend_disabled` — §3.7.
- `api/test_discrepancy.py::test_no_mutation_of_source_records` — §2.2 no-mutation guarantee.
- `api/test_discrepancy.py::test_estimated_amount_price_fallback_cascade` — §1.3 amount computation.
