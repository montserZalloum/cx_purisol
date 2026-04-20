# Quickstart — Phase 6: Notifications

**Feature**: 006-notifications | **Date**: 2026-04-19

This quickstart walks through the four notification triggers Phase 6 enables, in the order an administrator would exercise them on a fresh install that has already been migrated through Phase 5. The only change visible to an administrator from pre-Phase-6 behaviour is that the bell icon on every page now lights up when any of the four qualifying events occurs.

---

## 0. One-time setup

No Phase-6-specific setup is required. Phase 6 relies on three things that already exist after Phase 5:

1. The `Purisol Administrator` role exists (Phase-0 fixture).
2. At least one user is enabled AND holds the `Purisol Administrator` role (production admin; test sites seed this via `seed_administrator_user`).
3. The two thresholds on `Purisol Settings` have their defaults (or admin-edited values):
   - `customer_low_stock_threshold` — default `3`
   - `warehouse_low_stock_threshold` — default `5`

Optionally, an administrator can edit the thresholds live (no restart needed):

1. Navigate to `Purisol Settings` → **Stock Thresholds** section.
2. Adjust `Customer Low-Stock Threshold` and/or `Warehouse Low-Stock Threshold`.
3. Save.

The next triggering event honours the new values (FR-006).

---

## 1. Trigger — New Discrepancy Opened

### Preconditions

- Administrator `admin@example.com` is enabled and holds the `Purisol Administrator` role.
- A booklet `WP-00001` exists, `Sold` to a customer, with all 20 coupons `Available`.

### Steps

1. Submit a Coupon Consumption Entry that causes Phase-5 detection to open a discrepancy — e.g. list `CP-00007` and `CP-00008`, skipping the earlier coupons in the booklet. Phase-5's detection logic creates a `Purisol Coupon Discrepancy` for the gap `{CP-00003..CP-00006}`.
2. Open the bell icon in the top-right corner of the ERPNext desk (or navigate to `/app/notification-log`).

### Observed outcomes

- The bell icon shows a red dot (unread notifications present).
- One new notification appears with:
  - Subject: `Discrepancy PCD-2026-xxxxx opened`
  - Body: `Discrepancy PCD-2026-xxxxx opened: Missing Coupons in booklet WP-00001, delivery man EMP-0001.`
  - Click-through: opens the discrepancy record `/app/purisol-coupon-discrepancy/PCD-2026-xxxxx`.
- If the consumption entry created multiple discrepancies (e.g., one per affected booklet), one notification appears per discrepancy.
- If multiple users hold the `Purisol Administrator` role, each gets their own notification (the bell icon is per-user).

### Notes

- The notification fires on the `after_insert` of the discrepancy record. Submit-resolution of the discrepancy (Story 3/4/5 of Phase 5) does NOT fire a notification — Phase 6 notifies on opening only.

---

## 2. Trigger — Customer Low Stock

### Preconditions

- Customer `C-AL-MASRI` has two booklets: `WP-00001` with 2 coupons remaining and `WP-00002` with 2 coupons remaining, both `Sold`, non-`Depleted`. Total remaining = 4.
- `Purisol Settings.customer_low_stock_threshold = 3`.
- Administrator user is enabled.

### Steps

1. Submit a Coupon Consumption Entry that consumes 2 coupons — one from `WP-00001`, one from `WP-00002`. After the submit, the customer's total remaining = 2.

### Observed outcomes

- Phase-4 + Phase-5 behaviour unchanged (coupons flip to `Consumed`, no discrepancies since the sequence is intact).
- One new bell notification appears for each administrator user:
  - Subject: `Customer Al-Masri Restaurant low on coupons`  _(customer_name, not the raw ID)_
  - Body: `Customer Al-Masri Restaurant has 2 coupons remaining. Prepare a new booklet.`
  - Click-through: opens the Customer record `/app/customer/C-AL-MASRI`.

### Re-fire behaviour

- If the Administrator submits another Consumption Entry for the same customer that further drops remaining to 1, the notification fires again with the new count. Phase 6's MVP policy: fire on every qualifying submit (no per-customer daily dedup).
- If a different customer (unaffected by the entry) is already below threshold, no notification fires for them — the check is scoped to customers touched by the current entry.

### Edge cases

- **Unassigned booklet**: if the entry consumes from a booklet whose status is not `Sold` (Phase-5 Unassigned Booklet case), that booklet's "customer" is skipped (typically `None`). No Customer Low Stock notification for the unassigned booklet; Phase-5's `Unassigned Booklet` discrepancy still fires (Story 1 path).
- **Threshold edited mid-day**: if the admin edits `customer_low_stock_threshold` from 3 to 5 at 10:00, the next submit at 10:01 evaluates against the new threshold of 5. No restart, no cache-bust.

---

## 3. Trigger — Warehouse Low Stock

### Preconditions

- `Purisol Settings.warehouse_low_stock_threshold = 5`.
- Exactly 5 booklets have status `In Stock`. No prior Warehouse Low Stock notification has fired today.

### Steps

1. Submit a Sales Invoice that sells one booklet to a customer (Phase-3 path). Post-submit, the sold booklet transitions to `Sold`, leaving 4 booklets with `In Stock` status.
2. Open the bell icon.

### Observed outcomes

- One new bell notification appears for each administrator user:
  - Subject: `Warehouse low on booklet stock`
  - Body: `Only 4 booklets remain in stock. Generate a new batch.`
  - Click-through: opens the `Purisol Coupon Booklet` list (no specific record name).
- `Purisol Settings.last_warehouse_low_stock_notified_on` is set to today's date (internal field; hidden from the Settings form but visible in the doc's Track Changes log).

### Dedup behaviour

- If another Sales Invoice is submitted the same day that leaves the count at 3 (or 2, or 1), no additional Warehouse Low Stock notification fires.
- The next morning, a Sales Invoice that drops the count further (or that observes the count still below threshold) fires a fresh notification and updates `last_warehouse_low_stock_notified_on` to the new date.

### Reset without waiting for the next day

Administrators with access to Purisol Settings can force a re-evaluation by clearing `last_warehouse_low_stock_notified_on`:

```
# From a bench console (dev / support path — not exposed in the UI):
frappe.db.set_single_value("Purisol Settings", "last_warehouse_low_stock_notified_on", None)
frappe.db.commit()
```

Generally unnecessary; dedup resets naturally at midnight.

---

## 4. Trigger — Booklet Depleted

### Preconditions

- Booklet `WP-00005` is `Sold` to customer `C-AL-MASRI`, with 19 coupons consumed and coupon `CP-00100` still `Available`.
- Administrator user is enabled.

### Steps

1. Submit a Coupon Consumption Entry listing `CP-00100`.

### Observed outcomes

- Phase-4 auto-depletion runs: `WP-00005.status = "Depleted"`, `WP-00005.depleted_on = now()`.
- One new bell notification appears for each administrator user:
  - Subject: `Booklet WP-00005 depleted`
  - Body: `Booklet WP-00005 for customer Al-Masri Restaurant is fully consumed. Follow up for resale.`
  - Click-through: opens the booklet record `/app/purisol-coupon-booklet/WP-00005`.

### Multi-booklet depletion

- If a single Consumption Entry depletes two booklets (e.g., the last coupon of `WP-00005` AND the last coupon of `WP-00006` in the same submit), two separate Booklet Depleted notifications fire — one per booklet, per administrator user.

### Interaction with Customer Low Stock

- When `WP-00005` depletes, the customer's total remaining (across their `Sold` non-`Depleted` booklets) drops — often triggering Story 2 (Customer Low Stock) as well. Both notifications fire, sourced from the same Consumption Entry submit. Each is a separate bell entry; the admin sees two.

---

## 5. Viewing and dismissing notifications

1. Click the bell icon in the top-right corner of the ERPNext desk.
2. The dropdown shows all unread notifications for the current user, ordered newest-first.
3. Click a notification to open the referenced record and mark the notification read.
4. Clear all notifications via the **Mark All as Read** action in the bell dropdown.
5. View the full history at `/app/notification-log` — standard ERPNext list filtered to the current user.

Phase 6 does not alter the bell UI itself — it just creates the Notification Log entries that populate it.

---

## 6. When notifications do NOT fire

- **Cancellation / amendment** of a Consumption Entry, Sales Invoice, or Discrepancy → no notification. Phase 6 triggers only on initial submit / insert (FR-018).
- **Resolution** of a discrepancy → no notification. Phase 6 notifies on discrepancy insert only (FR-017).
- **Zero enabled Administrator users** → silent no-op. The triggering business event still succeeds (FR-014).
- **Customer is `None`** (Unassigned Booklet case) → Customer Low Stock notification is skipped for that booklet; Phase-5's own Unassigned Booklet discrepancy still opens (Story 1 path).
- **Below-threshold but already fired today** (Warehouse Low Stock) → dedup suppresses re-fire.
- **Above-threshold** (any trigger) → no notification.

---

## 7. Localization

Every notification's fixed phrase is translatable via Frappe's standard `frappe._()` mechanism. A user whose `User.language = "ar"` sees the Arabic versions of the subjects and bodies, with dynamic fields (booklet names, counts, customer names) interpolated into the Arabic-ordered shell phrase.

Example Arabic rendering for the Customer Low Stock notification:

- Subject: `العميل Al-Masri Restaurant على وشك نفاد القسائم`
- Body: `لدى العميل Al-Masri Restaurant 2 قسيمة متبقية. جهّز دفتراً جديداً.`

---

## 8. Running the tests

```bash
bench --site <test-site> run-tests --app cx_purisol
```

The Phase-6 suite extends the Phase-5 green-run. A green run is the phase's definition of done.

Focused runs:

```bash
# Utility unit tests
bench --site <test-site> run-tests --app cx_purisol --module cx_purisol.cx_purisol.api.test_notify

# Discrepancy controller widening
bench --site <test-site> run-tests --app cx_purisol --module cx_purisol.cx_purisol.doctype.purisol_coupon_discrepancy.test_purisol_coupon_discrepancy

# Integration — all four stories
bench --site <test-site> run-tests --app cx_purisol --module cx_purisol.cx_purisol.tests.test_notification_flows
```

---

## 9. Debugging

If a notification unexpectedly fails to appear:

1. **Check the role**: `frappe.get_all("Has Role", filters={"role": "Purisol Administrator", "parenttype": "User"})` should list the admin users.
2. **Check user enablement**: `frappe.db.get_value("User", "admin@example.com", "enabled")` should be `1`.
3. **Check the Notification Log table directly**: `frappe.get_all("Notification Log", filters={"for_user": "admin@example.com"}, order_by="creation desc", limit=5)`.
4. **Check the dedup marker for warehouse notifications**: `frappe.db.get_single_value("Purisol Settings", "last_warehouse_low_stock_notified_on")` — if equal to today, dedup is active.
5. **Check Purisol Settings thresholds**: `frappe.get_doc("Purisol Settings").as_dict()` — confirm the live values.
6. **For discrepancy notifications**, verify `Purisol Coupon Discrepancy` records are being created (Phase 5 is working) — Phase 6 notifications are purely downstream of Phase 5 insert events.

---

## 10. Pluggable future channels

Phase 6 ships bell-icon-only delivery. To add email, WhatsApp, or SMS in a future phase:

1. Edit `cx_purisol/cx_purisol/api/notify.py`.
2. Add new private functions `_emit_email`, `_emit_whatsapp`, `_emit_sms` following the `_emit_bell` pattern.
3. Inside `send()`, fan out to each enabled channel (e.g., read a future `Purisol Settings.notification_channels` Table field, iterate over registered channels, call each).
4. No change to the four trigger sites.

This is the extensibility contract Phase 6 was designed around and is the reason `send()`'s signature is channel-agnostic (constitution VII).
