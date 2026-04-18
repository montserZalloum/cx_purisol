# Phase 1 Quickstart — Consumption Recording

**Feature**: 004-consumption-recording | **Date**: 2026-04-18

This quickstart walks through the minimum concrete setup needed to exercise Phase 4 end-to-end on a clean Frappe site. It is the shortest path from "freshly-migrated site with Phases 1–3 installed" to "a Consumption Entry has been submitted, coupons are `Consumed`, a booklet has auto-depleted, and a cancel has reverted it all". It doubles as the reference script for the integration tests under `cx_purisol/tests/test_consumption_flows.py`.

---

## 1. Prerequisites

- Frappe Bench running locally with a site that has `cx_purisol` installed (`bench --site <site> install-app cx_purisol`).
- Phase 1 migrations applied (`Purisol Coupon Booklet`, `Purisol Coupon`, `Purisol Settings` exist).
- Phase 2 migrations applied (`Purisol Custody Entry`, `Purisol Custody Entry Booklet` exist).
- Phase 3 migrations applied (`Custom Field Sales Invoice Item.purisol_booklet` exists, Sales Invoice hooks are registered).
- Phase 4 migrations applied (`Purisol Coupon Consumption Entry`, `Purisol Coupon Consumption Item`, `Purisol Coupon Discrepancy Item` exist; coupon/booklet controllers widened).
- The `Purisol Administrator` role exists and is assigned to your user.
- `Purisol Settings.coupon_item` is configured (Phase 3 prerequisite).
- `Purisol Settings.default_price_list` is configured, or the workflow will prompt for one.

---

## 2. Seed data (one-time)

Run inside `bench --site <site> console` or as a test `setUp`:

```python
import frappe

# 1. A customer to sell to (ERPNext Customer).
if not frappe.db.exists("Customer", "Acme Co."):
    frappe.get_doc({
        "doctype": "Customer",
        "customer_name": "Acme Co.",
        "customer_type": "Company",
    }).insert(ignore_permissions=True)

# 2. A delivery man (ERPNext Employee).
if not frappe.db.exists("Employee", {"employee_name": "Ali"}):
    ali = frappe.get_doc({
        "doctype": "Employee",
        "employee_name": "Ali",
        "first_name": "Ali",
        "gender": "Male",
        "date_of_birth": "1990-01-01",
        "date_of_joining": "2024-01-01",
        "status": "Active",
        "company": frappe.defaults.get_user_default("Company"),
    }).insert(ignore_permissions=True)
else:
    ali = frappe.get_doc("Employee", {"employee_name": "Ali"})

# 3. Generate one booklet WP-00001 with 20 coupons CP-00001..CP-00020 (Phase 1 helper).
from cx_purisol.cx_purisol.api.booklet_generation import purisol_generate_booklets
purisol_generate_booklets(count=1)  # creates WP-00001 In Stock + 20 Available coupons

# 4. Sell WP-00001 to Acme via Phase 3 workflow.
from cx_purisol.cx_purisol.api.sell_booklets import purisol_create_sales_invoice_for_booklets
invoice_name = purisol_create_sales_invoice_for_booklets(
    customer="Acme Co.",
    booklets=["WP-00001"],
)
si = frappe.get_doc("Sales Invoice", invoice_name)
si.submit()
# Booklet WP-00001 is now Sold; coupons CP-00001..CP-00020 are still Available.
```

After this block:

- `Purisol Coupon Booklet[WP-00001].status == "Sold"`, `customer == "Acme Co."`, `consumed_count == 0`, `remaining_count == 20`.
- `Purisol Coupon[CP-00001..20].status == "Available"` for every one of the 20.

---

## 3. Happy path — Mode A: pick three coupons and submit

```python
import frappe

entry = frappe.get_doc({
    "doctype": "Purisol Coupon Consumption Entry",
    "posting_date": frappe.utils.today(),
    "posting_time": frappe.utils.nowtime(),
    "delivery_man": ali.name,
    "coupons": [
        {"coupon": "CP-00001"},  # Mode A would populate booklet/customer via fetch_from;
        {"coupon": "CP-00002"},  # server also fetches on validate. Setting just `coupon` works.
        {"coupon": "CP-00003"},
    ],
}).insert(ignore_permissions=True)
entry.submit()

# Verify postconditions:
assert frappe.db.get_value("Purisol Coupon", "CP-00001", "status") == "Consumed"
assert frappe.db.get_value("Purisol Coupon", "CP-00001", "consumed_by_delivery_man") == ali.name
assert frappe.db.get_value("Purisol Coupon", "CP-00001", "consumption_entry") == entry.name

booklet = frappe.get_doc("Purisol Coupon Booklet", "WP-00001")
assert booklet.consumed_count == 3
assert booklet.remaining_count == 17
assert booklet.status == "Sold"   # not yet depleted
```

---

## 4. Happy path — Mode B: resolve by coupon numbers, submit, auto-deplete

Continuing from the above (booklet now has 3 consumed, 17 Available):

```python
# Administrator pastes a block of 17 numbers — the remaining coupons.
from cx_purisol.cx_purisol.api.consumption import resolve_coupons

remaining_numbers = [f"CP-{i:05d}" for i in range(4, 21)]  # CP-00004..CP-00020
result = resolve_coupons(coupon_numbers=remaining_numbers)
assert result["unresolved"] == []
assert len(result["resolved"]) == 17

# Build the entry with those 17 coupons.
entry2 = frappe.get_doc({
    "doctype": "Purisol Coupon Consumption Entry",
    "posting_date": frappe.utils.today(),
    "posting_time": frappe.utils.nowtime(),
    "delivery_man": ali.name,
    "coupons": [{"coupon": r["coupon"]} for r in result["resolved"]],
}).insert(ignore_permissions=True)
entry2.submit()

booklet = frappe.get_doc("Purisol Coupon Booklet", "WP-00001")
assert booklet.consumed_count == 20
assert booklet.remaining_count == 0
assert booklet.status == "Depleted"             # auto-depletion fired
assert booklet.depleted_on is not None          # stamped with entry2.posting_datetime
```

A `Comment` with body `Depleted via <entry2.name>` is visible on the booklet's timeline.

---

## 5. Rejection paths — verify each blocking check

### 5.1. Empty entry

```python
bad = frappe.get_doc({
    "doctype": "Purisol Coupon Consumption Entry",
    "posting_date": frappe.utils.today(),
    "posting_time": frappe.utils.nowtime(),
    "delivery_man": ali.name,
    "coupons": [],
})
try:
    bad.insert(ignore_permissions=True)
    bad.submit()
    assert False, "expected ValidationError"
except frappe.ValidationError as e:
    assert "at least one coupon" in str(e)
```

### 5.2. Duplicate coupon in entry

```python
# Pre-state: CP-00005 exists and is already Consumed after §4's submit — use a fresh booklet here.
# For this snippet, substitute any pair of coupons on a fresh Available booklet.
```

### 5.3. Non-existent coupon

```python
bad = frappe.get_doc({
    "doctype": "Purisol Coupon Consumption Entry",
    "posting_date": frappe.utils.today(),
    "posting_time": frappe.utils.nowtime(),
    "delivery_man": ali.name,
    "coupons": [{"coupon": "CP-99999"}],
}).insert(ignore_permissions=True)
try:
    bad.submit()
    assert False
except frappe.ValidationError as e:
    assert "CP-99999" in str(e) and "does not exist" in str(e)
```

### 5.4. Already-consumed coupon

```python
# CP-00001 was consumed in §3.
bad = frappe.get_doc({
    "doctype": "Purisol Coupon Consumption Entry",
    "posting_date": frappe.utils.today(),
    "posting_time": frappe.utils.nowtime(),
    "delivery_man": ali.name,
    "coupons": [{"coupon": "CP-00001"}],
}).insert(ignore_permissions=True)
try:
    bad.submit()
    assert False
except frappe.ValidationError as e:
    assert "CP-00001" in str(e) and "already Consumed" in str(e)
```

---

## 6. Round-trip — cancel reverses everything

Starting from §4's state (WP-00001 Depleted, 20 coupons Consumed via entry+entry2):

```python
entry2.reload()
entry2.cancel()

booklet = frappe.get_doc("Purisol Coupon Booklet", "WP-00001")
assert booklet.status == "Sold"                 # auto-reverted
assert booklet.depleted_on is None              # cleared
assert booklet.consumed_count == 3              # only entry1's coupons remain Consumed
assert booklet.remaining_count == 17

for i in range(4, 21):
    name = f"CP-{i:05d}"
    assert frappe.db.get_value("Purisol Coupon", name, "status") == "Available"
    assert frappe.db.get_value("Purisol Coupon", name, "consumed_on") is None
    assert frappe.db.get_value("Purisol Coupon", name, "consumption_entry") is None

# entry1's coupons (CP-00001..CP-00003) remain Consumed because entry1 is not cancelled.
assert frappe.db.get_value("Purisol Coupon", "CP-00001", "status") == "Consumed"
```

---

## 7. UI flow (manual sanity check)

1. `bench --site <site> browse --user administrator`.
2. Navigate to **Purisol Coupon Consumption Entry → New**.
3. In the form:
   - Set `Delivery Man` to Ali.
   - Use the **By Booklet** tab: type `WP-00001`. A checklist of `Available` coupons appears.
   - Tick three coupons; click **Add to Entry**. The grid fills with three rows; `booklet` and `customer` auto-populate.
   - Switch to the **By Coupon Number** tab: paste `CP-00004\nCP-00005\nCP-99999`. Two rows are added; an inline red error names `CP-99999` and preserves the two good rows.
   - Remove `CP-99999` from the Mode B input and click **Save**. Draft persists.
   - Click **Submit**. The entry advances to `docstatus = 1`; the form reloads with the submitted toolbar.
4. Open `WP-00001` — observe `consumed_count = 5`, `remaining_count = 15`, status still `Sold`.
5. Open `CP-00001` — observe `status = Consumed`, `consumed_on` matches the entry's posting datetime, `consumed_by_delivery_man = Ali`, `consumption_entry` links back to your entry.

---

## 8. Run the test suite

```bash
bench --site <site> run-tests --app cx_purisol --doctype "Purisol Coupon Consumption Entry"
bench --site <site> run-tests --app cx_purisol --module cx_purisol.cx_purisol.api.test_consumption
bench --site <site> run-tests --app cx_purisol --module cx_purisol.cx_purisol.tests.test_consumption_flows
# Or the full app suite:
bench --site <site> run-tests --app cx_purisol
```

Tests that MUST pass before Phase 4 is considered done:

- `test_purisol_coupon_consumption_entry.py` — unit: validate rules (empty, duplicate, has_warnings, discrepancies_detected).
- `test_purisol_coupon.py` — widened: `Available ↔ Consumed` transition tests.
- `test_purisol_coupon_booklet.py` — widened: `Sold → Depleted` and `Depleted → Sold` transition tests.
- `test_consumption.py` (API) — permission gate, list_available_coupons filtering/sort, resolve_coupons batched resolution.
- `test_consumption_flows.py` — one test per Story 1–4 user story + cancel round-trip + concurrent-submit race.

A clean-database run of `bench run-tests --app cx_purisol` is the phase's definition of "done".

---

## 9. Troubleshooting

- **`Booklet status transition from Sold to Depleted is not allowed.`** — the Phase 4 patch `widen_states_for_consumption` did not run. Re-run `bench --site <site> migrate`.
- **`Coupon status must be 'Available' in this phase.`** — the coupon controller wasn't widened; verify the Phase 4 `purisol_coupon.py` edit landed.
- **Mode A checklist is empty for a newly-sold booklet** — verify that the booklet has 20 `Available` coupons via `frappe.db.count("Purisol Coupon", {"booklet": "WP-00001", "status": "Available"})`. If zero, Phase 1 booklet generation did not attach coupons — check the booklet's `before_insert` log.
- **Submit succeeds but `consumed_count` stays 0** — `on_submit` ran but the booklet recompute query has a bug. Inspect `Purisol Coupon Booklet[WP-00001].consumed_count` vs. `frappe.db.count("Purisol Coupon", {"booklet": "WP-00001", "status": "Consumed"})`; any drift indicates the recompute path skipped this booklet.
- **`Timestamp Mismatch Error` on submit** — a concurrent process (another Administrator, or a background job) updated one of the referenced coupons between your draft load and submit. Reload the draft and resubmit.
