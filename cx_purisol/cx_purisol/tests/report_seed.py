"""Shared deterministic seed for Phase 7 report tests.

Entry points (bundle-independent per SC-007):
  seed_for_operations() → SimpleNamespace   Bundle 1: R1 Daily DM Summary, R2 Active Booklets,
                                              R3 Current Custody, R4 Consumption Log
  seed_for_finance()    → SimpleNamespace   Bundle 2: R5 DM Discrepancies, R6 Liability Balance,
                                              R7 Booklet Sales, R8 Discrepancy Rate
  seed_for_analytics()  → SimpleNamespace   Bundle 3: R9 Customer Rate, R10 Lifecycle Duration
  seed_full_phase_7()   → SimpleNamespace   All 10 reports (merges all three)

Each entry point is independent — Bundle 2 tests call only seed_for_finance() and do not
require seed_for_operations() to have been called first.  Shared entities (customers,
employees, price lists) are created idempotently via ensure_* helpers.

Known constants (hand-calculable values used in integration-test assertions):

  Operations bundle
  -----------------
  DM A submits 8 coupons (4 + 4) from 2 booklets today → R1 AS1 row
    coupons_submitted=8, booklets_touched=2, discrepancies_count=1
  Cust-2 has 3 booklets: Depleted(20/0), Sold(12/8), Sold(0/20) → R2 AS2
  DM A holds 2 In-Custody booklets (5d ago and 1d ago) → R3 AS3
  40 consumed coupons within the last 7 days across 3 customers / 4 DMs → R4 AS4

  Finance bundle
  --------------
  DM A: 4 submitted discrepancies (via triggering entries) across 2 DMs → R5 AS1
  Liability JEs: owed_a=200, owed_b=150 → total_owed=350; PE paid=100 → open_balance=250 for DM A → R6 AS2
  5 invoices at pl_retail + 2 at pl_wholesale across 3 customers → R7 AS3
  DM A rate: 4/100 = 4.0%; DM B: 50 coupons, 0 discrepancies = 0.0% → R8 AS4

  Analytics bundle
  ----------------
  Cust-1: 3 Depleted booklets (30d, 45d, 60d) → avg_days=45.0 → R9 AS1
  Cust-2: 2 Depleted booklets (10d, 20d) → avg_days=15.0 → R9 AS1
  Lifecycle DM (avg_generation_to_sale=20, avg_sale_to_depletion=40, avg_full_lifetime=60) → R10 AS2
"""
from __future__ import annotations

import types

import frappe
from frappe.utils import add_to_date, now, today

from cx_purisol.cx_purisol.tests.fixtures import (
    configure_purisol_settings,
    configure_purisol_settings_accounts,
    ensure_coupon_item,
    ensure_customer,
    ensure_item_price,
    ensure_price_list,
    make_booklet_in_stock,
    make_employee,
    seed_administrator_user,
    seed_open_discrepancy,
)

# ---------------------------------------------------------------------------
# Shared name constants
# ---------------------------------------------------------------------------

SEED_ADMIN_EMAIL = "p7-seed-admin@test.example.com"
SEED_NONADMIN_EMAIL = "p7-seed-nonadmin@test.example.com"

SEED_PL_RETAIL = "Seed-P7-PL-Retail"
SEED_PL_WHOLESALE = "Seed-P7-PL-Wholesale"
SEED_ITEM_RATE_RETAIL = 500
SEED_ITEM_RATE_WHOLESALE = 400

SEED_CUSTOMER_1 = "Seed-P7-Cust-1"
SEED_CUSTOMER_2 = "Seed-P7-Cust-2"
SEED_CUSTOMER_3 = "Seed-P7-Cust-3"

SEED_DM_A = ("SeedP7DmA", "Seed")
SEED_DM_B = ("SeedP7DmB", "Seed")
SEED_DM_C = ("SeedP7DmC", "Seed")
SEED_DM_D = ("SeedP7DmD", "Seed")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _seed_nonadmin_user(email: str) -> str:
    if not frappe.db.exists("User", email):
        frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": "SeedNoAdmin",
            "send_welcome_email": 0,
            "enabled": 1,
            "user_type": "System User",
        }).insert(ignore_permissions=True)
    return email


def _shared_infra() -> dict:
    """Idempotently create shared infrastructure used by all three bundles."""
    configure_purisol_settings_accounts()

    pl_retail = ensure_price_list(SEED_PL_RETAIL)
    pl_wholesale = ensure_price_list(SEED_PL_WHOLESALE)
    item = ensure_coupon_item()
    ensure_item_price(item.name, pl_retail.name, SEED_ITEM_RATE_RETAIL)
    ensure_item_price(item.name, pl_wholesale.name, SEED_ITEM_RATE_WHOLESALE)
    configure_purisol_settings(coupon_item=item.name, default_price_list=pl_retail.name)

    dm_a = make_employee(*SEED_DM_A)
    dm_b = make_employee(*SEED_DM_B)
    dm_c = make_employee(*SEED_DM_C)
    dm_d = make_employee(*SEED_DM_D)

    cust_1 = ensure_customer(SEED_CUSTOMER_1, default_price_list=pl_retail.name)
    cust_2 = ensure_customer(SEED_CUSTOMER_2, default_price_list=pl_retail.name)
    cust_3 = ensure_customer(SEED_CUSTOMER_3, default_price_list=pl_wholesale.name)

    seed_administrator_user(SEED_ADMIN_EMAIL)
    _seed_nonadmin_user(SEED_NONADMIN_EMAIL)

    return {
        "dm_a": dm_a, "dm_b": dm_b, "dm_c": dm_c, "dm_d": dm_d,
        "cust_1": cust_1, "cust_2": cust_2, "cust_3": cust_3,
        "pl_retail": pl_retail, "pl_wholesale": pl_wholesale,
        "item": item,
    }


def _create_and_sell(customer_name: str) -> tuple[str, str]:
    """Create a new booklet via generation API, sell it, return (booklet_name, si_name)."""
    from cx_purisol.cx_purisol.api.booklet_generation import _create_booklet_and_coupons
    from cx_purisol.cx_purisol.api.sell_booklets import purisol_create_sales_invoice_for_booklets

    booklet_name, _ = _create_booklet_and_coupons(batch_id="SEED-P7")
    result = purisol_create_sales_invoice_for_booklets(customer_name, [booklet_name])
    si = frappe.get_doc("Sales Invoice", result["name"])
    si.submit()
    return booklet_name, si.name


def _coupon_map(booklet_name: str) -> dict[int, str]:
    rows = frappe.get_all(
        "Purisol Coupon",
        filters={"booklet": booklet_name},
        fields=["name", "page_number"],
    )
    return {r["page_number"]: r["name"] for r in rows}


def _consume_pages(
    booklet_name: str,
    delivery_man: str,
    pages: list[int],
    posting_date: str | None = None,
) -> object:
    """Submit a consumption entry for the given pages of booklet_name."""
    pm = _coupon_map(booklet_name)
    coupons = [pm[p] for p in pages if p in pm]
    entry = frappe.get_doc({
        "doctype": "Purisol Coupon Consumption Entry",
        "posting_date": posting_date or today(),
        "posting_time": frappe.utils.nowtime(),
        "delivery_man": delivery_man,
        "coupons": [{"coupon": c} for c in coupons],
    })
    entry.insert(ignore_permissions=True)
    entry.submit()
    return entry


def _assign_backdated(booklets: list[str], to_delivery_man: str, days_ago: int) -> object:
    """Submit a custody Assign entry with an entry_datetime backdated by days_ago."""
    entry = frappe.get_doc({
        "doctype": "Purisol Custody Entry",
        "entry_type": "Assign",
        "to_delivery_man": to_delivery_man,
        "entry_datetime": add_to_date(now(), days=-days_ago),
        "booklets": [{"booklet": b} for b in booklets],
    })
    entry.insert(ignore_permissions=True)
    entry.submit()
    return entry


def _resolve_disc(disc_name: str, delivery_man: str, action: str) -> object:
    """Submit a discrepancy with the given resolution_action (creates JE/PE as needed)."""
    disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
    disc.resolution_action = action
    if action in ("Add to Liability Ledger", "Immediate Cash Payment"):
        disc.liable_delivery_man = delivery_man
    disc.save(ignore_permissions=True)
    disc.submit()
    disc.reload()
    return disc


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def seed_for_operations() -> types.SimpleNamespace:
    """Seed deterministic data for Bundle 1 (operational) reports.

    Creates:
    - 4 employees, 3 customers, 2 price lists
    - 1 In Stock booklet
    - 2 In Custody booklets for DM A (assigned 5d and 1d ago) → R3 AS3
    - Cust-2: Depleted(20/0, sold 45d ago, depleted 15d ago) + Sold(12/8) + Sold(0/20) → R2 AS2
    - DM A consumes 4+4 coupons from 2 booklets today (gap triggers 1 discrepancy) → R1 AS1
    - DM B consumes 12 coupons day −3; DM C consumes 8 day −1; DM D consumes 8 day −4
    - DM A also consumed 4 day −2 (prior entry for the gap)
    - Total consumed within last 7 days = 40 → R4 AS4
    """
    frappe.set_user("Administrator")
    inf = _shared_infra()
    dm_a = inf["dm_a"].name
    dm_b = inf["dm_b"].name
    dm_c = inf["dm_c"].name
    dm_d = inf["dm_d"].name
    cust_1 = inf["cust_1"].name
    cust_2 = inf["cust_2"].name
    cust_3 = inf["cust_3"].name

    # --- In Stock ---
    booklet_in_stock = make_booklet_in_stock().name

    # --- In Custody for DM A (R3 AS3) ---
    b_5d = make_booklet_in_stock().name
    b_1d = make_booklet_in_stock().name
    _assign_backdated([b_5d], dm_a, days_ago=5)
    _assign_backdated([b_1d], dm_a, days_ago=1)

    # --- Active Booklets for Cust-2 (R2 AS2) ---
    # Depleted: sell and deplete all 20 coupons outside the 1-week window
    b_dep, _ = _create_and_sell(cust_2)
    _consume_pages(b_dep, dm_b, list(range(1, 21)), posting_date=add_to_date(today(), days=-16))
    frappe.db.set_value("Purisol Coupon Booklet", b_dep, {
        "sold_on": add_to_date(today(), days=-45),
        "depleted_on": add_to_date(today(), days=-15),
    })

    # Sold 12/20 consumed (by DM B, day -3, within week)
    b_sold12, _ = _create_and_sell(cust_2)
    entry_b12 = _consume_pages(b_sold12, dm_b, list(range(1, 13)), posting_date=add_to_date(today(), days=-3))
    frappe.db.set_value("Purisol Coupon Booklet", b_sold12, "sold_on", add_to_date(today(), days=-10))

    # Sold 0/20 consumed
    b_sold0, _ = _create_and_sell(cust_2)
    frappe.db.set_value("Purisol Coupon Booklet", b_sold0, "sold_on", add_to_date(today(), days=-5))

    # --- Daily DM Summary / Consumption Log (R1 AS1, R4 AS4) ---
    # Booklet A1: prior consumption day -2 (pages 1-4) then today (pages 9-12) → gap → discrepancy
    b_a1, _ = _create_and_sell(cust_1)
    _consume_pages(b_a1, dm_a, [1, 2, 3, 4], posting_date=add_to_date(today(), days=-2))
    entry_a1_today = _consume_pages(b_a1, dm_a, [9, 10, 11, 12], posting_date=today())

    # Booklet A2: dm_a today pages 1-4
    b_a2, _ = _create_and_sell(cust_1)
    entry_a2_today = _consume_pages(b_a2, dm_a, [1, 2, 3, 4], posting_date=today())

    # Booklet C1: dm_c day -1 pages 1-8
    b_c1, _ = _create_and_sell(cust_3)
    _consume_pages(b_c1, dm_c, list(range(1, 9)), posting_date=add_to_date(today(), days=-1))

    # Booklet D1: dm_d day -4 pages 1-8
    b_d1, _ = _create_and_sell(cust_1)
    _consume_pages(b_d1, dm_d, list(range(1, 9)), posting_date=add_to_date(today(), days=-4))

    # Resolve discrepancy generated by the gap in b_a1
    disc_from_a1 = frappe.db.get_value(
        "Purisol Coupon Discrepancy",
        {"triggering_consumption_entry": entry_a1_today.name},
        "name",
    )
    disc_amount = (
        frappe.db.get_value("Purisol Coupon Discrepancy", disc_from_a1, "estimated_amount")
        if disc_from_a1 else 0
    )

    return types.SimpleNamespace(
        admin_user=SEED_ADMIN_EMAIL,
        nonadmin_user=SEED_NONADMIN_EMAIL,
        dm_a=dm_a, dm_b=dm_b, dm_c=dm_c, dm_d=dm_d,
        cust_1=cust_1, cust_2=cust_2, cust_3=cust_3,
        pl_retail=inf["pl_retail"].name,
        pl_wholesale=inf["pl_wholesale"].name,
        # R1 AS1
        dm_a_today_coupons=8,
        dm_a_today_booklets_touched=2,
        dm_a_today_discrepancies=1,
        dm_a_today_discrepancy_total=disc_amount,
        # R2 AS2
        booklet_dep=b_dep,
        booklet_sold12=b_sold12,
        booklet_sold0=b_sold0,
        # R3 AS3
        booklet_custody_5d=b_5d,
        booklet_custody_1d=b_1d,
        # R4 AS4 — 40 coupons consumed within last 7 days
        total_consumed_this_week=40,
        # Other refs
        booklet_in_stock=booklet_in_stock,
        entry_a1_today=entry_a1_today.name,
        entry_b12=entry_b12.name,
        discrepancy_from_a1=disc_from_a1,
    )


def seed_for_finance() -> types.SimpleNamespace:
    """Seed deterministic data for Bundle 2 (financial/oversight) reports.

    Creates:
    - Shared infra (idempotent)
    - 5 booklets sold at pl_retail + 2 at pl_wholesale → R7 AS3
    - DM A: 100 coupons submitted (5 entries × 20) + 4 open discrepancies → R8 rate=4.0%
    - DM B: 50 coupons submitted (2 entries × 20+10... actually 50 total), 0 discrepancies → R8 rate=0.0%
    - 4 submitted discrepancies (3 via 'None' resolution, 1 via 'Immediate Cash Payment') → R5 AS1
    - 2 liability JEs for DM A (200 + 150 = 350 total_owed) + 1 PE (100 paid) → R6 AS2
    """
    frappe.set_user("Administrator")
    inf = _shared_infra()
    dm_a = inf["dm_a"].name
    dm_b = inf["dm_b"].name
    cust_1 = inf["cust_1"].name
    cust_2 = inf["cust_2"].name
    cust_3 = inf["cust_3"].name
    pl_retail = inf["pl_retail"].name
    pl_wholesale = inf["pl_wholesale"].name

    # --- Booklet Sales Report (R7 AS3): 5 retail + 2 wholesale invoices ---
    # Retail invoices (pl_retail default for cust_1, cust_2)
    si_retail = []
    for _ in range(5):
        bk, si = _create_and_sell(cust_1)
        si_retail.append(si)
    # Wholesale invoices — need cust_3 whose default_price_list is pl_wholesale
    si_wholesale = []
    for _ in range(2):
        bk, si = _create_and_sell(cust_3)
        si_wholesale.append(si)

    # --- Discrepancy Rate (R8): DM A 100 coupons / 4 discrepancies; DM B 50 coupons / 0 ---
    # DM A: 5 booklets × 20 coupons = 100 coupons submitted
    entries_a = []
    for _ in range(5):
        bk, _ = _create_and_sell(cust_2)
        e = _consume_pages(bk, dm_a, list(range(1, 21)))
        entries_a.append((bk, e))

    # DM B: 3 booklets → 20+20+10 = 50 coupons submitted
    entries_b = []
    for pages in (list(range(1, 21)), list(range(1, 21)), list(range(1, 11))):
        bk, _ = _create_and_sell(cust_1)
        e = _consume_pages(bk, dm_b, pages)
        entries_b.append((bk, e))

    # 4 open (draft docstatus=0) discrepancies linked to dm_a's first 4 entries
    disc_a_names = []
    for i in range(4):
        bk, e = entries_a[i]
        d_name = seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=bk,
            customer=cust_2,
            triggering_entry=e.name,
            estimated_amount=50.0,
        )
        disc_a_names.append(d_name)

    # Submitted discrepancies (docstatus=1) for R5 AS1:
    # 3 resolved via "None" (Admin Error), 1 via "Immediate Cash Payment" (Paid)
    # Use fresh booklets for clean submission flow
    submitted_discs = []
    for _ in range(3):
        bk_d, _ = _create_and_sell(cust_1)
        d = seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=bk_d,
            customer=cust_1,
            estimated_amount=40.0,
        )
        resolved = _resolve_disc(d, dm_a, "None")
        submitted_discs.append(resolved.name)

    bk_paid, _ = _create_and_sell(cust_1)
    d_paid_draft = seed_open_discrepancy(
        discrepancy_type="Missing Coupons",
        booklet=bk_paid,
        customer=cust_1,
        estimated_amount=80.0,
    )
    resolved_paid = _resolve_disc(d_paid_draft, dm_b, "Immediate Cash Payment")
    submitted_discs.append(resolved_paid.name)

    # --- Liability Balance (R6 AS2): 2 JEs + 1 PE for DM A ---
    settings = frappe.get_single("Purisol Settings")
    import erpnext
    company = settings.get("company") or erpnext.get_default_company()

    def _make_liability_je(amount: float) -> str:
        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.posting_date = today()
        je.company = company
        je.user_remark = f"Seed P7 liability JE {amount}"
        je.append("accounts", {
            "account": settings.employee_liability_account,
            "party_type": "Employee",
            "party": dm_a,
            "debit_in_account_currency": amount,
            "credit_in_account_currency": 0,
        })
        je.append("accounts", {
            "account": settings.discrepancy_offset_account,
            "debit_in_account_currency": 0,
            "credit_in_account_currency": amount,
        })
        je.insert(ignore_permissions=True)
        je.submit()
        return je.name

    def _make_liability_pe(amount: float) -> str:
        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Receive"
        pe.posting_date = today()
        pe.company = company
        pe.paid_from = settings.discrepancy_offset_account
        pe.paid_to = settings.default_cash_account
        pe.paid_amount = amount
        pe.received_amount = amount
        pe.party_type = "Employee"
        pe.party = dm_a
        pe.insert(ignore_permissions=True)
        pe.submit()
        return pe.name

    je1 = _make_liability_je(200.0)
    je2 = _make_liability_je(150.0)
    pe1 = _make_liability_pe(100.0)

    return types.SimpleNamespace(
        admin_user=SEED_ADMIN_EMAIL,
        nonadmin_user=SEED_NONADMIN_EMAIL,
        dm_a=dm_a, dm_b=dm_b,
        cust_1=cust_1, cust_2=cust_2, cust_3=cust_3,
        pl_retail=pl_retail, pl_wholesale=pl_wholesale,
        # R5 AS1: 4 submitted discrepancies (3 admin-error, 1 paid)
        submitted_disc_names=submitted_discs,
        # R6 AS2: liability balance for DM A
        liability_je_names=[je1, je2],
        liability_pe_name=pe1,
        dm_a_total_owed=350.0,
        dm_a_total_paid=100.0,
        dm_a_open_balance=250.0,
        # R7 AS3: invoice names by price list
        si_retail=si_retail,
        si_wholesale=si_wholesale,
        # R8 AS4: discrepancy rates
        dm_a_coupons_submitted=100,
        dm_a_discrepancies=4,
        dm_a_discrepancy_rate=4.0,
        dm_b_coupons_submitted=50,
        dm_b_discrepancies=0,
        dm_b_discrepancy_rate=0.0,
        # Open discrepancy names (docstatus=0, for reference)
        open_disc_names=disc_a_names,
    )


def seed_for_analytics() -> types.SimpleNamespace:
    """Seed deterministic data for Bundle 3 (analytical) reports.

    Creates:
    - Shared infra (idempotent)
    - Cust-1: 3 Depleted booklets with avg_days_to_deplete=45.0 (30+45+60 days) → R9 AS1
    - Cust-2: 2 Depleted booklets with avg_days_to_deplete=15.0 (10+20 days) → R9 AS1
    - Lifecycle booklets: known creation/sold_on/depleted_on offsets → R10 AS2
      avg_generation_to_first_sale=20, avg_sale_to_depletion=40, avg_full_lifetime=60
    """
    frappe.set_user("Administrator")
    inf = _shared_infra()
    dm_a = inf["dm_a"].name
    cust_1 = inf["cust_1"].name
    cust_2 = inf["cust_2"].name

    def _make_depleted_booklet(customer: str, sold_days_ago: int, days_to_deplete: int) -> str:
        """Create a Depleted booklet with backdated sold_on and depleted_on."""
        bk, _ = _create_and_sell(customer)
        _consume_pages(bk, dm_a, list(range(1, 21)))
        sold_on = add_to_date(today(), days=-sold_days_ago)
        depleted_on = add_to_date(today(), days=-(sold_days_ago - days_to_deplete))
        frappe.db.set_value("Purisol Coupon Booklet", bk, {
            "sold_on": sold_on,
            "depleted_on": depleted_on,
        })
        return bk

    # Cust-1: avg_days_to_deplete = (30 + 45 + 60) / 3 = 45.0
    # sold_days_ago values chosen so depleted_on = sold_on + days_to_deplete
    # We need sold_on IS NOT NULL and depleted_on IS NOT NULL, both in the past
    bk_c1_1 = _make_depleted_booklet(cust_1, sold_days_ago=100, days_to_deplete=30)
    bk_c1_2 = _make_depleted_booklet(cust_1, sold_days_ago=100, days_to_deplete=45)
    bk_c1_3 = _make_depleted_booklet(cust_1, sold_days_ago=100, days_to_deplete=60)

    # Cust-2: avg_days_to_deplete = (10 + 20) / 2 = 15.0
    bk_c2_1 = _make_depleted_booklet(cust_2, sold_days_ago=50, days_to_deplete=10)
    bk_c2_2 = _make_depleted_booklet(cust_2, sold_days_ago=50, days_to_deplete=20)

    # --- Lifecycle booklets (R10 AS2) ---
    # Target: avg_generation_to_first_sale=20, avg_sale_to_depletion=40, avg_full_lifetime=60
    # 3 booklets: creation → sold_on gap of 20d; sold_on → depleted_on gap of 40d
    lifecycle_booklets = []
    for i in range(3):
        bk, _ = _create_and_sell(cust_1)
        _consume_pages(bk, dm_a, list(range(1, 21)))
        # sold_on = creation + 20 days; depleted_on = sold_on + 40 days
        # We set creation indirectly by backdating sold_on and depleted_on
        # creation is fixed by Frappe (the insert timestamp); we calculate from it
        creation = frappe.db.get_value("Purisol Coupon Booklet", bk, "creation")
        from frappe.utils import get_date_str, get_datetime
        creation_date = get_date_str(get_datetime(creation))
        sold_on = add_to_date(creation_date, days=20)
        depleted_on = add_to_date(creation_date, days=60)
        frappe.db.set_value("Purisol Coupon Booklet", bk, {
            "sold_on": sold_on,
            "depleted_on": depleted_on,
        })
        lifecycle_booklets.append(bk)

    return types.SimpleNamespace(
        admin_user=SEED_ADMIN_EMAIL,
        nonadmin_user=SEED_NONADMIN_EMAIL,
        dm_a=dm_a,
        cust_1=cust_1, cust_2=cust_2,
        # R9 AS1
        cust_1_booklets=[bk_c1_1, bk_c1_2, bk_c1_3],
        cust_1_avg_days=45.0,
        cust_2_booklets=[bk_c2_1, bk_c2_2],
        cust_2_avg_days=15.0,
        # R10 AS2
        lifecycle_booklets=lifecycle_booklets,
        avg_generation_to_first_sale=20.0,
        avg_sale_to_depletion=40.0,
        avg_full_lifetime=60.0,
    )


def seed_full_phase_7() -> types.SimpleNamespace:
    """Seed all three bundles and return a merged SimpleNamespace."""
    ops = seed_for_operations()
    fin = seed_for_finance()
    ana = seed_for_analytics()
    merged = types.SimpleNamespace(**vars(ops))
    merged.__dict__.update(
        {k: v for k, v in vars(fin).items() if k not in vars(ops)}
    )
    merged.__dict__.update(
        {k: v for k, v in vars(ana).items() if k not in merged.__dict__}
    )
    return merged
