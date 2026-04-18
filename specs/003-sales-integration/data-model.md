# Phase 1 Data Model — Sales Integration

**Feature**: 003-sales-integration | **Date**: 2026-04-18

Phase 3 introduces **zero** new DocTypes and **zero** new fields on existing Purisol DocTypes. The schema work for this phase consists of:

1. One `Custom Field` on the standard ERPNext `Sales Invoice Item` DocType.
2. In-code activation of fields already declared on `Purisol Coupon Booklet` (from Phase 1) and on `Purisol Settings` (from Phase 1).
3. Widening of the `Purisol Coupon Booklet` controller's state-machine guard.

This document enumerates each, records the state-transition rules, and lists validations in one place for the implementer.

---

## 1. New schema element: `Sales Invoice Item.purisol_booklet`

**Type**: `Custom Field` (Frappe fixture)
**Parent DocType**: `Sales Invoice Item` (ERPNext core, child table of `Sales Invoice`)
**Field definition**:

| Attribute | Value |
|-----------|-------|
| `fieldname` | `purisol_booklet` |
| `label` | `Purisol Booklet` (wrapped in `_()` at render time via Frappe's Custom Field label translation) |
| `fieldtype` | `Link` |
| `options` | `Purisol Coupon Booklet` |
| `insert_after` | `item_code` |
| `in_list_view` | `1` |
| `depends_on` | `eval:doc.item_code && (doc.item_code == frappe.defaults.get_default("purisol_coupon_item_code"))` — see note below |
| `read_only_depends_on` | `eval:doc.parent && doc.docstatus==1` |
| `no_copy` | `1` (a booklet can be sold at most once; amending an invoice starts with empty booklet refs on new lines) |
| `allow_on_submit` | `0` |
| `permlevel` | `0` |
| `translatable` | `0` (field stores an ID, not localised text) |

**Note on `depends_on`**: Using a `frappe.defaults` key avoids re-querying `Purisol Settings` on every item-row render. The key is populated by a small client-script helper on Sales Invoice form load (`frappe.call("cx_purisol.api.sell_booklets.get_coupon_item_code")`) and cached. The server never relies on this default — it's purely a UI affordance to hide the field on non-booklet lines. Server logic gates on actual equality between `line.item_code` and `Purisol Settings.coupon_item`.

**Rationale for placement**: `Sales Invoice Item` is the row-level anchor. A `Link` fieldtype gives integrity, navigation, and report-column support. `in_list_view = 1` makes the booklet visible in the item grid. `read_only_depends_on` ensures the link cannot be changed on a submitted invoice. `no_copy = 1` prevents amendment/copy from auto-duplicating a reference that must point to a fresh booklet transition.

**Fixture location**: `cx_purisol/cx_purisol/fixtures/custom_field.json` (new file). Registered via `hooks.fixtures`:

```python
fixtures = [
    {"dt": "Role", "filters": [["name", "in", ["Purisol Administrator"]]]},
    {"dt": "Custom Field", "filters": [["name", "in", ["Sales Invoice Item-purisol_booklet"]]]},
]
```

---

## 2. Fields activated on existing DocTypes (no schema change)

### 2.1. `Purisol Settings` (from Phase 1)

Two fields already defined in Phase 1's `purisol_settings.json` are activated by Phase 3 — meaning they become *required for operation* when a sale is attempted, though the underlying DocType does not mark them `reqd = 1` (the singleton can exist with them unset; only the sales workflow refuses to start).

| Field | Type | Phase 3 semantics |
|-------|------|-------------------|
| `coupon_item` | `Link → Item` | **Required for any sale.** The workflow refuses to start if unset (FR-003). On `Sales Invoice` validate, the invoice lines whose `item_code == Purisol Settings.coupon_item` are the ones subject to Phase 3 logic (FR-020). |
| `default_price_list` | `Link → Price List` | **Fallback** when no other Price List is resolved for a sale (FR-002, FR-013). If unset and neither the workflow nor the Customer supplies one, the workflow raises (research.md §3). |

No JSON change required — both fields are already in `purisol_settings.json` from Phase 1.

### 2.2. `Purisol Coupon Booklet` (from Phase 1)

Four fields already defined in Phase 1 are activated by Phase 3:

| Field | Type | Phase 3 write rule |
|-------|------|--------------------|
| `customer` | `Link → Customer` | Written on `Sales Invoice.on_submit` (`= invoice.customer`); cleared on safe `Sales Invoice.on_cancel`. |
| `sold_on` | `Datetime` | Written on `on_submit` (`= invoice.posting_date` combined with `invoice.posting_time`; single datetime value); cleared on cancel. |
| `sales_invoice` | `Link → Sales Invoice` | Written on `on_submit` (`= invoice.name`); cleared on cancel. |
| `current_delivery_man` | `Link → Employee` | **Cleared** on `on_submit` (custody ends at sale, FR-024). **Not restored** on cancel (FR-032 — restoring custody requires an explicit Custody Entry). |

Plus one status-domain change (see §3 below): `status` gains `Sold` as a reachable value.

No JSON change required — all four fields plus the `status` options list (`In Stock\nIn Custody\nSold\nDepleted`) already exist from Phase 1.

### 2.3. `Purisol Coupon` (from Phase 1)

Phase 3 reads but never writes `Purisol Coupon.status`. Specifically, `Sales Invoice.on_cancel` counts coupons with `status == "Consumed"` for each referenced booklet to enforce the cancellation-blocked-by-consumption rule (FR-031).

No schema change; no JSON change.

---

## 3. State machine changes on `Purisol Coupon Booklet`

### 3.1. States reachable after Phase 3

| State | Reachable? | Entered by | Left by |
|-------|-----------|-----------|---------|
| `In Stock` | Yes (initial) | Booklet creation (Phase 1); `Sales Invoice.on_cancel` safe reversal (Phase 3) | `Purisol Custody Entry` submit (Assign); `Sales Invoice.on_submit` (sale) |
| `In Custody` | Yes | `Purisol Custody Entry` submit (Assign / Transfer) | `Purisol Custody Entry` submit (Return); `Sales Invoice.on_submit` (sale) |
| `Sold` | **New in Phase 3** | `Sales Invoice.on_submit` (submit of a booklet-bearing invoice) | `Sales Invoice.on_cancel` (safe reversal, no consumption) |
| `Depleted` | Not reachable yet (Phase 4) | — | — (terminal) |

### 3.2. Allowed transitions after Phase 3

```
In Stock    ─┬─→ In Custody        (Custody Entry Assign — Phase 2)
             ├─→ Sold               (Sales Invoice submit — Phase 3)
             └─← Sold               (Sales Invoice cancel, no consumption — Phase 3)

In Custody  ─┬─→ In Stock           (Custody Entry Return — Phase 2)
             └─→ Sold               (Sales Invoice submit — Phase 3)

Sold        ─── In Stock            (Sales Invoice cancel, no consumption — Phase 3)
             (no other exit; cancel with any consumption → rejected, stays Sold)

Depleted    ─── (unreachable in this phase; remains terminal once Phase 4 ships)
```

### 3.3. Controller constants (widened)

In `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/purisol_coupon_booklet.py`:

```python
# Phase 1:         {"In Stock"}
# Phase 2 widened: {"In Stock", "In Custody"}
# Phase 3 widens to:
_ALLOWED_STATUSES = {"In Stock", "In Custody", "Sold"}

# Phase 2 had:
#   {("In Stock", "In Custody"), ("In Custody", "In Stock")}
# Phase 3 adds:
_ALLOWED_TRANSITIONS = {
    ("In Stock",   "In Custody"),
    ("In Custody", "In Stock"),
    ("In Stock",   "Sold"),       # NEW — direct sale from shop
    ("In Custody", "Sold"),       # NEW — sale from a delivery man's hands
    ("Sold",       "In Stock"),   # NEW — safe cancel reversal
}
```

### 3.4. Migration: patches.txt entry

Patch `cx_purisol.patches.v0_3_0.widen_booklet_validate_for_sale` is added to `patches.txt` (post-model-sync). It is a no-op (logging only) on fresh installs; on upgraded sites it serves as a durable anchor for future troubleshooting ("this site was migrated through Phase 3"). Mirrors the Phase-2 pattern.

---

## 4. Validations in one place

### 4.1. Pre-invoice-creation (workflow entry point)

Function: `cx_purisol.api.sell_booklets.purisol_create_sales_invoice_for_booklets`

| # | Rule | On violation |
|---|------|--------------|
| W1 | Caller must hold `Purisol Administrator` role | `frappe.PermissionError` (via `frappe.only_for`) |
| W2 | `Purisol Settings.coupon_item` must be set | `frappe.throw(_("Configure coupon_item in Purisol Settings before selling."))` |
| W3 | `customer` argument non-empty and exists in `Customer` | `frappe.throw(_("Customer is required."))` / Frappe link-integrity error |
| W4 | `booklets` argument non-empty | `frappe.throw(_("Select at least one booklet to sell."))` (FR-016) |
| W5 | No duplicates in `booklets` list | `frappe.throw(_("Booklet {0} selected more than once.").format(name))` (FR-016) |
| W6 | Every booklet exists and has `status ∈ {In Stock, In Custody}` | `frappe.throw(_("Booklet {0} cannot be sold — status is {1}."))` (FR-012) |
| W7 | `_resolve_price_list` returns a non-empty Price List | `frappe.throw(_("No Price List could be resolved..."))` (research.md §3) |

### 4.2. Pre-invoice-submit (`Sales Invoice.validate` hook)

Function: `cx_purisol.sales_invoice.sales_invoice_hooks.validate_booklet_lines`. Only applies to lines where `item_code == Purisol Settings.coupon_item` AND `purisol_booklet` is set. All-or-nothing — any violation below aborts the whole save/submit.

| # | Rule | On violation |
|---|------|--------------|
| V1 | Each `purisol_booklet` link resolves to an existing booklet | `frappe.throw(_("Booklet {0} does not exist — broken reference."))` (FR-023) |
| V2 | Each booklet's current `status ∈ {In Stock, In Custody}` | `frappe.throw(_("Booklet {0} cannot be sold — current status: {1}."))` (FR-021) |
| V3 | No booklet appears in more than one line | `frappe.throw(_("Booklet {0} appears on more than one line of this invoice."))` (FR-022) |
| V4 | Line quantity == 1 on every booklet-bearing line | `frappe.throw(_("Booklet lines must have quantity 1."))` (implied by FR-014) |

### 4.3. Invoice-submit (`Sales Invoice.on_submit` hook)

Function: `cx_purisol.sales_invoice.sales_invoice_hooks.mark_booklets_sold`. Runs only after `validate_booklet_lines` has passed — no re-validation needed here. Writes per booklet:

```
booklet.status                = "Sold"
booklet.customer              = invoice.customer
booklet.sold_on               = combine(invoice.posting_date, invoice.posting_time)
booklet.sales_invoice         = invoice.name
booklet.current_delivery_man  = NULL
```

Plus one `Comment` on the booklet: `_("Sold via {0}").format(invoice.name)` (research.md §10).

### 4.4. Invoice-cancel (`Sales Invoice.on_cancel` hook)

Function: `cx_purisol.sales_invoice.sales_invoice_hooks.reverse_booklets_sale`.

| # | Rule | On violation |
|---|------|--------------|
| C1 | For every referenced booklet, `frappe.db.count("Purisol Coupon", {booklet, status: "Consumed"}) == 0` | Collect all blocking booklet names; `frappe.throw(_("Cannot cancel — coupons have been consumed on: {0}").format(", ".join(names)))` (FR-031) |

If C1 passes for every referenced booklet, then per booklet:

```
booklet.status         = "In Stock"
booklet.customer       = NULL
booklet.sold_on        = NULL
booklet.sales_invoice  = NULL
# booklet.current_delivery_man intentionally NOT restored (FR-032)
```

Plus one `Comment`: `_("Sale reversed — invoice {0} cancelled.").format(invoice.name)`.

### 4.5. Invoice-trash defence (`Sales Invoice.on_trash` hook)

Function: `cx_purisol.sales_invoice.sales_invoice_hooks.guard_trash`. Frappe already blocks deletion of submitted documents; this hook adds a belt-and-braces check for the edge case where a submitted invoice is un-submitted and then deleted:

| # | Rule | On violation |
|---|------|--------------|
| T1 | If any referenced booklet currently has `sales_invoice == invoice.name`, refuse delete | `frappe.throw(_("Cannot delete — booklets still reference this invoice. Cancel the invoice first."))` |

---

## 5. Relationships diagram

```
                                    Purisol Settings (singleton)
                                          │
                                          ├──→ Item          (coupon_item, Link)
                                          └──→ Price List    (default_price_list, Link)

         Sales Invoice (ERPNext)
          │    │
          │    └── items (child: Sales Invoice Item)
          │                │
          │                ├── item_code        → Item
          │                └── purisol_booklet  → Purisol Coupon Booklet   ← NEW Custom Field
          │
          ├── customer  → Customer
          └── selling_price_list → Price List

         Purisol Coupon Booklet
          ├── customer               → Customer          (populated on sale)
          ├── sales_invoice          → Sales Invoice     (populated on sale)
          ├── current_delivery_man   → Employee          (cleared on sale)
          ├── sold_on                : Datetime          (populated on sale)
          └── status                 : Select            (In Stock | In Custody | Sold | Depleted)
                 │
                 └── coupons (1:N) → Purisol Coupon.status  ← read on cancel for consumption check
```

---

## 6. What is deliberately NOT changed

- **No new DocType.** The spec and constitution both forbid a parallel sale DocType.
- **No coupon writes.** `Purisol Coupon.status`, `consumed_count`, `remaining_count` — all untouched by Phase 3. Sale and cancel do not move coupons between `Available` and `Consumed`.
- **No new role.** Constitution VI — only `Purisol Administrator` — holds.
- **No new Report.** "Current Custody by Delivery Man" (Phase 2) remains the only Purisol-owned report. Sales reporting is covered by ERPNext's standard Sales Invoice reports, which already see the new invoices.
- **No notification emission.** Phase 5/6 will handle customer-low-stock and other event-driven alerts.
- **No new fixtures** beyond the one `Custom Field` and the one `patches.txt` entry.
