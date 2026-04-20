# Phase 1 Data Model — Notifications

**Feature**: 006-notifications | **Date**: 2026-04-19

Phase 6 introduces **zero** new custom DocTypes, **zero** new child tables, **zero** new roles, and **zero** new custom-field fixtures. It adds **one** field to the `Purisol Settings` singleton, widens **two** existing controllers (`PurisolCouponDiscrepancy`, `PurisolCouponConsumptionEntry`), adds one function to **one** existing module (`sales_invoice_hooks.py`), and ships **one** new server-side utility module (`api/notify.py`). The schema footprint of Phase 6 is deliberately minimal — almost all the work is plumbing that reads existing data and writes to the framework-owned `Notification Log` DocType.

---

## 1. New server-side utility — `cx_purisol/cx_purisol/api/notify.py`

**Purpose**: Single, channel-agnostic entry point for every Phase-6 bell-icon notification. Internally dispatches to the only channel registered in Phase 6 (ERPNext `Notification Log`); a later phase adds email / SMS / WhatsApp by editing this module only.

### 1.1. Public API

```python
def send(
    recipient: str,
    subject: str,
    message: str,
    reference_doctype: str | None = None,
    reference_name: str | None = None,
) -> list[str]:
    """
    Create one Notification Log entry per enabled user matching `recipient`.

    `recipient` may be either an exact Role name (preferred) or an exact User name.
    Role input expands to the set of enabled users holding that role; unknown roles,
    unknown users, and disabled users all collapse to an empty recipient set and
    a silent no-op (no error raised).

    Returns the list of Notification Log names created, possibly empty.
    Runs inside the caller's transaction.  Any raise propagates and rolls back.
    """
```

### 1.2. Private helpers

```python
def _resolve_recipients(recipient: str) -> list[str]:
    """
    Resolve a role-or-user input to a list of enabled User names.
    Role-first resolution; falls back to direct User lookup.
    Empty result on unknown input or all-disabled role (FR-014).
    """

def _emit_bell(
    for_user: str,
    subject: str,
    message: str,
    reference_doctype: str | None,
    reference_name: str | None,
) -> str:
    """
    Create one Notification Log entry with type='Alert' targeting for_user.
    Returns the created Notification Log name.
    """
```

### 1.3. Constants / imports

```python
from __future__ import annotations

import frappe
from frappe import _
```

No module-level mutable state. No cached values. Every call re-resolves recipients fresh so admin changes take effect immediately (FR-006).

### 1.4. Module conventions

- Wraps every user-visible string at call sites via `frappe._()` — the utility itself does not translate, the callers do (so the callers can interpolate locale-correctly).
- Uses `ignore_permissions=True` on `.insert()` — the host submit already ran the permission check; the recipient user lacks permission to insert on its own behalf.
- Propagates raises; does not swallow them.

---

## 2. Widened DocType — `Purisol Settings`

### 2.1. JSON change — add one field

**Before** (Phase 5): `field_order` ends with `enable_consumption_warnings`. Fields list ends after that field.

**After** (Phase 6): append one field at the end.

```json
{
  "field_order": [
    "coupon_item",
    "default_price_list",
    "section_break_thresholds",
    "customer_low_stock_threshold",
    "warehouse_low_stock_threshold",
    "section_break_accounts",
    "employee_liability_account",
    "discrepancy_offset_account",
    "default_cash_account",
    "section_break_warnings",
    "enable_consumption_warnings",
    "last_warehouse_low_stock_notified_on"
  ],
  "fields": [
    ...,
    {
      "fieldname": "last_warehouse_low_stock_notified_on",
      "fieldtype": "Date",
      "label": "Last Warehouse Low-Stock Notified On",
      "read_only": 1,
      "hidden": 1
    }
  ]
}
```

| Property | Value |
|----------|-------|
| `fieldname` | `last_warehouse_low_stock_notified_on` |
| `fieldtype` | `Date` |
| `label` | `Last Warehouse Low-Stock Notified On` |
| `read_only` | `1` — only the Phase-6 trigger writes to it via `frappe.db.set_single_value` |
| `hidden` | `1` — internal dedup state, not admin-editable |
| default | (empty) |
| `reqd` | `0` |

No other Purisol Settings field changes. `track_changes = 1` (from Phase 1) automatically captures edits to the new field.

### 2.2. Controller — `purisol_settings.py`

**No code change.** The new field is internal plumbing; no validation required. The existing `PurisolSettings(Document)` class continues to pass.

### 2.3. Test file — `test_purisol_settings.py`

Optionally extend with a trivial assertion that the new field exists and is nullable on a fresh singleton load. Phase 6 does not treat this as blocking.

---

## 3. Widened controller — `Purisol Coupon Discrepancy`

### 3.1. New method — `after_insert`

Add to `purisol_coupon_discrepancy.py`:

```python
def after_insert(self):
    """
    Phase 6: on discrepancy creation, notify Purisol Administrator users.
    Runs after .insert() commits the discrepancy record.  Inside the caller's
    transaction (the consumption entry's on_submit).
    """
    from cx_purisol.cx_purisol.api import notify

    delivery_man = (
        frappe.db.get_value(
            "Purisol Coupon Consumption Entry",
            self.triggering_consumption_entry,
            "delivery_man",
        )
        if self.triggering_consumption_entry
        else None
    )

    notify.send(
        recipient="Purisol Administrator",
        subject=_("Discrepancy {0} opened").format(self.name),
        message=_("Discrepancy {0} opened: {1} in booklet {2}, delivery man {3}.").format(
            self.name,
            _(self.discrepancy_type),
            self.booklet,
            delivery_man or _("(unknown)"),
        ),
        reference_doctype="Purisol Coupon Discrepancy",
        reference_name=self.name,
    )
```

### 3.2. What else changes on the controller

- `before_insert`, `validate`, `before_submit`, `on_submit`, `on_cancel`: **unchanged**.
- DocType JSON: **unchanged**.
- Permissions: **unchanged**.

### 3.3. Transactional shape

The `after_insert` hook runs after `self.insert()` commits the parent + child rows of the discrepancy. The discrepancy insert happens inside `PurisolCouponConsumptionEntry.on_submit` (Phase 5's detection service); the entire stack is inside the consumption-entry submit transaction. A raise from `notify.send` rolls the whole submit back — consumption entry, discrepancy, notification, all together.

### 3.4. Interaction with Phase-5 `seed_open_discrepancy` helper (tests)

The Phase-5 test fixture `seed_open_discrepancy(...)` directly inserts a draft discrepancy, bypassing the detection path. That insert triggers `after_insert` and fires a Phase-6 notification. Phase-6 tests either count deltas (so the pre-existing notification from seeding is absorbed into the baseline) or suppress by running `seed_open_discrepancy` before seeding the administrator user.

---

## 4. Widened controller — `Purisol Coupon Consumption Entry`

### 4.1. Python changes inside existing `on_submit`

Two additive changes inside the existing method. The JSON is unchanged; no validate/before_submit/on_cancel changes.

**Phase-4 depletion block (existing)**:

```python
if triggered_depletion:
    booklet.status = "Depleted"
    booklet.depleted_on = posting_dt
booklet.save(ignore_permissions=True)
if triggered_depletion:
    booklet.add_comment("Info", _("Depleted via {0}").format(self.name))
```

**Widened (Phase 6)** — add one call inside the second `if triggered_depletion:`:

```python
if triggered_depletion:
    booklet.add_comment("Info", _("Depleted via {0}").format(self.name))

    # Phase 6: Booklet Depleted notification
    customer_name = (
        frappe.db.get_value("Customer", booklet.customer, "customer_name")
        if booklet.customer
        else None
    ) or booklet.customer or _("(unknown)")
    notify.send(
        recipient="Purisol Administrator",
        subject=_("Booklet {0} depleted").format(booklet.name),
        message=_("Booklet {0} for customer {1} is fully consumed. Follow up for resale.").format(
            booklet.name, customer_name
        ),
        reference_doctype="Purisol Coupon Booklet",
        reference_name=booklet.name,
    )
```

**After Phase-5 detection block (new pass, at end of `on_submit`)** — add:

```python
# Phase 6: Customer Low Stock evaluation
affected_customers = {
    frappe.db.get_value("Purisol Coupon Booklet", b, "customer")
    for b in booklets
}
affected_customers.discard(None)
affected_customers.discard("")

if affected_customers:
    threshold = frappe.get_doc("Purisol Settings").customer_low_stock_threshold or 0
    for customer in affected_customers:
        total_remaining = frappe.db.sql(
            """
            SELECT COALESCE(SUM(remaining_count), 0)
            FROM `tabPurisol Coupon Booklet`
            WHERE customer = %s AND status = 'Sold'
            """,
            (customer,),
        )[0][0] or 0
        if total_remaining <= threshold:
            customer_name = (
                frappe.db.get_value("Customer", customer, "customer_name") or customer
            )
            notify.send(
                recipient="Purisol Administrator",
                subject=_("Customer {0} low on coupons").format(customer_name),
                message=_("Customer {0} has {1} coupons remaining. Prepare a new booklet.").format(
                    customer_name, int(total_remaining)
                ),
                reference_doctype="Customer",
                reference_name=customer,
            )
```

Import at top: `from cx_purisol.cx_purisol.api import notify`.

### 4.2. Notes on the widening

- **Fresh settings read per submit**: `frappe.get_doc("Purisol Settings")` (not `get_cached_doc`) ensures threshold edits take effect immediately (FR-006).
- **`affected_customers.discard(None)`**: booklets with `status != "Sold"` have `customer = None`; those are Unassigned Booklet cases (Phase 5). Customer Low Stock never fires for unassigned booklets (US2 Acceptance 5).
- **`threshold or 0`**: defensive against a `None` in the DB (`customer_low_stock_threshold` is `reqd = 1` with default 3, so this is belt-and-braces).
- **`total_remaining <= threshold`**: matches FR-005 and US2 Acceptance 1 — fires when the new total is at or below threshold, including exactly equal.
- **Order**: the Customer Low Stock block runs AFTER Phase-5 detection so discrepancies are in the DB first (preserves Story 1 + Story 2 independence per spec edge case "same Consumption Entry triggers both").

### 4.3. Phase-4 state reversal (cancel path)

Phase 6 does NOT widen `on_cancel`. Spec FR-018 explicitly says Phase 6 triggers fire only on initial submit/insert, not on cancel/amend. An administrator who cancels a depleting consumption entry sees the booklet reverted from `Depleted → Sold` (Phase 4's existing logic), but no "un-notification" fires. The previously-delivered Notification Log entry remains in the bell dropdown; administrators dismiss it manually if it is no longer relevant.

---

## 5. Widened module — `cx_purisol/cx_purisol/sales_invoice/sales_invoice_hooks.py`

### 5.1. New function — `check_warehouse_low_stock`

Add to the bottom of the existing module:

```python
def check_warehouse_low_stock(doc, method=None):
    """
    Phase 6: after a Sales Invoice submit, check if in-stock booklet count is below
    threshold; if so, and if no warehouse-low-stock notification has fired today,
    send one bell notification per administrator user.

    Wired as a secondary on_submit hook in hooks.py — runs after mark_booklets_sold.

    Dedup: single Date field on Purisol Settings.last_warehouse_low_stock_notified_on.
    """
    from cx_purisol.cx_purisol.api import notify

    settings = frappe.get_doc("Purisol Settings")
    threshold = settings.warehouse_low_stock_threshold or 0

    in_stock_count = frappe.db.count("Purisol Coupon Booklet", {"status": "In Stock"})

    if in_stock_count >= threshold:
        return  # FR-007: strict inequality

    today = frappe.utils.today()
    if settings.last_warehouse_low_stock_notified_on == today:
        return  # FR-008: already fired today

    notify.send(
        recipient="Purisol Administrator",
        subject=_("Warehouse low on booklet stock"),
        message=_("Only {0} booklets remain in stock. Generate a new batch.").format(
            int(in_stock_count)
        ),
        reference_doctype="Purisol Coupon Booklet",
        reference_name=None,
    )

    frappe.db.set_single_value("Purisol Settings", "last_warehouse_low_stock_notified_on", today)
```

### 5.2. Existing functions — unchanged

- `validate_booklet_lines` — unchanged
- `mark_booklets_sold` — unchanged
- `reverse_booklets_sale` — unchanged
- `guard_trash` — unchanged

### 5.3. Import changes

Add at top:

```python
from frappe import _  # already imported in Phase 3; present already
```

No new top-level imports required (notify is imported inside the function to keep module load light).

---

## 6. Wiring — `hooks.py`

### 6.1. `doc_events` change

**Before** (Phase 5):

```python
doc_events = {
    "Sales Invoice": {
        "validate": "cx_purisol.cx_purisol.sales_invoice.sales_invoice_hooks.validate_booklet_lines",
        "on_submit": "cx_purisol.cx_purisol.sales_invoice.sales_invoice_hooks.mark_booklets_sold",
        "on_cancel": "cx_purisol.cx_purisol.sales_invoice.sales_invoice_hooks.reverse_booklets_sale",
        "on_trash": "cx_purisol.cx_purisol.sales_invoice.sales_invoice_hooks.guard_trash",
    }
}
```

**After** (Phase 6) — `on_submit` becomes a list:

```python
doc_events = {
    "Sales Invoice": {
        "validate": "cx_purisol.cx_purisol.sales_invoice.sales_invoice_hooks.validate_booklet_lines",
        "on_submit": [
            "cx_purisol.cx_purisol.sales_invoice.sales_invoice_hooks.mark_booklets_sold",
            "cx_purisol.cx_purisol.sales_invoice.sales_invoice_hooks.check_warehouse_low_stock",
        ],
        "on_cancel": "cx_purisol.cx_purisol.sales_invoice.sales_invoice_hooks.reverse_booklets_sale",
        "on_trash": "cx_purisol.cx_purisol.sales_invoice.sales_invoice_hooks.guard_trash",
    }
}
```

Frappe natively supports list-form `doc_events` values and executes them in list order. `mark_booklets_sold` runs first so that booklet statuses flip to `Sold` before the warehouse-in-stock count is recomputed by the Phase-6 handler.

### 6.2. No other `hooks.py` change

- `doctype_js` — unchanged.
- `doctype_list_js` — unchanged.
- `fixtures` — unchanged.
- `before_tests` — unchanged.

---

## 7. Patch — `cx_purisol/patches/v0_6_0/add_warehouse_low_stock_dedup_field.py`

```python
import frappe


def execute():
    print(
        "cx_purisol.patches.v0_6_0.add_warehouse_low_stock_dedup_field: "
        "no-op anchor for Phase 6 (field landed via JSON migrate)"
    )
```

`patches.txt` extended:

```
cx_purisol.patches.v0_6_0.add_warehouse_low_stock_dedup_field
```

(appended as the next post-model-sync entry).

---

## 8. Relationships diagram

```
         Purisol Coupon Consumption Entry  (Phase 4; widened in Phase 6)
          ├── (Phase 4 + 5 fields unchanged ...)
          ├── on_submit
          │      ├── (Phase 4: flip coupons, update booklet aggregates, auto-deplete)
          │      │       └── if triggered_depletion:
          │      │              └── notify.send("Purisol Administrator",
          │      │                    subject="Booklet {0} depleted",
          │      │                    body="Booklet {0} for customer {1} is fully consumed.",
          │      │                    ref → Purisol Coupon Booklet:{booklet.name})    ← Story 4
          │      ├── (Phase 5: detect_for_entry; Purisol Coupon Discrepancy.after_insert
          │      │              fires per discrepancy, which notify.sends per discrepancy) ← Story 1
          │      └── (Phase 6: for each unique customer, evaluate low-stock, notify.send) ← Story 2
          │
          └── on_cancel  (unchanged — no Phase-6 trigger)


         Purisol Coupon Discrepancy  (Phase 5; widened with after_insert in Phase 6)
          ├── after_insert  ← NEW in Phase 6
          │      └── notify.send("Purisol Administrator",
          │            subject="Discrepancy {0} opened",
          │            body="Discrepancy {0} opened: {1} in booklet {2}, delivery man {3}.",
          │            ref → Purisol Coupon Discrepancy:{self.name})              ← Story 1
          └── (all other hooks unchanged)


         Sales Invoice  (ERPNext core; Phase 3 + Phase 6 hooks)
          ├── validate     → validate_booklet_lines (Phase 3)
          ├── on_submit    → [mark_booklets_sold (Phase 3),
          │                   check_warehouse_low_stock (Phase 6)]                ← Story 3
          ├── on_cancel    → reverse_booklets_sale (Phase 3)
          └── on_trash     → guard_trash (Phase 3)


         Purisol Settings  (Phase 1; widened with one field in Phase 6)
          ├── (existing Phase-1/5 fields: thresholds, accounts, enable_consumption_warnings)
          └── last_warehouse_low_stock_notified_on  ← NEW in Phase 6
                   (Date, read-only, hidden; Phase-6 dedup marker)


         ERPNext Notification Log  (framework-owned; all four triggers create records here)
          ├── type           = "Alert"
          ├── subject        = <localized, short, per-trigger>
          ├── email_content  = <localized, plain-text body>
          ├── for_user       = <individual User>
          ├── document_type  = <target doctype>
          ├── document_name  = <target record or None>
          └── from_user      = None  (system-generated)


         cx_purisol.cx_purisol.api.notify  (NEW module)
          ├── send(recipient, subject, message, reference_doctype, reference_name) -> list[str]
          ├── _resolve_recipients(recipient) -> list[str]   (role/user expansion, filters disabled)
          └── _emit_bell(for_user, subject, message, ...)    (inserts one Notification Log)
```

---

## 9. Validations in one place

### 9.1. `Purisol Notify.send()` — input handling

| # | Rule | On violation |
|---|------|--------------|
| V1 | `recipient` is a string | `TypeError` (programming error — not expected at runtime) |
| V2 | `subject` and `message` are non-empty strings | `ValueError` (programming error — callers always supply both) |
| V3 | `reference_doctype` is `None` or a string | — |
| V4 | `reference_name` is `None` or a string | — |
| V5 | Unknown role / unknown user / all-disabled role | Silent no-op (FR-014) |

The utility does not validate that `reference_doctype` names a real DocType — that is Frappe's job when rendering the bell-icon click-through.

### 9.2. `PurisolCouponDiscrepancy.after_insert` — rules

| # | Rule | On violation |
|---|------|--------------|
| AI1 | `self.triggering_consumption_entry` exists and resolves to a real Consumption Entry | Fallback: interpolate `_("(unknown)")` in the body; no raise |
| AI2 | `notify.send` raises infrastructure error | Propagates — the consumption entry submit rolls back |

### 9.3. `PurisolCouponConsumptionEntry.on_submit` widening — rules

| # | Rule | On violation |
|---|------|--------------|
| W1 | Booklet depletion block: `notify.send` fires iff `triggered_depletion == True` after the booklet `.save()` succeeds | — |
| W2 | Customer Low Stock block: fires for each customer where total remaining ≤ threshold | — |
| W3 | Customer Low Stock threshold read from `frappe.get_doc("Purisol Settings")` freshly each submit | — |
| W4 | Unassigned Booklet cases (customer=None) excluded from Customer Low Stock evaluation | — |

### 9.4. `check_warehouse_low_stock` — rules

| # | Rule | On violation |
|---|------|--------------|
| WH1 | `in_stock_count < threshold` (strict) | Return; no notification |
| WH2 | `settings.last_warehouse_low_stock_notified_on == today` | Return; no notification (dedup) |
| WH3 | Dedup marker updated iff notification was sent | — |
| WH4 | Dedup marker write uses `frappe.db.set_single_value` (keeps inside transaction) | — |

---

## 10. Fixtures / migrations

### 10.1. Fixtures

**No new fixtures.** The `Purisol Administrator` role already exists (Phase 0 constitution / setup). The `fixtures` list in `hooks.py` is unchanged.

### 10.2. `patches.txt`

Add one post-model-sync entry:

```
cx_purisol.patches.v0_6_0.add_warehouse_low_stock_dedup_field
```

No-op anchor, matches Phases 2/3/4/5 pattern.

### 10.3. `hooks.py` changes

`doc_events["Sales Invoice"]["on_submit"]` becomes a 2-element list (see §6.1).

No other `hooks.py` changes.

### 10.4. Translations

Append to `cx_purisol/translations/ar.csv` — 8 new strings (4 subject templates + 4 body templates), plus any fallback phrases (`(unknown)`) introduced in this phase. See research.md §12 for the table.

---

## 11. What is deliberately NOT changed

- **No change** to `purisol_coupon.json`, `purisol_coupon_booklet.json`, `purisol_custody_entry*.json`, `purisol_coupon_consumption_entry.json`, `purisol_coupon_consumption_item.json`, `purisol_coupon_discrepancy.json`, `purisol_coupon_discrepancy_coupon.json`, `purisol_coupon_discrepancy_related_person.json`, `purisol_coupon_discrepancy_item.json`. The only DocType JSON touched is `purisol_settings.json` (one additive field).
- **No new role.** `Purisol Administrator` covers every Phase-6 recipient.
- **No new custom field fixture.** Phase 3's `Sales Invoice Item.purisol_booklet` is unrelated to Phase 6.
- **No new whitelisted API.** The utility is server-side only.
- **No client-side JS.** Zero files under `public/js/` or colocated `.js` files are added. The bell icon is rendered by ERPNext core.
- **No new workspace.** Notifications appear in the existing bell icon; no Purisol workspace widget is added.
- **No new `Notification` DocType records.** Phase 6 writes directly to `Notification Log`.
- **No changes to Phase 3's `sales_invoice_hooks.mark_booklets_sold`.** The Phase-6 handler is a sibling, not a rewrite.
- **No changes to `Purisol Coupon Consumption Entry.validate` or `.on_cancel`.** Widening is limited to two additive blocks inside `on_submit`.
- **No changes to `Purisol Coupon Discrepancy.validate`, `.before_submit`, `.on_cancel`.** Widening adds one new method: `after_insert`.
- **No background jobs.** All trigger work is synchronous (constitution VIII — well under 100-record threshold).
