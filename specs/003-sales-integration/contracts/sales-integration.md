# Sales Integration — Behavioural Contracts

**Feature**: 003-sales-integration | **Date**: 2026-04-18

Phase 3 exposes one whitelisted Python API and three `Sales Invoice` document-event hooks. This document is the authoritative contract for each: signature, preconditions, postconditions, side effects, and error modes. Tests assert against these contracts.

---

## 1. `purisol_create_sales_invoice_for_booklets` (whitelisted API)

### 1.1. Location

`cx_purisol.api.sell_booklets.purisol_create_sales_invoice_for_booklets`

### 1.2. Signature

```python
@frappe.whitelist()
def purisol_create_sales_invoice_for_booklets(
    customer: str,
    booklets: list[str] | str,   # JSON string from JS client, or Python list from tests
    price_list: str | None = None,
) -> dict:
    """Create a draft Sales Invoice for the given booklets.

    Returns {"name": "<sales-invoice-name>"} on success.
    """
```

### 1.3. Preconditions (raise `frappe.throw` or `frappe.PermissionError`)

| # | Condition | Error (translated) |
|---|-----------|---------------------|
| P1 | Caller has `Purisol Administrator` role | `frappe.PermissionError` (via `frappe.only_for`) |
| P2 | `Purisol Settings.coupon_item` is set | `"Configure coupon_item in Purisol Settings before selling."` |
| P3 | `customer` is a non-empty string naming an existing `Customer` | `"Customer is required."` / Frappe link-integrity error |
| P4 | `booklets` parses to a non-empty list | `"Select at least one booklet to sell."` |
| P5 | `booklets` contains no duplicates | `"Booklet {0} selected more than once."` |
| P6 | Each booklet exists and has `status ∈ {In Stock, In Custody}` | `"Booklet {0} cannot be sold — status is {1}."` |
| P7 | A Price List can be resolved (workflow → customer → Settings) | `"No Price List could be resolved for this sale. Configure a default_price_list in Purisol Settings or pick one on the workflow."` |

### 1.4. Postconditions (on success)

- Exactly one `Sales Invoice` exists with:
  - `docstatus = 0` (draft; **never** auto-submitted — FR-015).
  - `customer = <arg>`.
  - `selling_price_list = <resolved price list>`.
  - `len(items) == len(booklets)`, with each line carrying:
    - `item_code = Purisol Settings.coupon_item`
    - `qty = 1`
    - `rate` populated by standard ERPNext Price List lookup (no custom rate math)
    - `purisol_booklet = <booklet name>` (Custom Field)
- Returned dict: `{"name": "<the invoice's name>"}`.
- **Booklet state is unchanged** — no status transition happens at draft creation; status flips only on invoice submit (P6-style checks also run at submit time, see §2).

### 1.5. Side effects

- One `Sales Invoice` inserted.
- Standard Frappe version/comment tracking on that invoice.
- No booklet record modified.
- No other records modified.

### 1.6. Idempotency

Not idempotent: every call creates a new draft. Callers are responsible for not re-invoking the API on the same selection (the UI dialog dismisses after success).

### 1.7. Concurrency

Two concurrent calls that share no booklets: both succeed, produce two independent drafts.
Two concurrent calls that share at least one booklet: both succeed at draft creation (no booklet state is written yet). The conflict surfaces only at submit time (see §2.4).

---

## 2. `Sales Invoice.validate` hook — `validate_booklet_lines`

### 2.1. Location

`cx_purisol.sales_invoice.sales_invoice_hooks.validate_booklet_lines`

Registered in `hooks.py`:
```python
doc_events = {
    "Sales Invoice": {
        "validate": "cx_purisol.sales_invoice.sales_invoice_hooks.validate_booklet_lines",
        ...
    },
}
```

### 2.2. Trigger

Called on every `Sales Invoice.save()` — draft save, resave, and submit all funnel through `validate`. Short-circuits immediately (returns without raising) if no line carries `purisol_booklet`.

### 2.3. Preconditions checked (per booklet-bearing line)

| # | Condition | Error (translated) |
|---|-----------|---------------------|
| V1 | `line.purisol_booklet` is set AND resolves to an existing `Purisol Coupon Booklet` | `"Booklet {0} does not exist — broken reference."` |
| V2 | `line.item_code == Purisol Settings.coupon_item` (lines with `purisol_booklet` but a different `item_code` are rejected to prevent smuggling booklets into non-coupon lines) | `"Booklet {0} cannot be sold under item_code {1}."` |
| V3 | Current booklet status ∈ `{In Stock, In Custody}` | `"Booklet {0} cannot be sold — current status: {1}."` |
| V4 | No booklet appears on more than one line | `"Booklet {0} appears on more than one line of this invoice."` |
| V5 | `line.qty == 1` | `"Booklet lines must have quantity 1."` |

### 2.4. Postconditions

- If no violation: function returns; Frappe proceeds with save.
- If any violation: `frappe.ValidationError` raised; Frappe aborts save, nothing is written.

### 2.5. Side effects

None on booklets (validate is read-only from Purisol's side).

---

## 3. `Sales Invoice.on_submit` hook — `mark_booklets_sold`

### 3.1. Location

`cx_purisol.sales_invoice.sales_invoice_hooks.mark_booklets_sold`

### 3.2. Trigger

Called once when the user (or amendment flow) submits the invoice. Runs inside the submit transaction, after Frappe has set `docstatus = 1` and before the transaction commits. Short-circuits if no line has `purisol_booklet`.

### 3.3. Preconditions

- All `validate_booklet_lines` preconditions hold (validate runs first in the same transaction).
- `Purisol Settings.coupon_item` is set (re-checked as a safety net).

### 3.4. Postconditions (atomic, all-or-nothing)

For each booklet-bearing line, the referenced booklet is updated with:

| Field | New value |
|-------|-----------|
| `status` | `"Sold"` |
| `customer` | `invoice.customer` |
| `sold_on` | `combine(invoice.posting_date, invoice.posting_time)` (single `Datetime`) |
| `sales_invoice` | `invoice.name` |
| `current_delivery_man` | `None` (cleared) |

Plus one `Comment` on each booklet: `"Sold via {invoice.name}"` (translated).

### 3.5. Side effects

- Up to `N` `frappe.db` writes on `Purisol Coupon Booklet` (where `N` = booklet-bearing lines on the invoice, typically 1–10; max 10 in Phase 3).
- Up to `N` `tabVersion` entries (from `track_changes = 1`).
- Up to `N` `Comment` records.
- **No coupon records** (`Purisol Coupon`) are modified.
- **No notifications emitted** — Phase 5/6 concern.

### 3.6. Atomicity

All writes happen inside the Frappe request transaction. Any `frappe.throw` unwinds the whole transaction, including Frappe's own `docstatus = 1` flip and any accounting side effects. Administrator observes: either the submit fully succeeded (invoice is submitted AND every booklet is `Sold`) or the submit fully failed (invoice remains draft, booklets unchanged).

### 3.7. Concurrency

Frappe's optimistic-locking check on `Purisol Coupon Booklet.modified` serializes concurrent submits on the same booklet. Loser receives `frappe.TimestampMismatchError`, which Frappe surfaces to the user as a retry-able error. Winner's submit completes normally.

---

## 4. `Sales Invoice.on_cancel` hook — `reverse_booklets_sale`

### 4.1. Location

`cx_purisol.sales_invoice.sales_invoice_hooks.reverse_booklets_sale`

### 4.2. Trigger

Called once when the user (or amendment flow) cancels a submitted invoice. Runs inside the cancel transaction. Short-circuits if no line has `purisol_booklet`.

### 4.3. Preconditions (all-or-nothing across the invoice)

| # | Condition | Error (translated) |
|---|-----------|---------------------|
| C1 | For every booklet referenced by the invoice, `frappe.db.count("Purisol Coupon", {"booklet": B, "status": "Consumed"}) == 0` | Collect all offending booklet names; raise one error: `"Cannot cancel — coupons have been consumed on: {comma-separated-names}. The only correction path is a financial adjustment (outside Phase 3 scope)."` |

The error message names **all** offending booklets, not just the first — so the Administrator sees the complete blocker list in one read.

### 4.4. Postconditions (only when C1 passes)

For each booklet-bearing line, the referenced booklet is updated with:

| Field | New value |
|-------|-----------|
| `status` | `"In Stock"` |
| `customer` | `None` |
| `sold_on` | `None` |
| `sales_invoice` | `None` |
| `current_delivery_man` | *unchanged* (remains `None` — cancel does NOT restore prior custody, FR-032) |

Plus one `Comment` on each booklet: `"Sale reversed — invoice {invoice.name} cancelled."`.

### 4.5. Side effects

- Up to `N` reads on `Purisol Coupon` (one `COUNT(*)` per booklet, to check consumption).
- Up to `N` writes on `Purisol Coupon Booklet` (only when C1 passes for all).
- Up to `N` `tabVersion` entries and `N` `Comment` records.
- No coupon records modified.

### 4.6. Atomicity

Same as `on_submit`. Any `frappe.throw` (including the C1 rejection) unwinds the entire cancel transaction — the invoice remains submitted and booklets remain `Sold`.

---

## 5. `Sales Invoice.on_trash` hook — `guard_trash`

### 5.1. Location

`cx_purisol.sales_invoice.sales_invoice_hooks.guard_trash`

### 5.2. Trigger

Called on delete attempts (which Frappe itself normally blocks for submitted docs, but we defend against edge cases like un-submit-then-delete).

### 5.3. Preconditions

| # | Condition | Error (translated) |
|---|-----------|---------------------|
| T1 | No `Purisol Coupon Booklet` still has `sales_invoice == invoice.name` | `"Cannot delete — booklets still reference this invoice. Cancel the invoice first."` |

### 5.4. Postconditions

None (pure guard — success = the function returns and Frappe proceeds with delete).

---

## 6. List-view action: "Sell Selected to Customer"

### 6.1. Location

`cx_purisol/cx_purisol/public/js/purisol_coupon_booklet_list.js`, registered via `hooks.py`:

```python
doctype_list_js = {"Purisol Coupon Booklet": "public/js/purisol_coupon_booklet_list.js"}
```

### 6.2. Visibility

- Visible only when `frappe.user.has_role("Purisol Administrator")`.
- Enabled only when all selected rows have `status ∈ {In Stock, In Custody}`. If any selected row has `status ∈ {Sold, Depleted}`, the action is greyed out with a tooltip explaining why.

### 6.3. Behaviour

1. Administrator selects one or more booklet rows in the list view.
2. Clicks "Sell Selected to Customer" in the bulk-action menu.
3. Dialog opens (`frappe.prompt`) with:
   - **Customer** (Link, required).
   - **Price List** (Link, optional). Placeholder text: `"Leave blank to use Customer default or Settings default."`.
   - Read-only summary of selected booklet names (for confirmation).
4. On submit of the dialog:
   - Calls `frappe.call("cx_purisol.api.sell_booklets.purisol_create_sales_invoice_for_booklets", {customer, booklets, price_list})`.
   - On success: `frappe.set_route("Form", "Sales Invoice", r.message.name)` — navigates to the draft (FR-015).
   - On error: dialog stays open; error is displayed via Frappe's standard error surface (`frappe.msgprint`).

### 6.4. What the action does **not** do

- Does not submit the invoice — submit is an explicit user action on the Sales Invoice form.
- Does not modify the booklet's status or any Purisol record. All side effects happen in `on_submit` (see §3).
- Does not check `Purisol Settings.coupon_item` on the client — server raises P2 and the dialog surfaces the error. The client could pre-check as a UX improvement but isn't authoritative.

---

## 7. Error surface summary

| Scenario | Where detected | Error |
|----------|----------------|-------|
| coupon_item not configured | Workflow entry point | P2 |
| Customer missing | Workflow entry point | P3 |
| Empty booklet list | Workflow entry point | P4 |
| Duplicate booklet in selection | Workflow entry point | P5 |
| Booklet status wrong at workflow | Workflow entry point | P6 |
| No Price List resolvable | Workflow entry point | P7 |
| Booklet link broken at submit | `validate_booklet_lines` | V1 |
| Booklet used under wrong item_code | `validate_booklet_lines` | V2 |
| Booklet status changed since draft | `validate_booklet_lines` | V3 |
| Duplicate booklet on invoice | `validate_booklet_lines` | V4 |
| Booklet-line qty ≠ 1 | `validate_booklet_lines` | V5 |
| Consumption blocks cancel | `reverse_booklets_sale` | C1 |
| Delete of referencing invoice | `guard_trash` | T1 |
| Non-Administrator invokes API | Workflow entry point | P1 (PermissionError) |
| Concurrent submits | Booklet optimistic lock | `frappe.TimestampMismatchError` |
| Price List missing `coupon_item` entry | Standard ERPNext rate lookup | ERPNext core error (translated) |

Every error message is wrapped in `_()` and uses named placeholders — Arabic renderings preserve correct word order.
