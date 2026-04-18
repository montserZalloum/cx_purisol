# Phase 0 Research — Sales Integration

**Feature**: 003-sales-integration | **Date**: 2026-04-18

This document resolves every open question in the feature spec and plan Technical Context. Each section follows the format: **Decision** (what was chosen), **Rationale** (why), **Alternatives considered** (what else evaluated and why rejected).

---

## 1. How to link a Sales Invoice line back to a specific booklet

**Decision**: Add a `Custom Field` to the **`Sales Invoice Item`** DocType with `fieldname = "purisol_booklet"`, `fieldtype = "Link"`, `options = "Purisol Coupon Booklet"`. Ship it as a Frappe fixture (`Custom Field` DocType with `dt = "Sales Invoice Item"`), registered via `hooks.fixtures`. The field is visible in the invoice line grid (`in_list_view = 1`, after `item_code`), with a `depends_on` expression that only renders when the line's `item_code` equals the configured `coupon_item`. On submitted invoices the field becomes `read_only = 1` via the fixture's `read_only` property.

**Rationale**:
- ERPNext's `Sales Invoice Item` is the correct row-level anchor for a per-line booklet reference. Putting the link on the parent `Sales Invoice` wouldn't scale to multi-booklet invoices (each booklet needs its own line → its own link).
- A `Link` field gives clean navigation both ways: clicking from the invoice line lands on the booklet; the booklet's `sales_invoice` link reaches the invoice. This matches FR-061 and SC-007.
- `Custom Field` fixtures survive ERPNext upgrades without conflict because they're added to a documented extension point (the `Custom Field` DocType), not to core ERPNext JSON. Any site-level customisation layered on top (via the Customise Form UI) is merged by Frappe at migrate time.
- Only activating the field when `item_code == coupon_item` keeps it out of the way for ordinary (non-booklet) invoice lines — so the same `Sales Invoice` form is still usable for generic selling (spec edge case "Invoice line without a booklet reference").

**Alternatives considered**:
- **Store the booklet name in `Sales Invoice Item.serial_no`** — rejected. `serial_no` is a free-text field tied to Frappe's stock ledger semantics; using it for Purisol booklet references would confuse any standard stock report and break the non-stock model of `coupon_item`.
- **Store the booklet name in `Sales Invoice Item.remarks`** — rejected. Stringly-typed foreign keys can't be navigated, can't be validated by Frappe's link-integrity code, and won't appear in reports as a proper link column.
- **Create a new child table `Purisol Sale Booklet` hanging off `Sales Invoice`** — rejected. This is exactly the "parallel sale DocType" pattern the constitution (Principle II) forbids and that the spec explicitly calls out: "no parallel custom invoice DocType is created" (FR-060). A sibling child table produces the same fragmentation of truth as a full sibling DocType.
- **Store the booklet name on the `Sales Invoice` parent via `po_no` / `po_date`** — rejected. Parent-level field can hold at most one value; multi-booklet sales (Story 2) need per-line references.

---

## 2. Where to run the submit/cancel logic: controller override vs. `doc_events`

**Decision**: Use Frappe's `hooks.doc_events` mechanism in `cx_purisol/hooks.py`, registering module-level callables for `Sales Invoice`:

```python
doc_events = {
    "Sales Invoice": {
        "validate":   "cx_purisol.sales_invoice.sales_invoice_hooks.validate_booklet_lines",
        "on_submit":  "cx_purisol.sales_invoice.sales_invoice_hooks.mark_booklets_sold",
        "on_cancel":  "cx_purisol.sales_invoice.sales_invoice_hooks.reverse_booklets_sale",
        "on_trash":   "cx_purisol.sales_invoice.sales_invoice_hooks.guard_trash",
    },
}
```

Each callable iterates `doc.items`, short-circuits when no line has `purisol_booklet` set, and performs its booklet updates inside the request transaction.

**Rationale**:
- `doc_events` is the idiomatic Frappe hook for "integrate with a DocType I don't own" — it layers onto the core controller without monkey-patching. Any future ERPNext upgrade that adds its own `on_submit` logic keeps working; our hook runs alongside.
- Subclassing `ERPNext.Selling.SalesInvoice` would force us to register an `override_doctype_class` in `hooks.py`, which means **every** Sales Invoice load in a site with cx_purisol installed goes through our subclass — a much larger blast radius than needed. `doc_events` only run at the specified lifecycle points.
- Using module-level functions (not methods) keeps the logic trivially unit-testable: tests can construct a `frappe.get_doc(...)` in memory and call `validate_booklet_lines(doc, method="validate")` directly.
- Frappe's `doc_events` guarantee that the hook is called **inside** the transaction Frappe opened for `save()` / `submit()` / `cancel()` — so raising `frappe.ValidationError` aborts the whole operation with no partial state. This is exactly what FR-024 and FR-031 demand.

**Alternatives considered**:
- **Subclass via `override_doctype_class`** — rejected, blast radius (see above).
- **Use `before_submit` instead of `on_submit`** — rejected. `before_submit` runs before the parent's `docstatus` has flipped to 1; writing to a booklet's `sales_invoice` field with the not-yet-submitted invoice name introduces a tiny but real window where a crash leaves a booklet referencing a never-submitted invoice. `on_submit` runs after `docstatus == 1` is persisted inside the same transaction, and the transaction's atomicity covers any crash during the booklet writes.
- **Use `before_cancel` instead of `on_cancel`** — considered, chose `on_cancel` for symmetry with `on_submit`. `before_cancel` would allow rejecting the cancel earlier (by raising), but both hooks are inside the cancel transaction and have identical effect on atomicity. Using `on_cancel` keeps "happens after Frappe has validated the user can cancel this doc at all" semantics.

---

## 3. How to resolve the Price List on a given sale

**Decision**: Implement a pure helper in `cx_purisol/cx_purisol/cx_purisol/api/sell_booklets.py`:

```python
def _resolve_price_list(customer: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    customer_default = frappe.db.get_value("Customer", customer, "default_price_list")
    if customer_default:
        return customer_default
    settings_default = frappe.db.get_single_value("Purisol Settings", "default_price_list")
    if settings_default:
        return settings_default
    frappe.throw(_(
        "No Price List could be resolved for this sale. "
        "Configure a default_price_list in Purisol Settings or pick one on the workflow."
    ))
```

The resolved value is set on `Sales Invoice.selling_price_list` before Frappe's built-in rate-lookup runs. No custom rate calculation is performed.

**Rationale**:
- Centralising resolution in one function makes FR-013 a single testable unit. The same helper covers both the draft-creation path (where it must succeed) and any future "retry with different price list" path.
- Delegating the actual rate lookup to Frappe (`doc.set_missing_values()` / `doc.calculate_taxes_and_totals()`) inherits every bit of standard ERPNext pricing behaviour: `Price List Item` lookup, currency conversion, Pricing Rule application, UOM conversion, tax template attachment. We don't reimplement any of that.
- Raising on no-resolvable case (rather than silently defaulting to ERPNext's "first Price List ever found") matches FR-041 and avoids the failure mode where a new site with no Price List configured still manages to create a zero-rate invoice.

**Alternatives considered**:
- **Let ERPNext resolve the price list implicitly** — rejected. ERPNext's `Customer.default_price_list` is used when the Sales Invoice is created through the form, but the workflow creates the invoice programmatically, and we also need the spec's three-tier fallback (workflow → customer → Settings) which ERPNext core doesn't model.
- **Store the resolution-preference order in Purisol Settings as a configurable list** — rejected as premature. The spec pins the order, and having it configurable would produce ambiguous error messages ("which order was in effect when this sale failed?"). We can add configurability later if a real need surfaces.

---

## 4. How to check for consumption during cancellation

**Decision**: On `on_cancel`, for each booklet referenced by a line with `purisol_booklet` set, run:

```python
consumed_count = frappe.db.count(
    "Purisol Coupon",
    filters={"booklet": booklet_name, "status": "Consumed"},
)
```

If `consumed_count > 0` for **any** referenced booklet, accumulate the offending booklet names, then raise a single `frappe.ValidationError` naming all of them. Only when every referenced booklet reports `consumed_count == 0` does the reversal proceed.

**Rationale**:
- Checking **all** referenced booklets before reversing anything matches FR-031 ("cancellation is all-or-nothing across the invoice") and the Story 3 acceptance scenario 3 (multi-booklet cancel with one consumed booklet rejects the whole cancel, not just the consumed line).
- Using `frappe.db.count` (which executes a single `SELECT COUNT(*)` per booklet) is more efficient than loading each coupon as a document — for a 10-booklet invoice that's 10 cheap queries, well under the performance budget.
- Accumulating all offending booklets before raising (rather than raising on the first) gives the Administrator a complete picture of what's blocking the cancel — they don't have to cancel, retry, re-discover another blocker, retry, ad infinitum. Matches SC-009's "identify and correct on first read" goal.

**Alternatives considered**:
- **Check `booklet.remaining_count < 20`** — rejected. `remaining_count` is an aggregate cache; per-coupon status is the source of truth (constitution IV: "Aggregates lie; per-coupon metadata does not."). An earlier phase or a future manual correction could theoretically leave `remaining_count` out of sync; querying `Purisol Coupon.status` directly is the defensible check.
- **Check individual `Purisol Coupon.consumption_entry` non-null** — equivalent in correctness but more verbose than the status filter, and couples the check to Phase 4's submittable DocType name. Using `status == "Consumed"` is the layer-appropriate check.

---

## 5. Workflow entry point: command palette, list action, or form button?

**Decision**: Ship **both** the list-view action (primary path) and the `frappe.prompt`-based dialog (dialog is what opens regardless of how the workflow is launched). The list-view action is defined in `cx_purisol/cx_purisol/public/js/purisol_coupon_booklet_list.js` (loaded via `doctype_list_js` in `hooks.py`). A future dedicated workflow form is deliberately deferred — the list-action + dialog combination satisfies FR-010 entirely, and adding a form later is a small additive change.

**Rationale**:
- The list view is where the Administrator already has the context of "which booklets to sell" — spec's user stories all describe selecting booklets in a list and launching the workflow on the selection. A list-view action reuses that context directly.
- A standalone workflow form (a non-submittable "Purisol Sell Booklets Workflow" DocType used only to carry UI state) would introduce a new DocType whose only purpose is UI, which violates Principle II and adds migration weight for zero durable value. The `frappe.prompt` dialog carries the same transient UI state without persisting anything.
- The dialog approach makes it trivial to reuse from a command-palette keyboard shortcut or a dashboard button in a future phase — both call the same whitelisted function.

**Alternatives considered**:
- **Standalone workflow DocType** — rejected as above.
- **List-view bulk action only, no dialog** — rejected. FR-011 requires choosing a customer, FR-013 allows optionally choosing a Price List — a bulk action with no interactive step would have to pick arbitrary defaults for both, which is worse UX.

---

## 6. What to do on invoice amendment (cancel + new)

**Decision**: No special Phase 3 handling required. Frappe's built-in amend flow performs a `cancel` on the original and an `insert` of a new draft invoice with `amended_from` set to the cancelled one. Because `on_cancel` already enforces the consumption-blocks-reversal rule, amendment inherits it for free: if any referenced booklet has consumption, the cancel step fails and amendment can't proceed; if no consumption, the booklets revert to `In Stock` and the new draft can freely re-reference any of them.

**Rationale**:
- Reusing the standard ERPNext amend flow keeps the accounting correct (original invoice is cancelled in the GL, new invoice is posted) and preserves the audit trail (the booklet's `tabVersion` history shows one cancel + one new sale, matching the financial record).
- Writing a custom "amend" path would duplicate the consumption check and introduce a way for the two paths to drift.

**Alternatives considered**:
- **Block amendment entirely on booklet-bearing invoices** — rejected. The Administrator needs a correction path for real mistakes (wrong customer, typo on Price List); blocking amendment would force them to manually cancel, then manually create a new invoice, re-linking every booklet by hand — defeats the whole "one workflow run" design.

---

## 7. Configuration prerequisite: the `coupon_item`

**Decision**: The Administrator creates the `coupon_item` once, as a standard ERPNext `Item` with:
- `item_code` chosen by the shop (e.g., `COUPON-BOOKLET`); the name is not magic.
- `item_group` set to a generic group (no Purisol-specific group is required).
- `stock_uom = "Booklet"` (ERPNext UOM — Administrator creates if not present).
- `is_stock_item = 0` (non-stock — ERPNext inventory must not double-count what Purisol tracks).
- `include_item_in_manufacturing = 0`.
- `is_sales_item = 1` (so it appears in Sales Invoice item pickers for general awareness — the workflow doesn't use the picker, but manual invoice edits should at least see the item exists).

The `Item` is then linked in `Purisol Settings.coupon_item`. The quickstart walks through this one-time setup; Phase 3 code does not auto-create the Item (it refuses to operate when the setting is missing, matching FR-003).

**Rationale**:
- `is_stock_item = 0` prevents ERPNext stock entries / warehouse reservations that would conflict with Purisol's own inventory of booklets. Booklet inventory is tracked by `Purisol Coupon Booklet.status`; ERPNext stock would shadow-track it incorrectly.
- Using `stock_uom = "Booklet"` gives clean invoice prints ("1 Booklet × 100 SAR = 100 SAR") and makes future per-booklet pricing reports trivial.
- Auto-creating the Item would hide this setup from the Administrator and bury decisions (item group, UOM, non-stock flag) that the shop's accountant may want to review.

**Alternatives considered**:
- **Auto-create the Item in a fixtures file or in `Purisol Settings` validation** — rejected. Silent auto-creation would still need default values for `item_group`, `income_account`, `expense_account`, etc. — every wrong guess becomes a lifetime data migration. Refusing to operate until the Administrator configures it explicitly is simpler and safer.

---

## 8. Transactional atomicity: do we need a savepoint?

**Decision**: No explicit savepoint. The Frappe request transaction (opened implicitly by `doc.submit()` and `doc.cancel()`) is sufficient.

**Rationale**:
- Frappe commits at the end of the HTTP request; any `frappe.throw` before commit rolls back all pending writes. Because `validate`, `on_submit`, and `on_cancel` all run **inside** that one transaction, a failure anywhere in our hook unwinds every booklet write together with the invoice's own writes. This matches FR-024 and FR-032.
- Savepoints inside `on_submit` would only matter if we wanted to catch an exception ourselves and continue; we explicitly don't — spec says partial completion is not allowed.

**Alternatives considered**:
- **`frappe.db.savepoint` per booklet** — rejected. Adds code complexity without changing the guarantee (we never `rollback_to_savepoint`; any failure still raises all the way out).
- **`frappe.enqueue` the updates in a background job** — rejected. Background enqueueing would break the atomicity between the invoice submit and the booklet updates (the job could run after the invoice is committed but fail before the booklets update, leaving a committed `Sold` invoice and an unchanged booklet). Keeping everything synchronous and bounded-size is the right trade for a single-sale scale.

---

## 9. Concurrency: two simultaneous submits of the same booklet

**Decision**: Rely on Frappe's optimistic locking on `Purisol Coupon Booklet.modified`. The `validate` hook loads each referenced booklet (`frappe.get_doc("Purisol Coupon Booklet", name)`) during submit; the implicit `modified` stamp is compared at write time; the loser of a race receives `frappe.TimestampMismatchError`, which Frappe surfaces as a retry-able error.

**Rationale**:
- Spec's Story 2 acceptance scenario 2 and the concurrent-submit edge case both require "exactly one invoice succeeds; the other is rejected at submit with a clear error". Optimistic locking delivers this without pessimistic `FOR UPDATE` locks that would serialise unrelated sales.
- At the 1–10 booklet scale, optimistic locking conflicts are rare and cheap (Administrator retries once); pessimistic locking would introduce deadlock potential if two submits overlap in booklet sets.
- The resulting error message from `TimestampMismatchError` is translated by Frappe core and is adequate for Phase 3. (Future phases can catch and re-raise with a more specific Purisol-shaped message if real-world feedback demands it.)

**Alternatives considered**:
- **Explicit `SELECT ... FOR UPDATE` on booklet rows in `validate`** — rejected as above.
- **Advisory lock per booklet via `frappe.cache` / Redis** — rejected. Over-engineering at this scale; adds a new failure mode (lock leak on crashed worker) with no offsetting benefit.

---

## 10. Auditability: attributing the booklet state change to the invoice

**Decision**: Do the booklet updates via `doc.db_set(fieldname, value, update_modified=True, notify=True)` wrapped in a single helper that also passes a `Comment` onto the booklet (`frappe.get_doc(...).add_comment("Info", _("Sold via {0}").format(invoice_name))`). `track_changes = 1` on the booklet already writes a `tabVersion` entry with the user and timestamp; the explicit `Comment` makes the "why" discoverable on the booklet's timeline without hunting through Version diffs.

**Rationale**:
- Matches FR-025 ("change log MUST attribute the status change to the submitted Sales Invoice") and SC-010 ("any later viewer can answer 'why did this booklet's status change?' from the booklet record alone").
- A `Comment` is a standard Frappe affordance — it's visible in the timeline alongside the Version entries, survives exports, and doesn't require a custom audit-log DocType.
- `db_set` (versus full `doc.save()`) is the correct choice for these targeted field updates: it writes exactly the named field(s), updates `modified`, and fires `on_update` events — without re-running `validate` (which would reject the `In Stock → Sold` transition on its own, since the helper isn't aware of which transition is "OK" outside the submit context). To let `db_set` through without the widened-validate guard re-triggering, the booklet controller's `_ALLOWED_TRANSITIONS` set must be the source of truth — which is why we widen it in the controller rather than guarding at call sites.

**Alternatives considered**:
- **Write a parallel `Purisol Booklet Sale Event` submittable DocType** — rejected. That would be a custom ledger for sale events running alongside the Sales Invoice, exactly the duplication constitution II prohibits. The Sales Invoice itself is the submittable record.
- **Emit a custom `frappe.log_error` / `frappe.logger` entry per booklet change** — rejected. Error logs are not meant for audit trails; they decay with log rotation and are not indexed against the booklet record.

---

## 11. Permission enforcement on the workflow entry point

**Decision**: Decorate `purisol_create_sales_invoice_for_booklets` with `@frappe.whitelist()` and add `frappe.only_for("Purisol Administrator")` as the first line of the function body. The list-view action JS also checks `frappe.user.has_role("Purisol Administrator")` before rendering.

**Rationale**:
- `frappe.only_for` raises `frappe.PermissionError` if the current user lacks the role — a clean, standard Frappe rejection that the framework translates into a 403.
- Server-side enforcement is authoritative; the JS role check is a UX nicety (don't show the button) but never a security boundary.
- Standard ERPNext Sales Invoice permissions continue to govern the Sales Invoice itself — users who launch the workflow must also have permission to create a Sales Invoice (otherwise Frappe's `Document.insert` raises); Purisol Administrators are expected to hold at least `Accounts User` or equivalent in practice.

**Alternatives considered**:
- **JS-only role check** — rejected. Curl/bench requests would bypass it.
- **Custom role "Purisol Seller"** — rejected. Constitution VI allows exactly one custom role; adding another requires a constitution amendment and isn't justified by MVP needs.
