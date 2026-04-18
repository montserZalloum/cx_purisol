# Quickstart: Core Data Model — Booklets & Coupons

**Feature**: `001-core-data-model` · **Date**: 2026-04-18

A hands-on walkthrough for installing and exercising Phase 1. Assumes a working `frappe-bench` with a site that already has ERPNext installed.

---

## 1. Install the app on a site

```bash
cd ~/frappe-bench
bench get-app /path/to/cx_purisol          # once
bench --site <site-name> install-app cx_purisol
bench --site <site-name> migrate
```

After migration:
- The `Purisol Administrator` role exists.
- The `Purisol Settings` singleton exists with default thresholds (`customer_low_stock_threshold = 3`, `warehouse_low_stock_threshold = 5`, `enable_consumption_warnings = 1`). Accounting links are empty.

## 2. Assign the role

In the desk, open the User you intend to act as Administrator → **Roles** → add `Purisol Administrator`. Save.

## 3. Verify Purisol Settings

- Navigate to `/app/purisol-settings` (or **Home → Purisol Settings**).
- Confirm:
  - The form loads a single record (no "New" button).
  - Threshold fields hold the defaults above.
  - Accounting links are editable but optional.

Attempting to create a second `Purisol Settings` via the REST API should return an error — this is the structural guarantee enforced by `issingle = 1`.

## 4. Generate a small batch (synchronous path)

From the bench console:

```bash
bench --site <site-name> console
```

```python
import frappe
frappe.set_user("<admin-user>")
result = frappe.call(
    "cx_purisol.api.booklet_generation.purisol_generate_booklets",
    quantity=5,
)
print(result)
```

Expected:

```python
{
    "mode": "sync",
    "first_booklet": "WP-00001",
    "last_booklet": "WP-00005",
    "total_coupons": 100,
    "batch_id": None,
}
```

Verify:

- **Booklet list** (`/app/purisol-coupon-booklet`) shows 5 rows `WP-00001` … `WP-00005`, each with `status = In Stock`, `first_coupon = CP-00001/CP-00021/…`, `last_coupon = CP-00020/CP-00040/…`, `total_coupons = 20`, `consumed_count = 0`, `remaining_count = 20`.
- **Coupon list** (`/app/purisol-coupon`) shows 100 rows, `CP-00001` … `CP-00100`, each with `status = Available`, `page_number ∈ [1, 20]`.
- Booklet `WP-00003` contains coupons `CP-00041` through `CP-00060`.

## 5. Generate a second batch — continuity check

```python
frappe.call(
    "cx_purisol.api.booklet_generation.purisol_generate_booklets",
    quantity=2,
    batch_id="2026-04-18-A",
)
```

Expected:

```python
{
    "mode": "sync",
    "first_booklet": "WP-00006",
    "last_booklet": "WP-00007",
    "total_coupons": 40,
    "batch_id": "2026-04-18-A",
}
```

Verify:

- Booklet `WP-00007` contains coupons `CP-00121` through `CP-00140`.
- Filtering the booklet list by `batch_id = "2026-04-18-A"` returns exactly `WP-00006` and `WP-00007`.

## 6. Generate a large batch (background path)

From the desk (if the Generate Booklets form is wired) or from the console:

```python
frappe.call(
    "cx_purisol.api.booklet_generation.purisol_generate_booklets",
    quantity=50,
)
```

Expected immediate return:

```python
{
    "mode": "async",
    "job_name": "purisol_generate_booklets_<uuid>",
    "channel": "purisol_generate_booklets_progress",
    "quantity": 50,
}
```

The UI receives progress events on channel `purisol_generate_booklets_progress`. After completion:

- Total booklet count has increased by 50.
- Booklet `WP-00057` exists (assuming the sequence started at 1 and has reached 7 before this batch) with coupons continuing contiguously.
- A completion event with the same shape as the sync-path return is published on the realtime channel.

## 7. Rejection cases

```python
frappe.call("cx_purisol.api.booklet_generation.purisol_generate_booklets", quantity=0)
# raises frappe.ValidationError: "Quantity must be a positive integer."

frappe.call("cx_purisol.api.booklet_generation.purisol_generate_booklets", quantity=-5)
# raises frappe.ValidationError: "Quantity must be a positive integer."
```

## 8. Run the tests

```bash
bench --site <site-name> run-tests --app cx_purisol
```

All tests in the three files listed in research.md §8 should pass on a clean database.

## 9. Troubleshooting

- **`tabSeries` row for `WP` or `CP` out of sync with actual max name** (would manifest as a duplicate-name error on the next generation): inspect with `SELECT name, current FROM tabSeries WHERE name IN ('WP', 'CP')`. If it lags, reset with:

  ```python
  import frappe
  max_wp = int(frappe.db.sql("SELECT MAX(CAST(SUBSTRING(name, 4) AS UNSIGNED)) FROM `tabPurisol Coupon Booklet`")[0][0] or 0)
  frappe.db.set_value("Series", "WP", "current", max_wp)
  max_cp = int(frappe.db.sql("SELECT MAX(CAST(SUBSTRING(name, 4) AS UNSIGNED)) FROM `tabPurisol Coupon`")[0][0] or 0)
  frappe.db.set_value("Series", "CP", "current", max_cp)
  frappe.db.commit()
  ```

  This is an operational guard, not a Phase 1 requirement — the generation code is expected to leave `tabSeries` consistent.

- **Background job appears not to run**: check `bench --site <site-name> doctor` and the RQ worker logs (`bench logs` or `~/frappe-bench/logs/worker.*.log`). Ensure the `long` queue has at least one running worker.

- **`PermissionError` on generation**: the calling user is missing the `Purisol Administrator` role. Confirm via the User form.
