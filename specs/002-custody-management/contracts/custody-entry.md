# Contract: Purisol Custody Entry — Submit / Cancel Behaviour

**Feature**: `002-custody-management` · **Date**: 2026-04-18

Phase 2 does **not** introduce a new whitelisted Python function. The interaction surface is the standard Frappe submittable DocType (desk UI + REST `/api/resource/Purisol Custody Entry` + `/api/method/frappe.client.save` + `/api/method/frappe.client.submit` + `/api/method/frappe.client.cancel`). This document specifies the contract that the `Purisol Custody Entry` DocType honours when exercised via any of those surfaces.

---

## Document shape (create / update)

All fields accepted by `POST /api/resource/Purisol Custody Entry` (draft) or `frappe.client.insert`:

```json
{
  "doctype": "Purisol Custody Entry",
  "entry_type": "Assign | Transfer | Return",
  "from_delivery_man": "<Employee name or null>",
  "to_delivery_man":   "<Employee name or null>",
  "entry_datetime":    "YYYY-MM-DD HH:MM:SS",
  "notes":             "<optional free text>",
  "booklets": [
    { "booklet": "WP-00001" },
    { "booklet": "WP-00002" }
  ]
}
```

- `created_by` is **server-populated** in `before_insert`; clients that supply it have their value ignored.
- `booklet_status_at_entry` and `delivery_man_at_entry` on child rows are **server-populated** in `before_submit` from the booklet's live state; clients that supply them have their value overwritten.
- `entry_datetime` defaults to `now()` if omitted; admin-supplied past values are permitted (back-dating is expected).

---

## Authorization

- Every write (insert, save, submit, cancel) requires the caller to hold the `Purisol Administrator` role. Missing role → `frappe.PermissionError` *before* any validation.
- Delete is **not** permitted by permission; cancel is the reversal path.
- Amend is **not** permitted by permission in this phase.

---

## Lifecycle and effects

### 1. Create / Save draft (`docstatus = 0`)

- Runs `validate` (see "Validation" below).
- No booklet is modified. No snapshot is captured.
- Mis-shaped drafts are rejected with `frappe.ValidationError` and not persisted.

### 2. Submit (`docstatus = 0 → 1`)

**Pre-submit (`before_submit`)**: populates `booklet_status_at_entry` and `delivery_man_at_entry` on every child row from the booklets' live state at this instant.

**Submit (`on_submit`)**: iterates every child row and updates the referenced `Purisol Coupon Booklet` under the request's transaction:

| `entry_type` | Booklet `status` after | Booklet `current_delivery_man` after |
|--------------|-----------------------|--------------------------------------|
| `Assign` | `In Custody` | `self.to_delivery_man` |
| `Transfer` | `In Custody` (unchanged) | `self.to_delivery_man` |
| `Return` | `In Stock` | `null` |

Writes go through `booklet.save(ignore_permissions=True)`, which triggers the booklet's own (widened) `validate`. If any booklet update fails, the whole transaction rolls back — all-or-nothing (spec FR-020, FR-024).

### 3. Cancel (`docstatus = 1 → 2`)

**Pre-condition**: for every child row, the referenced booklet's **current** `status` and `current_delivery_man` MUST match the post-submit expected state of this entry:

| `entry_type` | Expected current `status` | Expected current `current_delivery_man` |
|--------------|--------------------------|----------------------------------------|
| `Assign`, `Transfer` | `In Custody` | `self.to_delivery_man` |
| `Return` | `In Stock` | `null` |

If any booklet has a different current state (i.e., a subsequent Custody Entry moved it), the cancel is **rejected** with a `frappe.ValidationError` naming the booklet and the mismatch. The cancel does not partially succeed.

**Reversal**: if all pre-conditions pass, every referenced booklet is reverted to the snapshot captured at submit time:

- `booklet.status = row.booklet_status_at_entry`
- `booklet.current_delivery_man = row.delivery_man_at_entry`

Writes share the request's transaction; a mid-reversal failure rolls back everything.

### 4. Delete

Not permitted. Any attempt returns `frappe.PermissionError`.

---

## Validation rules (surface by error)

All validation runs in `validate` (pre-submit) and raises `frappe.ValidationError` with a translated message. Errors are **collected** across all rows before throwing, so one submit attempt reports every fixable issue in a single message.

| Condition | Message (before `_()`) |
|-----------|------------------------|
| Child table empty | `"Custody Entry must list at least one booklet."` |
| Same booklet appears twice in child table | `"Booklet {0} is listed more than once in this entry."` |
| `Assign` with `from_delivery_man` set | `"An Assign entry must not have a from_delivery_man."` |
| `Assign` without `to_delivery_man` | `"An Assign entry requires a to_delivery_man."` |
| `Return` with `to_delivery_man` set | `"A Return entry must not have a to_delivery_man."` |
| `Return` without `from_delivery_man` | `"A Return entry requires a from_delivery_man."` |
| `Transfer` without `from_delivery_man` or `to_delivery_man` | `"A Transfer entry requires both from_delivery_man and to_delivery_man."` |
| `Transfer` with `from_delivery_man == to_delivery_man` | `"A Transfer from a delivery man to themselves is not meaningful."` |
| `Assign` with a booklet not `In Stock` | `"Booklet {0} is not In Stock (current: {1})."` |
| `Return` / `Transfer` with a booklet not `In Custody` | `"Booklet {0} is not In Custody (current: {1})."` |
| `Return` / `Transfer` with a booklet held by someone other than `from_delivery_man` | `"Booklet {0} is held by {1}, not by {2}."` |
| Cancel with a booklet that has since moved | `"Cannot cancel: booklet {0} has since moved (current status: {1}, current holder: {2}). Cancel the subsequent custody event first."` |

No warning discrepancies are raised in this phase (per constitution V, custody rules are unambiguous).

---

## Post-conditions

After a successful submit of `Purisol Custody Entry X` with entry type `T`, child rows `R_1 … R_n`:

1. Every `R_i.booklet` has `status` and `current_delivery_man` equal to the post-submit expected values for `T` (table in §2 above).
2. Every `R_i.booklet_status_at_entry` and `R_i.delivery_man_at_entry` is populated to reflect the booklet's pre-submit state.
3. `X.docstatus = 1`, `X.name` is the allocated `PCE-YYYY-#####`.
4. The audit trail (`tabVersion` on `Purisol Coupon Booklet` for each listed booklet) records this change with timestamp and user.
5. No other booklet (not listed in `X.booklets`) has been modified.
6. No `Purisol Coupon` record has been modified — Custody Entries do not touch coupons.

After a successful cancel of `X`:

1. Every `R_i.booklet` has `status = R_i.booklet_status_at_entry` and `current_delivery_man = R_i.delivery_man_at_entry`.
2. `X.docstatus = 2`; `X` is immutable and cannot be re-submitted.
3. `X` remains queryable for audit purposes; the link from each booklet's change history still resolves.

---

## Concurrency

Two submits touching the same booklet are serialized by Frappe's optimistic locking on `Purisol Coupon Booklet.modified`:

- The first submit's transaction advances `modified` and commits.
- The second submit's `booklet.save(ignore_permissions=True)` sees a stale `modified` and raises `frappe.TimestampMismatchError`. Frappe aborts the second transaction; no partial write persists.
- The second Administrator sees a clear error and retries — at which point validation re-evaluates against the new state and typically reports the real conflict (e.g., "Booklet is held by X, not by Y").

Concurrent cancels against the same entry are serialized by the same mechanism on `Purisol Custody Entry.modified`.

---

## Report contract: Current Custody by Delivery Man

**Report name**: `Current Custody by Delivery Man`
**Report type**: Query Report
**Module**: `Cx Purisol`
**URL**: `/app/query-report/Current%20Custody%20by%20Delivery%20Man`

### Filters

| Filter | Type | Required | Default |
|--------|------|----------|---------|
| `delivery_man` | Link → Employee | No | (all) |
| `batch_id` | Data | No | (all) |

### Columns

| Column | Type | Description |
|--------|------|-------------|
| `current_delivery_man` | Link (Employee) | Who holds the booklet now. |
| `booklet` | Link (Purisol Coupon Booklet) | `WP-NNNNN` identifier. |
| `days_in_custody` | Int | Days since the most recent submitted Custody Entry touching this booklet. |
| `customer` | Link (Customer) | Always `null` in this phase; present for forward-compat with Phase 3. |
| `batch_id` | Data | Generation batch identifier (if any). |

### Rows

Exactly one row per `Purisol Coupon Booklet` with `status = "In Custody"`. Booklets in any other status do not appear.

### Ordering

Default order: `current_delivery_man` ASC, then `booklet` ASC. Grouping by `current_delivery_man` is available via Frappe's report grouping control.

### Performance

Queries rely on existing indexes (`Purisol Coupon Booklet.status`, `Purisol Coupon Booklet.current_delivery_man`, `Purisol Custody Entry Booklet.booklet`). Load target: ≤ 2 s for up to 1,000 `In Custody` booklets (spec SC-005).

---

## Out of scope for this contract

- Amendment of a submitted Custody Entry (deferred — cancel + new entry is the supported path).
- Bulk cancel or bulk re-route through a single API call (not required by spec).
- Emission of notifications on submit (Phase 5/6).
- Custody of coupon-level items (Custody Entries touch booklets only; consumption records coupon-level custody endings and lives in Phase 4).
