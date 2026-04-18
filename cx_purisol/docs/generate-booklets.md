# Generate Booklets — Operational Guide

## Invoking from the Desk

1. Open **Purisol Coupon Booklet** in the desk (Home → Purisol Coupon Booklet).
2. Click the **Actions** button in the list view → **Generate Booklets**.
3. Enter **Quantity** (required, positive integer) and an optional **Batch ID**.
4. Click **Generate**.

For quantities ≤ 20, the dialog returns immediately with a summary (first/last booklet, total coupons, batch ID).

## Progress Feedback (Async Path)

For quantities > 20, generation runs in the background (`long` queue). A progress bar appears and updates as booklets are created. On completion, the same summary dialog is shown. If the job fails mid-run, an error message is displayed and the partial state is noted — already-committed booklets remain; no partial booklet (fewer than 20 coupons) is left behind.

## Recovering from a Stale `tabSeries`

If a generation is interrupted at the database level (server restart, worker kill), the `WP` or `CP` series counter in `tabSeries` may fall behind the actual maximum name. This causes a duplicate-key error on the next generation run. To recover:

```python
import frappe
max_wp = int(frappe.db.sql(
    "SELECT MAX(CAST(SUBSTRING(name, 4) AS UNSIGNED)) FROM `tabPurisol Coupon Booklet`"
)[0][0] or 0)
frappe.db.set_value("Series", "WP", "current", max_wp)
max_cp = int(frappe.db.sql(
    "SELECT MAX(CAST(SUBSTRING(name, 4) AS UNSIGNED)) FROM `tabPurisol Coupon`"
)[0][0] or 0)
frappe.db.set_value("Series", "CP", "current", max_cp)
frappe.db.commit()
```

Run from `bench --site <site-name> console`.

## Background Worker Checklist

- The `long` queue must have at least one running RQ worker: `bench --site <site-name> doctor`.
- Worker logs: `~/frappe-bench/logs/worker.*.log` or `bench logs`.
- Job timeout is 1 800 s (30 min), sufficient for ≈ 6 000 booklets at observed throughput.
