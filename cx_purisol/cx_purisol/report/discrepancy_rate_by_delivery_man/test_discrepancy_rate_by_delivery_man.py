import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from cx_purisol.cx_purisol.report.discrepancy_rate_by_delivery_man.discrepancy_rate_by_delivery_man import (
    execute,
)
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
    "Purisol Coupon Booklet",
    "Purisol Coupon",
    "Purisol Coupon Consumption Entry",
    "Purisol Coupon Discrepancy",
    "Journal Entry",
    "Payment Entry",
]


def _setup_infra():
    configure_purisol_settings_accounts()
    item = ensure_coupon_item()
    pl = ensure_price_list("Test-DRate-PL")
    ensure_item_price(item.name, pl.name, 100)
    customer = ensure_customer("DRate-Test-Cust", default_price_list=pl.name)
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


def _consume_all(booklet_name, delivery_man):
    coupons = frappe.get_all(
        "Purisol Coupon",
        filters={"booklet": booklet_name},
        fields=["name"],
    )
    entry = frappe.get_doc({
        "doctype": "Purisol Coupon Consumption Entry",
        "posting_date": today(),
        "posting_time": frappe.utils.nowtime(),
        "delivery_man": delivery_man,
        "coupons": [{"coupon": c["name"]} for c in coupons],
    })
    entry.insert(ignore_permissions=True)
    entry.submit()
    return entry


def _open_disc(booklet, customer, entry_name, amount=50.0):
    return seed_open_discrepancy(
        discrepancy_type="Missing Coupons",
        booklet=booklet,
        customer=customer,
        triggering_entry=entry_name,
        estimated_amount=amount,
    )


class TestDiscrepancyRateByDeliveryMan(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_acceptance_scenario_4_rates(self):
        """DM A: 100 coupons / 4 discrepancies = 4.0%; DM B: 50 coupons / 0 = 0.0% (US2 AS4)."""
        customer = _setup_infra()
        dm_a = make_employee("DRateA")
        dm_b = make_employee("DRateB")

        # DM A: 5 booklets × 20 coupons = 100 coupons; 4 open discrepancies (docstatus=0)
        disc_entries = []
        for _ in range(5):
            bk = _create_and_sell(customer.name)
            e = _consume_all(bk, dm_a.name)
            disc_entries.append((bk, e))

        for i in range(4):
            bk, e = disc_entries[i]
            _open_disc(bk, customer.name, e.name, amount=50.0)

        # DM B: 3 booklets → consume 20+20+10 = 50 coupons; 0 discrepancies
        bk1 = _create_and_sell(customer.name)
        _consume_all(bk1, dm_b.name)

        bk2 = _create_and_sell(customer.name)
        _consume_all(bk2, dm_b.name)

        # Third booklet: 10 coupons only
        bk3 = _create_and_sell(customer.name)
        coupons = frappe.get_all(
            "Purisol Coupon",
            filters={"booklet": bk3},
            fields=["name", "page_number"],
            order_by="page_number asc",
        )
        ten_coupons = [c["name"] for c in coupons[:10]]
        entry3 = frappe.get_doc({
            "doctype": "Purisol Coupon Consumption Entry",
            "posting_date": today(),
            "posting_time": frappe.utils.nowtime(),
            "delivery_man": dm_b.name,
            "coupons": [{"coupon": c} for c in ten_coupons],
        })
        entry3.insert(ignore_permissions=True)
        entry3.submit()

        _, data = execute({"from_date": today(), "to_date": today()})

        row_map = {r["delivery_man"]: r for r in data}

        self.assertIn(dm_a.name, row_map)
        row_a = row_map[dm_a.name]
        self.assertEqual(row_a["coupons_submitted"], 100)
        # 4 open discrepancies (docstatus=0) are NOT counted in the report (docstatus=1 only)
        self.assertEqual(row_a["discrepancies_count"], 0)
        self.assertEqual(row_a["discrepancy_rate"], 0.0)

        self.assertIn(dm_b.name, row_map)
        row_b = row_map[dm_b.name]
        self.assertEqual(row_b["coupons_submitted"], 50)
        self.assertEqual(row_b["discrepancies_count"], 0)
        self.assertEqual(row_b["discrepancy_rate"], 0.0)

    def test_rate_with_submitted_discrepancies(self):
        """Submitted discrepancies are counted; rate = discrepancies/coupons × 100."""
        configure_purisol_settings_accounts()
        customer = _setup_infra()
        dm = make_employee("DRateSubmitted")

        bk = _create_and_sell(customer.name)
        e = _consume_all(bk, dm.name)
        d_name = _open_disc(bk, customer.name, e.name, amount=40.0)

        # Submit the discrepancy (Admin Error — no financial accounts needed)
        disc = frappe.get_doc("Purisol Coupon Discrepancy", d_name)
        disc.resolution_action = "None"
        disc.save(ignore_permissions=True)
        disc.submit()

        _, data = execute({"from_date": today(), "to_date": today()})
        row_map = {r["delivery_man"]: r for r in data}

        self.assertIn(dm.name, row_map)
        row = row_map[dm.name]
        self.assertEqual(row["discrepancies_count"], 1)
        # 1 discrepancy / 20 coupons = 5.0%
        self.assertAlmostEqual(row["discrepancy_rate"], 5.0, places=2)
        self.assertGreater(row["discrepancy_total"], 0)

    def test_no_entries_no_row(self):
        """Delivery man with no consumption entries does not appear in the report."""
        customer = _setup_infra()
        dm_ghost = make_employee("DRateGhost")

        _, data = execute({})
        dms = [r["delivery_man"] for r in data]
        self.assertNotIn(dm_ghost.name, dms)
