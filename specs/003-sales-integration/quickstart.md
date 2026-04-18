# Quickstart — Sales Integration

**Feature**: 003-sales-integration | **Date**: 2026-04-18

This quickstart walks a fresh ERPNext site through: one-time configuration of the coupon item and price list; selling a single booklet; selling a multi-booklet order; and both branches of cancellation (safe reversal and consumption-blocked rejection). Each section states the exact prerequisites, steps, and verification points.

Prerequisites for **everything below**: `cx_purisol` is installed on the site; Phase 1 (booklet generation) and Phase 2 (custody) migrations have run successfully; at least one user holds the `Purisol Administrator` role.

---

## 1. One-time configuration (run once per site)

### 1.1. Create the Coupon Item

Desk → `Item` → **New**:

| Field | Value |
|-------|-------|
| Item Code | `COUPON-BOOKLET` *(or whatever code the shop prefers — it's not magic)* |
| Item Name | `Coupon Booklet` |
| Item Group | `All Item Groups` (or whatever Item Group the shop uses for non-physical goods) |
| Stock UOM | `Booklet` *(create the UOM if it doesn't exist)* |
| Is Stock Item | **unchecked** *(critical — Purisol tracks inventory, not ERPNext)* |
| Is Sales Item | **checked** |
| Include Item in Manufacturing | **unchecked** |

Save. The Item page now has a default `Income Account` field — populate it if the Company's chart-of-accounts requires it (ERPNext will complain at invoice submit otherwise).

### 1.2. Create / confirm a Price List

Desk → `Price List` → open `Standard Selling` (or **New**). Ensure:
- `Selling` is checked.
- A `Currency` is set (matches the Company's default).

Then: Desk → `Item Price` → **New**:

| Field | Value |
|-------|-------|
| Item Code | `COUPON-BOOKLET` *(the code you chose above)* |
| Price List | `Standard Selling` |
| Price List Rate | `100` *(or whatever per-booklet rate is correct)* |

Save.

### 1.3. Configure Purisol Settings

Desk → `Purisol Settings` (singleton):

| Field | Set to |
|-------|--------|
| Coupon Item | `COUPON-BOOKLET` *(your Item Code from 1.1)* |
| Default Price List | `Standard Selling` |

Save. Phase 3 is now operational.

### 1.4. Verification

```bash
bench --site <site> console
```
```python
from frappe import get_single
s = get_single("Purisol Settings")
assert s.coupon_item == "COUPON-BOOKLET"
assert s.default_price_list == "Standard Selling"
```

---

## 2. Seed data for the walkthrough

### 2.1. A Customer

Desk → `Customer` → **New**:

| Field | Value |
|-------|-------|
| Customer Name | `Acme Co.` |
| Customer Type | `Company` |
| Customer Group | `All Customer Groups` |
| Territory | `All Territories` |

Save. Do **not** set a per-customer Default Price List (we'll test the Settings-default resolution path first).

### 2.2. A Delivery Man (Employee)

Desk → `Employee` → **New**:

| Field | Value |
|-------|-------|
| First Name | `Ali` |
| Company | *(the default Company)* |
| Status | `Active` |

Save; note the Employee's `name` (e.g., `HR-EMP-00001`).

### 2.3. Booklets

If no booklets exist yet, generate a few:

Desk → any URL → open the list view for `Purisol Coupon Booklet` → use the Phase-1 "Generate Booklets" action with quantity `5`.

Wait for completion; confirm 5 new booklets exist with `status = In Stock`.

### 2.4. Put one booklet into Custody (optional — needed for User Story 1 scenario 2 and Story 2)

Desk → `Purisol Custody Entry` → **New**:

| Field | Value |
|-------|-------|
| Entry Type | `Assign` |
| To Delivery Man | `Ali` (the `HR-EMP-00001` you noted) |
| Booklets (child table) | add one row with the second booklet (e.g., `WP-00002`) |

Save → **Submit**. Confirm that booklet now has `status = In Custody` and `current_delivery_man = HR-EMP-00001`.

---

## 3. Walkthrough: Sell a single booklet (User Story 1)

### 3.1. Launch the workflow

1. Desk → list view for `Purisol Coupon Booklet`.
2. Select the checkbox next to the first `In Stock` booklet (e.g., `WP-00001`).
3. In the bulk-action menu: **Sell Selected to Customer**.
4. Dialog opens.

### 3.2. Fill the dialog

| Field | Value |
|-------|-------|
| Customer | `Acme Co.` |
| Price List | *(leave blank — we'll test Settings-default resolution)* |

Click **Create Invoice**.

### 3.3. Expected result

- The desk navigates to the newly-created **draft** `Sales Invoice`.
- The invoice has:
  - `customer = Acme Co.`
  - `selling_price_list = Standard Selling`
  - Exactly one item line with:
    - `item_code = COUPON-BOOKLET`
    - `qty = 1`
    - `rate = 100` (from the Price List)
    - `purisol_booklet = WP-00001` *(visible in the grid)*
- **Booklet `WP-00001` is still `In Stock`** — no transition happens at draft creation.

### 3.4. Submit the invoice

Click **Submit** on the Sales Invoice.

Confirm on `Purisol Coupon Booklet` (`WP-00001`):

| Field | Expected value |
|-------|----------------|
| status | `Sold` |
| customer | `Acme Co.` |
| sold_on | *invoice's posting date + posting time* |
| sales_invoice | *the new invoice's name* |
| current_delivery_man | *(empty)* |

Open the booklet's **Timeline** (right panel) and confirm:
- A `Comment` entry: `Sold via <invoice name>`.
- A `Version` entry showing the field transitions (`status: In Stock → Sold`, etc.).

### 3.5. Bidirectional navigation (SC-007)

- From the booklet: click the `sales_invoice` link → lands on the submitted Sales Invoice.
- From the Sales Invoice line: click the `purisol_booklet` link → lands on the booklet.

### 3.6. Scenario variant: sell a `In Custody` booklet

Repeat 3.1–3.4 with booklet `WP-00002` (the one assigned to Ali in §2.4).

Expected: the booklet transitions `In Custody → Sold`, `current_delivery_man` is **cleared**, and the past custody history remains in the Custody Entry chain (open `WP-00002`'s Timeline and scroll back — the Phase-2 Assign entry is still there).

---

## 4. Walkthrough: Sell multiple booklets in one invoice (User Story 2)

1. In the booklet list view, select three rows: two `In Stock` and one `In Custody` (use the remaining booklets from §2.3, re-assigning one via a fresh Custody Entry if needed).
2. **Sell Selected to Customer** → Customer `Acme Co.`, Price List blank.
3. Draft invoice opens with **three** line items, each with a distinct `purisol_booklet` link.
4. Submit.

Expected: all three booklets transition to `Sold`, share the same `sold_on` (the invoice's posting datetime) and `sales_invoice`, and the `In Custody` one has `current_delivery_man` cleared.

### 4.1. Rejection: duplicate booklet on the draft

Open a fresh draft (via the workflow), then manually add a second line in the items grid that reuses the same `purisol_booklet` as the first. Click **Submit**.

Expected: submit is rejected with `"Booklet <name> appears on more than one line of this invoice."` No booklet modified, invoice remains draft.

### 4.2. Rejection: stale draft, booklet already sold elsewhere

1. Create draft A referencing booklet `WP-00003` (don't submit).
2. Via the workflow, create draft B referencing the same booklet and **submit** B first.
3. Return to draft A and click **Submit**.

Expected: draft A's submit is rejected with `"Booklet WP-00003 cannot be sold — current status: Sold."` Draft A remains draft; `WP-00003` stays `Sold` against invoice B.

---

## 5. Walkthrough: Cancel a sale (User Story 3)

### 5.1. Safe cancellation (no consumption)

Pick a booklet sold in §3 or §4 whose coupons are all still `Available` (they are, since Phase 3 never writes coupons).

On its `Sales Invoice`: **Menu → Cancel**.

Expected:
- Invoice `docstatus` flips to `2` (cancelled).
- Each referenced booklet:
  - `status = In Stock`
  - `customer`, `sold_on`, `sales_invoice` all empty
  - `current_delivery_man` remains empty (cancel does **not** restore custody — FR-032)
- Booklet Timeline shows the original sale comment AND a new comment: `Sale reversed — invoice <name> cancelled.`

### 5.2. Consumption-blocked cancellation

Requires a consumed coupon. Since Phase 4 isn't shipped yet, simulate via the console:

```bash
bench --site <site> console
```
```python
import frappe
# Pick a currently-Sold booklet
booklet_name = "WP-00004"  # whatever you sold above
coupon = frappe.get_all("Purisol Coupon",
                        filters={"booklet": booklet_name}, limit=1, pluck="name")[0]
frappe.db.set_value("Purisol Coupon", coupon, "status", "Consumed")
frappe.db.commit()
```

> **Note**: This direct write is **only** valid in the Phase-3 quickstart for testing. Phase 4 will introduce the `Purisol Consumption Entry` submittable; in production that submittable is the only legitimate way to set `status = "Consumed"`.

Now try to cancel the Sales Invoice that sold `WP-00004`: **Menu → Cancel**.

Expected: cancel is rejected with a message naming `WP-00004`. The invoice remains submitted; the booklet remains `Sold`; no state change anywhere.

Clean up the test-only consumption so subsequent runs aren't polluted:
```python
frappe.db.set_value("Purisol Coupon", coupon, "status", "Available")
frappe.db.commit()
```

---

## 6. Walkthrough: Price List resolution (User Story 4)

### 6.1. Prep: seed a second Price List

Desk → `Price List` → **New** with name `Wholesale` (Selling checked).
Desk → `Item Price` → **New**: `COUPON-BOOKLET` on `Wholesale` at rate `80`.

### 6.2. Case A — Settings default

Customer `Acme Co.` has no per-customer default; workflow picks no Price List.
Expected line rate: **100** (Settings `default_price_list = Standard Selling`, rate 100).

### 6.3. Case B — Customer default

Set `Acme Co..default_price_list = Wholesale`. Re-run the workflow with no Price List chosen.
Expected line rate: **80**.

### 6.4. Case C — Workflow override

Leave `Acme Co..default_price_list = Wholesale` but in the workflow dialog pick **Price List = Standard Selling**.
Expected line rate: **100** — the workflow's explicit choice wins.

### 6.5. Case D — Misconfigured Price List

Create a Price List `Empty` (no `Item Price` entry for `COUPON-BOOKLET`). Run the workflow and pick `Empty`.
Expected: invoice creation surfaces a clear error from standard ERPNext ("no price found for item ...") naming the missing Price List entry — Administrator fixes configuration and retries.

---

## 7. Test the full flow from bench

```bash
# Run only Phase-3 tests (requires site configured as above)
bench --site <site> run-tests --app cx_purisol \
    --module cx_purisol.cx_purisol.tests.test_sales_flows
```

All tests should pass on a clean site that has completed steps 1–2 of this quickstart. CI runs `bench --site <ci-site> run-tests --app cx_purisol` on every PR.

---

## 8. Verification checklist (maps to success criteria)

| Success criterion | Walkthrough section | Pass when |
|-------------------|---------------------|-----------|
| SC-001 Single sale < 60 s | §3 | Complete §3.1–3.4 end-to-end within one minute |
| SC-002 Booklet fields correct on submit | §3.4 | All fields match the table |
| SC-003 Multi-sale of up to 10 < 90 s | §4 | Complete §4 for 10 booklets in under 90 s |
| SC-004 Wrong-status booklets rejected | §4.2 | Stale-draft submit rejected with clear error |
| SC-005 No partial updates on invalid submit | §4.1, §4.2 | On rejection, no booklet is modified |
| SC-006 Cancellation rules | §5.1, §5.2 | Safe cancel reverses; consumed cancel rejected |
| SC-007 Bidirectional navigation | §3.5 | Both navigations work in one click |
| SC-008 Price List resolution order | §6.2–§6.4 | All three cases produce the expected rate |
| SC-009 Error messages self-explanatory | §4.1, §4.2, §5.2 | A first-time Administrator can fix each error on first read |
| SC-010 Audit trail attribution | §3.4, §5.1 | Each sale and reversal has a dedicated Comment on the booklet |
