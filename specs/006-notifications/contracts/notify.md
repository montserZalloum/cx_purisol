# Phase 1 Contract — Notifications

**Feature**: 006-notifications | **Date**: 2026-04-19

This document defines the observable contracts Phase 6 exposes and consumes. All contracts are server-side Python interfaces or ERPNext-framework-level hook invocations; none are HTTP/REST endpoints. Phase 6 ships zero whitelisted surfaces.

---

## 1. `Purisol Notify.send()` — utility contract

**Location**: `cx_purisol.cx_purisol.api.notify.send`

### 1.1. Signature

```python
def send(
    recipient: str,
    subject: str,
    message: str,
    reference_doctype: str | None = None,
    reference_name: str | None = None,
) -> list[str]:
    ...
```

### 1.2. Preconditions

- Called from inside a Frappe request / submit / background-job transaction (caller's transaction is the unit of atomicity).
- `recipient` is a non-empty string that names either a `Role` or a `User`.
- `subject` and `message` are non-empty strings. Both SHOULD already be translated by the caller via `frappe._()` with interpolated field values.
- `reference_doctype` is either `None`, `""`, or the exact name of an existing DocType. Not validated by the utility (ERPNext validates at render-time).
- `reference_name` is either `None`, `""`, or an exact record name within the `reference_doctype`. Not validated by the utility.

### 1.3. Postconditions — success

- One `Notification Log` record exists per enabled user resolved from `recipient`, each with:
  - `type = "Alert"`
  - `subject` = the argument verbatim
  - `email_content = message` (note: Frappe's "email_content" field is the bell body field regardless of delivery channel)
  - `for_user` = one resolved user per row
  - `document_type = reference_doctype` (or `None` if not supplied)
  - `document_name = reference_name` (or `None` if not supplied)
  - `from_user = None`
- Returns a list of the created `Notification Log.name` values, in resolver order.
- Zero mutations to any other DocType.

### 1.4. Postconditions — empty recipient set

- No `Notification Log` records are created.
- Returns `[]`.
- No exception raised (FR-014).
- The triggering business event that invoked `send()` proceeds normally.

**Qualifying empty-recipient cases**:

1. `recipient` names a role that no user holds.
2. `recipient` names a role whose users are all `User.enabled = 0`.
3. `recipient` names a non-existent role/user.
4. `recipient` is an empty string or whitespace.

### 1.5. Atomicity

- The utility runs in the caller's transaction. If any `Notification Log.insert()` raises, the utility propagates the exception. The caller's transaction rolls back — the Notification Log inserts already performed in this call are rolled back along with the business event.
- No `frappe.enqueue`. No `commit`/`rollback` inside the utility. No savepoints.

### 1.6. Idempotence

- `send()` is NOT idempotent — two calls with identical arguments create two distinct Notification Log records. Dedup is the caller's responsibility (e.g., the warehouse trigger implements it via a `Purisol Settings` field).

### 1.7. What this contract does NOT guarantee

- **Order of Notification Log names across recipients**: the list returned from `send()` matches `_resolve_recipients` internal order, which matches the DB's `frappe.get_all("User", filters=...)` order. Callers must not depend on it.
- **Channel beyond bell**: Phase 6 delivers only via `Notification Log` (bell). A future phase may add email / SMS; this is transparent to call sites.
- **Permission check on recipient's ability to see the reference record**: if `reference_doctype`/`reference_name` point at a record the recipient user lacks read permission for, the bell link still appears but clicking it will return a permission error. Phase 6 does not pre-filter recipients by reference-read permission — the `Purisol Administrator` role has read on every Purisol/ERPNext DocType Phase 6 references.

---

## 2. `Purisol Coupon Discrepancy.after_insert` — behavioural contract

### 2.1. Preconditions

- A `Purisol Coupon Discrepancy` record has just been `.insert()`ed (draft, `docstatus = 0`, `status = "Open"`).
- The record has `triggering_consumption_entry`, `booklet`, and `discrepancy_type` set (Phase-5 detection always populates these).
- The insert is happening inside some caller's transaction (typically `PurisolCouponConsumptionEntry.on_submit` via `detect_for_entry`; possibly a test fixture via `seed_open_discrepancy`).

### 2.2. Postconditions — if ≥1 enabled Administrator user exists

- One `Notification Log` entry exists per administrator user, with:
  - `subject = _("Discrepancy {name} opened").format(self.name)`
  - `email_content = _("Discrepancy {name} opened: {type} in booklet {booklet}, delivery man {dm}.").format(self.name, _(self.discrepancy_type), self.booklet, delivery_man or "(unknown)")`
  - `document_type = "Purisol Coupon Discrepancy"`
  - `document_name = self.name`
- No mutations to the discrepancy or any other record.

### 2.3. Postconditions — if no enabled Administrator exists

- Zero `Notification Log` entries created.
- Discrepancy insert succeeds normally. The host submit (typically the consumption entry) proceeds.

### 2.4. Atomicity

- Runs in the transaction that enclosed the `.insert()`. A raise propagates and rolls back the whole stack (consumption entry submit → discrepancy insert → `after_insert` notification calls → all rolled back atomically).

### 2.5. What this contract does NOT cover

- **Discrepancy submit (resolution)**: `after_insert` does NOT fire on submit. Phase-6 does not notify on resolution (FR-017).
- **Discrepancy cancellation / trash**: Phase-6 does not notify on these either (FR-018).

---

## 3. `Purisol Coupon Consumption Entry.on_submit` widening — behavioural contract

### 3.1. Preconditions

- Consumption Entry is being submitted through the standard Phase-4 submit path.
- Phase-4 side effects (coupon flips, booklet aggregates) have completed inside `on_submit`.
- Phase-5 detection has completed (zero or more discrepancies created; each triggered its own `after_insert` notification per §2).

### 3.2. Postconditions — Booklet Depleted

- For each booklet in `booklets` set that transitioned from `Sold` to `Depleted` in this submit (`triggered_depletion == True` post-Phase-4):
  - One `Notification Log` entry per administrator user with:
    - `subject = _("Booklet {0} depleted").format(booklet.name)`
    - `email_content = _("Booklet {0} for customer {1} is fully consumed. Follow up for resale.").format(booklet.name, customer_name or "(unknown)")`
    - `document_type = "Purisol Coupon Booklet"`
    - `document_name = booklet.name`

- A Consumption Entry that depletes two booklets creates two separate Booklet Depleted notifications per administrator user (US4 Acceptance 2).

### 3.3. Postconditions — Customer Low Stock

- For each unique customer among all touched Sold booklets:
  - If `SUM(remaining_count) FOR customer AND status='Sold' <= customer_low_stock_threshold`:
    - One `Notification Log` entry per administrator user with:
      - `subject = _("Customer {0} low on coupons").format(customer_name)`
      - `email_content = _("Customer {0} has {1} coupons remaining. Prepare a new booklet.").format(customer_name, total_remaining)`
      - `document_type = "Customer"`
      - `document_name = customer.name`
- Booklets with `customer IS NULL` (Unassigned Booklet cases) are excluded from evaluation.
- Threshold is read freshly per submit from `frappe.get_doc("Purisol Settings").customer_low_stock_threshold` (no cache) — so live admin edits to the threshold take effect on the next submit (SC-005).

### 3.4. Interaction with existing Phase-4 tests

- Phase-4 tests that submit a consumption entry where a booklet depletes OR a customer drops below threshold will now create Notification Log entries as a side effect. Those tests continue to pass because they never asserted absolute Notification Log counts.
- No Phase-4 test changes required for Phase-6 correctness.

### 3.5. Atomicity

- The two Phase-6 blocks both run inside the same `on_submit` transaction as Phase-4 and Phase-5 side effects. A raise in any block rolls the whole submit back.

---

## 4. `Sales Invoice.on_submit` via `check_warehouse_low_stock` — behavioural contract

### 4.1. Preconditions

- A `Sales Invoice` was just submitted.
- Phase-3's `mark_booklets_sold` has already run in the same `on_submit` event chain (Frappe runs the list-form `doc_events` handlers in order; Phase-6 handler is registered second). So any booklets sold on this invoice are now `status = "Sold"` and are excluded from the `In Stock` count.

### 4.2. Postconditions — threshold-below + not-yet-fired-today

- One `Notification Log` entry per administrator user with:
  - `subject = _("Warehouse low on booklet stock")`
  - `email_content = _("Only {0} booklets remain in stock. Generate a new batch.").format(in_stock_count)`
  - `document_type = "Purisol Coupon Booklet"`
  - `document_name = None`
- `Purisol Settings.last_warehouse_low_stock_notified_on = frappe.utils.today()` (single-value write).

### 4.3. Postconditions — not below threshold

- No notifications created.
- No write to `last_warehouse_low_stock_notified_on`.

### 4.4. Postconditions — below threshold but already fired today

- No notifications created.
- No write to `last_warehouse_low_stock_notified_on` (idempotent same-day re-check).

### 4.5. Day-boundary behaviour

- After server-clock crosses midnight, `frappe.utils.today()` returns the new date. The comparison `settings.last_warehouse_low_stock_notified_on == today` becomes false, and the next qualifying submit fires a fresh notification and updates the dedup marker to the new date. No scheduler or cron needed (research.md §10).

### 4.6. Concurrency note

- Two concurrent `on_submit` runs against the same singleton row may both pass the dedup check (both read "yesterday") before either writes "today". The worst-case is two Notification Log entries per admin instead of one. Acceptable for single-shop single-admin operation; not a correctness issue.

### 4.7. Invoice-level interactions

- An invoice that does NOT reference any Purisol booklet still triggers this hook (all Sales Invoices run the hook). The `in_stock_count` is unchanged relative to the pre-invoice state, and dedup semantics apply identically. This matches US3 Acceptance 6.
- Invoice cancellation / amendment does NOT emit a warehouse notification (FR-018 — only `on_submit`).

---

## 5. `Notification Log` record shape — data contract

Each entry inserted by Phase 6:

| Field | Value |
|-------|-------|
| `doctype` | `"Notification Log"` |
| `type` | `"Alert"` |
| `subject` | localized short phrase, ≤ 140 chars |
| `email_content` | localized body, plain text |
| `for_user` | exactly one User name per row |
| `document_type` | target DocType or `None` |
| `document_name` | target record name or `None` |
| `from_user` | `None` |
| `read` | `0` (default, unread) |

Every other field on `Notification Log` (e.g., `category`, `link`, `attached_file`) is left at default.

---

## 6. Error contract — aggregated across all four triggers

- **Infrastructure failures in `notify.send()`** (DB error during `Notification Log.insert`, etc.): propagate out, roll back the host submit.
- **Input programming errors** (`subject=""`, `recipient=None`): propagate out as `TypeError`/`ValueError`. These indicate a bug in a Phase-6 trigger site and are not expected in correct operation.
- **Empty recipient set** (role has no enabled users, unknown recipient name): NOT an error. Silent no-op, returns `[]`, host submit continues (FR-014).
- **Reference record does not exist** (e.g. `reference_name` points at a deleted record): the `Notification Log` insert still succeeds. The bell-icon click-through will later show "record not found". Phase 6 does not pre-validate references.
- **ERPNext Notification Log DocType missing** (stripped-down Frappe install): `.insert()` raises `DoesNotExistError`, the host submit rolls back, admin sees a clear error. This is a deployment configuration issue, not a Phase-6 bug (research.md §11).

---

## 7. Translation contract

Every user-visible fixed phrase is wrapped in `frappe._()`:

| Context | Source string |
|---------|---------------|
| New Discrepancy subject | `Discrepancy {0} opened` |
| New Discrepancy body | `Discrepancy {0} opened: {1} in booklet {2}, delivery man {3}.` |
| Customer Low Stock subject | `Customer {0} low on coupons` |
| Customer Low Stock body | `Customer {0} has {1} coupons remaining. Prepare a new booklet.` |
| Warehouse Low Stock subject | `Warehouse low on booklet stock` |
| Warehouse Low Stock body | `Only {0} booklets remain in stock. Generate a new batch.` |
| Booklet Depleted subject | `Booklet {0} depleted` |
| Booklet Depleted body | `Booklet {0} for customer {1} is fully consumed. Follow up for resale.` |
| Fallback customer name | `(unknown)` |
| `discrepancy_type` value (interpolated translatable) | `Missing Coupons` / `Unassigned Booklet` (already in Phase-5 translation set) |

Every phrase above MUST have a row in `cx_purisol/translations/ar.csv` for the Arabic rendering to be complete (research.md §12).

---

## 8. Test-contract summary

Every contract above must have at least one test that exercises both the success and the failure path.

- `api/test_notify.py::test_send_role_expands_to_all_enabled_users` — §1.3 success path.
- `api/test_notify.py::test_send_role_excludes_disabled_users` — §1.4 (disabled user filtered).
- `api/test_notify.py::test_send_unknown_role_is_silent_no_op` — §1.4 (unknown recipient).
- `api/test_notify.py::test_send_user_recipient_direct` — §1.3 with user-shaped recipient.
- `api/test_notify.py::test_send_rolls_back_on_insert_failure` — §1.5 (atomicity on raise).
- `doctype/purisol_coupon_discrepancy/test_purisol_coupon_discrepancy.py::test_after_insert_fires_notification` — §2.2.
- `doctype/purisol_coupon_discrepancy/test_purisol_coupon_discrepancy.py::test_after_insert_no_admin_silent` — §2.3.
- `doctype/purisol_coupon_consumption_entry/test_purisol_coupon_consumption_entry.py::test_depletion_fires_booklet_depleted_notification` — §3.2 (optional; may live in integration tests).
- `tests/test_notification_flows.py::test_story1_discrepancy_notification` — end-to-end Story 1.
- `tests/test_notification_flows.py::test_story2_customer_low_stock` — end-to-end Story 2.
- `tests/test_notification_flows.py::test_story2_unassigned_booklet_skips_customer_check` — spec edge case (customer=None excluded).
- `tests/test_notification_flows.py::test_story2_threshold_live_edit` — SC-005 (threshold edit mid-session).
- `tests/test_notification_flows.py::test_story3_warehouse_low_stock_first_fire` — end-to-end Story 3 first-qualifying-submit.
- `tests/test_notification_flows.py::test_story3_warehouse_low_stock_dedup_same_day` — US3 Acceptance 2 (same-day dedup).
- `tests/test_notification_flows.py::test_story3_warehouse_low_stock_resets_next_day` — US3 Acceptance 3 (day boundary).
- `tests/test_notification_flows.py::test_story3_warehouse_low_stock_strict_inequality` — US3 Acceptance 4.
- `tests/test_notification_flows.py::test_story4_booklet_depleted_notification` — end-to-end Story 4.
- `tests/test_notification_flows.py::test_story4_multi_booklet_depletion_fires_per_booklet` — US4 Acceptance 2.
- `tests/test_notification_flows.py::test_atomicity_rolls_back_notifications_with_submit` — SC-008.
- `tests/test_notification_flows.py::test_no_admin_triggers_all_silent_no_op` — SC-007.
