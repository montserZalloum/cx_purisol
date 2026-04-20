import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from cx_purisol.cx_purisol.report.daily_delivery_man_summary.daily_delivery_man_summary import execute
from cx_purisol.cx_purisol.tests.fixtures import (
    configure_purisol_settings,
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
]


def _setup_infra():
    item = ensure_coupon_item()
    pl = ensure_price_list("Test-DMS-PL")
    ensure_item_price(item.name, pl.name, 100)
    customer = ensure_customer("DMS-Test-Cust", default_price_list=pl.name)
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


def _coupons_for(booklet, pages):
    rows = frappe.get_all(
        "Purisol Coupon",
        filters={"booklet": booklet},
        fields=["name", "page_number"],
    )
    pm = {r["page_number"]: r["name"] for r in rows}
    return [pm[p] for p in pages if p in pm]


def _submit_entry(delivery_man, coupon_names, posting_date=None):
    entry = frappe.get_doc({
        "doctype": "Purisol Coupon Consumption Entry",
        "posting_date": posting_date or today(),
        "posting_time": frappe.utils.nowtime(),
        "delivery_man": delivery_man,
        "coupons": [{"coupon": c} for c in coupon_names],
    })
    entry.insert(ignore_permissions=True)
    entry.submit()
    return entry


class TestDailyDeliveryManSummary(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_acceptance_scenario_1(self):
        """1 dm, 2 booklets, 2 entries today (4+4=8 coupons), 1 discrepancy → 1 row."""
        customer = _setup_infra()
        dm = make_employee("DmSummaryA")

        bk1 = _create_and_sell(customer.name)
        bk2 = _create_and_sell(customer.name)

        e1 = _submit_entry(dm.name, _coupons_for(bk1, [1, 2, 3, 4]))
        e2 = _submit_entry(dm.name, _coupons_for(bk2, [1, 2, 3, 4]))

        disc_name = seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=bk2,
            customer=customer.name,
            triggering_entry=e2.name,
            estimated_amount=120.0,
        )

        _, data = execute({"from_date": today(), "to_date": today(), "delivery_man": dm.name})

        dm_rows = [r for r in data if r["delivery_man"] == dm.name]
        self.assertEqual(len(dm_rows), 1)
        row = dm_rows[0]
        self.assertEqual(row["coupons_submitted"], 8)
        self.assertEqual(row["booklets_touched"], 2)
        self.assertEqual(row["discrepancies_count"], 1)
        self.assertAlmostEqual(float(row["discrepancy_total"]), 120.0, places=2)

    def test_filters_exclude_other_dates(self):
        """Entries outside the date range must not appear."""
        from frappe.utils import add_to_date

        customer = _setup_infra()
        dm = make_employee("DmSummaryB")

        bk = _create_and_sell(customer.name)
        yesterday = add_to_date(today(), days=-1)
        _submit_entry(dm.name, _coupons_for(bk, [1, 2]), posting_date=yesterday)

        _, data = execute({"from_date": today(), "to_date": today(), "delivery_man": dm.name})
        dm_rows = [r for r in data if r["delivery_man"] == dm.name]
        self.assertEqual(len(dm_rows), 0)

    def test_no_filters_returns_all(self):
        """Without filters the report returns rows for every day with activity."""
        customer = _setup_infra()
        dm = make_employee("DmSummaryC")

        bk = _create_and_sell(customer.name)
        _submit_entry(dm.name, _coupons_for(bk, [1, 2]))

        _, data = execute({})
        all_dms = [r["delivery_man"] for r in data]
        self.assertIn(dm.name, all_dms)
