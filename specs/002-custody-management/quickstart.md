# Quickstart: Custody Management

**Feature**: `002-custody-management` · **Date**: 2026-04-18

A hands-on walkthrough for exercising Phase 2 on a site that already has Phase 1 (Core Data Model) installed.

---

## 1. Prerequisites

- A Frappe bench site with `cx_purisol` installed and migrated up to Phase 1.
- A Frappe user that holds the `Purisol Administrator` role.
- At least 2 Employee records to act as delivery men (e.g., `HR-EMP-00001 "Ali"`, `HR-EMP-00002 "Sami"`). Created via standard ERPNext HR onboarding.
- At least 4 `Purisol Coupon Booklet` records in `In Stock` status. If your Phase-1 install is fresh, run:

  ```python
  frappe.call("cx_purisol.api.booklet_generation.purisol_generate_booklets", quantity=4)
  ```

---

## 2. Apply the Phase-2 migration

```bash
cd ~/frappe-bench
bench --site <site-name> migrate
bench --site <site-name> clear-cache
bench build --app cx_purisol
```

After migration:

- DocTypes `Purisol Custody Entry` and `Purisol Custody Entry Booklet` exist.
- The Query Report `Current Custody by Delivery Man` is installed under the Purisol module.
- On the `Purisol Coupon Booklet` form, the fields `status` and `current_delivery_man` are read-only (locked by `purisol_coupon_booklet.js`).
- Role `Purisol Administrator` has `read / write / create / submit / cancel` on `Purisol Custody Entry`.

Verify with:

```bash
bench --site <site-name> console
```
```python
import frappe
frappe.get_meta("Purisol Custody Entry").is_submittable
# => 1
frappe.get_meta("Purisol Custody Entry Booklet").istable
# => 1
```

---

## 3. Assign booklets to a delivery man

In the desk, navigate to **Home → Purisol Custody Entry → New**:

1. `Entry Type`: `Assign`.
2. `To Delivery Man`: `HR-EMP-00001` (Ali).
3. `Entry Datetime`: default (now).
4. In the `Booklets` child table, add rows referencing `WP-00001` and `WP-00002`.
5. Click **Submit**.

Verify:

- The new entry appears as `PCE-2026-00001` with `docstatus = 1` (submitted).
- Open `WP-00001`: `status = In Custody`, `current_delivery_man = HR-EMP-00001`. Both fields are read-only in the form.
- Open `WP-00002`: same.
- Under the entry's **Booklets** table, each row shows `booklet_status_at_entry = In Stock` and `delivery_man_at_entry = (empty)` — the snapshot of the pre-submit state.

Or from the console:

```python
entry = frappe.get_doc({
    "doctype": "Purisol Custody Entry",
    "entry_type": "Assign",
    "to_delivery_man": "HR-EMP-00001",
    "booklets": [
        {"booklet": "WP-00001"},
        {"booklet": "WP-00002"},
    ],
})
entry.insert()
entry.submit()
print(entry.name, entry.docstatus)
# => PCE-2026-00001 1

print(frappe.db.get_value("Purisol Coupon Booklet", "WP-00001",
                          ["status", "current_delivery_man"], as_dict=True))
# => {"status": "In Custody", "current_delivery_man": "HR-EMP-00001"}
```

---

## 4. Transfer a subset of booklets between delivery men

Scenario: Ali meets Sami on the route and hands over only `WP-00001`.

1. **New Custody Entry**.
2. `Entry Type`: `Transfer`.
3. `From Delivery Man`: `HR-EMP-00001` (Ali).
4. `To Delivery Man`: `HR-EMP-00002` (Sami).
5. `Booklets`: only `WP-00001`.
6. **Submit**.

Verify:

- `WP-00001`: `current_delivery_man = HR-EMP-00002`. Status remains `In Custody`.
- `WP-00002`: unchanged; still held by Ali. This is the "partial transfer" guarantee — only listed booklets move.

Console:

```python
frappe.get_doc({
    "doctype": "Purisol Custody Entry",
    "entry_type": "Transfer",
    "from_delivery_man": "HR-EMP-00001",
    "to_delivery_man": "HR-EMP-00002",
    "booklets": [{"booklet": "WP-00001"}],
}).insert().submit()

frappe.db.get_value("Purisol Coupon Booklet", "WP-00001", "current_delivery_man")
# => "HR-EMP-00002"
frappe.db.get_value("Purisol Coupon Booklet", "WP-00002", "current_delivery_man")
# => "HR-EMP-00001"
```

---

## 5. Return a booklet to the shop

1. **New Custody Entry**.
2. `Entry Type`: `Return`.
3. `From Delivery Man`: `HR-EMP-00002` (Sami, who now holds `WP-00001`).
4. `Booklets`: `WP-00001`.
5. **Submit**.

Verify:

- `WP-00001`: `status = In Stock`, `current_delivery_man` cleared.

---

## 6. Observe the "Current Custody by Delivery Man" report

Navigate to **Reports → Purisol → Current Custody by Delivery Man** (or `/app/query-report/Current%20Custody%20by%20Delivery%20Man`).

Expected output (given the state after §5):

| current_delivery_man | booklet | days_in_custody | customer | batch_id |
|---------------------|---------|------------------|----------|----------|
| HR-EMP-00001 | WP-00002 | 0 | (null) | (null) |

- `WP-00001` does not appear (it's back in stock).
- Booklets `WP-00003` and `WP-00004` do not appear (they were never assigned).
- Grouping by `current_delivery_man` produces one group per delivery man currently holding at least one booklet.

Apply the `Delivery Man` filter = `HR-EMP-00001` to narrow further.

---

## 7. Rejection cases

### 7.1 Wrong source state

Try to Assign a booklet that's already in custody:

```python
frappe.get_doc({
    "doctype": "Purisol Custody Entry",
    "entry_type": "Assign",
    "to_delivery_man": "HR-EMP-00001",
    "booklets": [{"booklet": "WP-00002"}],  # already held by Ali
}).insert().submit()
# => frappe.ValidationError: "Booklet WP-00002 is not In Stock (current: In Custody)."
```

### 7.2 Wrong current holder

Try to Transfer a booklet from the wrong delivery man:

```python
frappe.get_doc({
    "doctype": "Purisol Custody Entry",
    "entry_type": "Transfer",
    "from_delivery_man": "HR-EMP-00002",  # but WP-00002 is held by Ali, not Sami
    "to_delivery_man":   "HR-EMP-00001",
    "booklets": [{"booklet": "WP-00002"}],
}).insert().submit()
# => frappe.ValidationError: "Booklet WP-00002 is held by HR-EMP-00001, not by HR-EMP-00002."
```

### 7.3 Self-transfer

```python
frappe.get_doc({
    "doctype": "Purisol Custody Entry",
    "entry_type": "Transfer",
    "from_delivery_man": "HR-EMP-00001",
    "to_delivery_man":   "HR-EMP-00001",
    "booklets": [{"booklet": "WP-00002"}],
}).insert().submit()
# => frappe.ValidationError: "A Transfer from a delivery man to themselves is not meaningful."
```

### 7.4 Empty or duplicate booklets

```python
frappe.get_doc({
    "doctype": "Purisol Custody Entry",
    "entry_type": "Assign",
    "to_delivery_man": "HR-EMP-00001",
    "booklets": [],
}).insert()
# => frappe.ValidationError: "Custody Entry must list at least one booklet."

frappe.get_doc({
    "doctype": "Purisol Custody Entry",
    "entry_type": "Assign",
    "to_delivery_man": "HR-EMP-00001",
    "booklets": [{"booklet": "WP-00003"}, {"booklet": "WP-00003"}],
}).insert()
# => frappe.ValidationError: "Booklet WP-00003 is listed more than once in this entry."
```

### 7.5 Missing required delivery-man field

```python
frappe.get_doc({
    "doctype": "Purisol Custody Entry",
    "entry_type": "Assign",
    "booklets": [{"booklet": "WP-00003"}],
}).insert()
# => frappe.ValidationError: "An Assign entry requires a to_delivery_man."
```

---

## 8. Cancel a Custody Entry

### 8.1 Happy path — nothing has moved since

Re-assign `WP-00001` to Ali (from §3 onwards it is back `In Stock`):

```python
e = frappe.get_doc({
    "doctype": "Purisol Custody Entry",
    "entry_type": "Assign",
    "to_delivery_man": "HR-EMP-00001",
    "booklets": [{"booklet": "WP-00001"}],
}).insert()
e.submit()
```

Now cancel it:

```python
e.cancel()
# WP-00001 should revert to In Stock, current_delivery_man cleared.
frappe.db.get_value("Purisol Coupon Booklet", "WP-00001",
                    ["status", "current_delivery_man"], as_dict=True)
# => {"status": "In Stock", "current_delivery_man": None}
```

### 8.2 Rejected cancel — booklet has since moved

Re-do the assign, then transfer it to Sami *before* cancelling the assign:

```python
e1 = frappe.get_doc({
    "doctype": "Purisol Custody Entry",
    "entry_type": "Assign",
    "to_delivery_man": "HR-EMP-00001",
    "booklets": [{"booklet": "WP-00001"}],
}).insert(); e1.submit()

e2 = frappe.get_doc({
    "doctype": "Purisol Custody Entry",
    "entry_type": "Transfer",
    "from_delivery_man": "HR-EMP-00001",
    "to_delivery_man":   "HR-EMP-00002",
    "booklets": [{"booklet": "WP-00001"}],
}).insert(); e2.submit()

e1.cancel()
# => frappe.ValidationError:
# "Cannot cancel: booklet WP-00001 has since moved
#  (current status: In Custody, current holder: HR-EMP-00002).
#  Cancel the subsequent custody event first."
```

Cancel the Transfer first, then the original Assign can be cancelled.

---

## 9. Reconstruct a booklet's custody history

```python
history = frappe.db.sql("""
    SELECT
        parent AS custody_entry,
        parenttype,
        modified
    FROM `tabPurisol Custody Entry Booklet`
    WHERE booklet = %s
    ORDER BY modified
""", ("WP-00001",), as_dict=True)
for row in history:
    entry = frappe.get_doc("Purisol Custody Entry", row.custody_entry)
    print(entry.name, entry.entry_type, entry.from_delivery_man, "→",
          entry.to_delivery_man, entry.entry_datetime, "docstatus:", entry.docstatus)
```

Output for a booklet that went through Assign → Transfer → (still held):

```text
PCE-2026-00004 Assign None → HR-EMP-00001 2026-04-18 14:10:00 docstatus: 1
PCE-2026-00005 Transfer HR-EMP-00001 → HR-EMP-00002 2026-04-18 14:11:00 docstatus: 1
```

Cancelled entries appear with `docstatus = 2` — still part of the audit chain, but not contributing to the current state.

---

## 10. Run the tests

```bash
bench --site <site-name> run-tests --app cx_purisol
```

All tests (Phase 1 + Phase 2) should pass on a clean database. The Phase-2 additions live in:

- `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_custody_entry/test_purisol_custody_entry.py` (unit)
- `cx_purisol/cx_purisol/cx_purisol/tests/test_custody_flows.py` (integration)
- `cx_purisol/cx_purisol/cx_purisol/report/current_custody_by_delivery_man/test_current_custody_by_delivery_man.py` (report)

---

## 11. Troubleshooting

- **`frappe.TimestampMismatchError` on submit**: another Administrator edited the booklet concurrently. Reload and resubmit.
- **`current_delivery_man` is editable in the form**: the client script `purisol_coupon_booklet.js` did not load. Run `bench build --app cx_purisol` and `bench --site <site-name> clear-cache`.
- **Cancel rejected with "has since moved"**: a later Custody Entry affects this booklet. Cancel the later entry first (the error message names the current state so you can find it).
- **Report shows 0 rows but booklets exist**: all booklets are `In Stock` (no one is currently in custody). Submit an `Assign` and refresh the report.
- **Permission denied on create**: the calling user lacks the `Purisol Administrator` role. Assign it via the User form.
