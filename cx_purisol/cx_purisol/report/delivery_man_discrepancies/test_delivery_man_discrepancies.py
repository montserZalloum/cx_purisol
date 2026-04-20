import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from cx_purisol.cx_purisol.tests.fixtures import (
    configure_purisol_settings,
    configure_purisol_settings_accounts,
    ensure_coupon_item,
    ensure_customer,
    ensure_item_price,
    ensure_price_list,
    make_employee,
    seed_open_discrepancy,
)

test_ignore = [
    "Employee",
    "Customer",
    "Sales Invoice",
    "Journal Entry",
    "Payment Entry",
    "Purisol Coupon Booklet",
    "Purisol Coupon",
    "Purisol Coupon Consumption Entry",
    "Purisol Coupon Discrepancy",
]

_REPORT_SQL = """
SELECT
    d.name AS discrepancy,
    d.opened_on,
    d.discrepancy_type,
    d.booklet,
    (SELECT COUNT(*) FROM `tabPurisol Coupon Discrepancy Coupon` dc WHERE dc.parent = d.name) AS coupons_count,
    d.estimated_amount,
    d.status,
    d.resolution_action,
    cce.delivery_man
FROM `tabPurisol Coupon Discrepancy` d
LEFT JOIN `tabPurisol Coupon Consumption Entry` cce ON cce.name = d.triggering_consumption_entry
WHERE d.docstatus = 1
  AND (cce.name IS NULL OR cce.docstatus = 1)
  AND (%(from_date)s IS NULL OR DATE(d.opened_on) >= %(from_date)s)
  AND (%(to_date)s IS NULL OR DATE(d.opened_on) <= %(to_date)s)
  AND (%(delivery_man)s IS NULL OR cce.delivery_man = %(delivery_man)s)
  AND (%(status)s IS NULL OR %(status)s = '' OR d.status = %(status)s)
ORDER BY d.opened_on DESC
"""


def _run_report(from_date=None, to_date=None, delivery_man=None, status=None):
    return frappe.db.sql(
        _REPORT_SQL,
        {
            "from_date": from_date,
            "to_date": to_date,
            "delivery_man": delivery_man,
            "status": status,
        },
        as_dict=True,
    )


def _setup_infra():
    configure_purisol_settings_accounts()
    item = ensure_coupon_item()
    pl = ensure_price_list("Test-DMDisc-PL")
    ensure_item_price(item.name, pl.name, 100)
    customer = ensure_customer("DMDisc-Test-Cust", default_price_list=pl.name)
    configure_purisol_settings(coupon_item=item.name, default_price_list=pl.name)
    return customer


def _create_and_sell(customer_name):
    from cx_purisol.cx_purisol.api.booklet_generation import _create_booklet_and_coupons
    from cx_purisol.cx_purisol.api.sell_booklets import purisol_create_sales_invoice_for_booklets

    booklet_name, _ = _create_booklet_and_coupons(batch_id=None)
    result = purisol_create_sales_invoice_for_booklets(customer_name, [booklet_name])
    si = frappe.get_doc("Sales Invoice", result["name"])
    si.submit()
    return booklet_name


def _consume_entry(booklet_name, delivery_man, pages=(1, 2)):
    all_coupons = frappe.get_all(
        "Purisol Coupon",
        filters={"booklet": booklet_name},
        fields=["name", "page_number"],
    )
    pm = {r["page_number"]: r["name"] for r in all_coupons}
    coupon_names = [pm[p] for p in pages if p in pm]
    entry = frappe.get_doc({
        "doctype": "Purisol Coupon Consumption Entry",
        "posting_date": today(),
        "posting_time": frappe.utils.nowtime(),
        "delivery_man": delivery_man,
        "coupons": [{"coupon": c} for c in coupon_names],
    })
    entry.insert(ignore_permissions=True)
    entry.submit()
    return entry


def _resolve(disc_name, delivery_man, action):
    disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
    disc.resolution_action = action
    if action in ("Add to Liability Ledger", "Immediate Cash Payment"):
        disc.liable_delivery_man = delivery_man
    disc.save(ignore_permissions=True)
    disc.submit()
    disc.reload()
    return disc


class TestDeliveryManDiscrepancies(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_acceptance_scenario_1(self):
        """3 Admin Error + 1 Paid discrepancy across 2 DMs → 4 rows under date filter (US2 AS1)."""
        customer = _setup_infra()
        dm_a = make_employee("DiscRepA")
        dm_b = make_employee("DiscRepB")

        # DM A: 3 booklets / entries → 3 Admin Error discrepancies
        disc_admin_names = []
        for _ in range(3):
            bk = _create_and_sell(customer.name)
            entry = _consume_entry(bk, dm_a.name, pages=(1, 2))
            d = seed_open_discrepancy(
                discrepancy_type="Missing Coupons",
                booklet=bk,
                customer=customer.name,
                triggering_entry=entry.name,
                estimated_amount=40.0,
            )
            resolved = _resolve(d, dm_a.name, "None")
            disc_admin_names.append(resolved.name)

        # DM B: 1 booklet / entry → 1 Paid discrepancy
        bk_paid = _create_and_sell(customer.name)
        entry_b = _consume_entry(bk_paid, dm_b.name, pages=(1, 2))
        d_paid = seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=bk_paid,
            customer=customer.name,
            triggering_entry=entry_b.name,
            estimated_amount=80.0,
        )
        resolved_paid = _resolve(d_paid, dm_b.name, "Immediate Cash Payment")

        all_names = set(disc_admin_names) | {resolved_paid.name}

        rows = _run_report(from_date=today(), to_date=today())
        returned_ids = {r["discrepancy"] for r in rows}

        for name in all_names:
            self.assertIn(name, returned_ids)

        # Verify statuses
        status_map = {r["discrepancy"]: r["status"] for r in rows}
        for name in disc_admin_names:
            self.assertEqual(status_map[name], "Resolved - Admin Error")
        self.assertEqual(status_map[resolved_paid.name], "Resolved - Paid")

        # Verify amounts
        amount_map = {r["discrepancy"]: float(r["estimated_amount"]) for r in rows}
        for name in disc_admin_names:
            self.assertAlmostEqual(amount_map[name], 40.0, places=2)
        self.assertAlmostEqual(amount_map[resolved_paid.name], 80.0, places=2)

    def test_delivery_man_filter(self):
        """Filter by delivery_man returns only that DM's discrepancies."""
        customer = _setup_infra()
        dm_a = make_employee("DiscFilterA")
        dm_b = make_employee("DiscFilterB")

        bk_a = _create_and_sell(customer.name)
        entry_a = _consume_entry(bk_a, dm_a.name, pages=(1, 2))
        d_a = seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=bk_a,
            customer=customer.name,
            triggering_entry=entry_a.name,
            estimated_amount=30.0,
        )
        _resolve(d_a, dm_a.name, "None")

        bk_b = _create_and_sell(customer.name)
        entry_b = _consume_entry(bk_b, dm_b.name, pages=(1, 2))
        d_b = seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=bk_b,
            customer=customer.name,
            triggering_entry=entry_b.name,
            estimated_amount=50.0,
        )
        _resolve(d_b, dm_b.name, "None")

        rows_a = _run_report(delivery_man=dm_a.name)
        dms_a = {r["delivery_man"] for r in rows_a}
        self.assertIn(dm_a.name, dms_a)
        self.assertNotIn(dm_b.name, dms_a)

        rows_b = _run_report(delivery_man=dm_b.name)
        dms_b = {r["delivery_man"] for r in rows_b}
        self.assertIn(dm_b.name, dms_b)
        self.assertNotIn(dm_a.name, dms_b)

    def test_status_filter(self):
        """Status filter narrows to matching status only."""
        customer = _setup_infra()
        dm = make_employee("DiscStatusTest")

        bk = _create_and_sell(customer.name)
        entry = _consume_entry(bk, dm.name, pages=(1, 2))
        d = seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=bk,
            customer=customer.name,
            triggering_entry=entry.name,
            estimated_amount=20.0,
        )
        resolved = _resolve(d, dm.name, "None")

        rows_admin = _run_report(status="Resolved - Admin Error")
        ids = {r["discrepancy"] for r in rows_admin}
        self.assertIn(resolved.name, ids)

        rows_paid = _run_report(status="Resolved - Paid")
        ids_paid = {r["discrepancy"] for r in rows_paid}
        self.assertNotIn(resolved.name, ids_paid)
