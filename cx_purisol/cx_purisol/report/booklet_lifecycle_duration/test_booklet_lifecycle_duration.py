import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, today

from cx_purisol.cx_purisol.tests.fixtures import (
    configure_purisol_settings,
    ensure_coupon_item,
    ensure_customer,
    ensure_item_price,
    ensure_price_list,
    make_employee,
)

test_ignore = [
    "Employee",
    "Customer",
    "Sales Invoice",
    "Purisol Coupon Booklet",
    "Purisol Coupon",
    "Purisol Coupon Consumption Entry",
]


def _run_report():
    from cx_purisol.cx_purisol.report.booklet_lifecycle_duration.booklet_lifecycle_duration import execute

    _, data = execute()
    return data[0] if data else {}


def _setup_infra():
    item = ensure_coupon_item()
    pl = ensure_price_list("Test-BLD-PL")
    ensure_item_price(item.name, pl.name, 100)
    configure_purisol_settings(coupon_item=item.name, default_price_list=pl.name)
    return item, pl


def _create_and_sell(customer_name):
    from cx_purisol.cx_purisol.api.booklet_generation import _create_booklet_and_coupons
    from cx_purisol.cx_purisol.api.sell_booklets import purisol_create_sales_invoice_for_booklets

    booklet_name, _ = _create_booklet_and_coupons(batch_id=None)
    result = purisol_create_sales_invoice_for_booklets(customer_name, [booklet_name])
    si = frappe.get_doc("Sales Invoice", result["name"])
    si.submit()
    return booklet_name


def _deplete_with_offsets(booklet_name, delivery_man, gen_to_sale_days, sale_to_deplete_days):
    """Consume all coupons and set sold_on/depleted_on relative to creation."""
    coupons = frappe.get_all("Purisol Coupon", filters={"booklet": booklet_name}, fields=["name"])
    entry = frappe.get_doc({
        "doctype": "Purisol Coupon Consumption Entry",
        "posting_date": today(),
        "posting_time": frappe.utils.nowtime(),
        "delivery_man": delivery_man,
        "coupons": [{"coupon": c["name"]} for c in coupons],
    })
    entry.insert(ignore_permissions=True)
    entry.submit()

    from frappe.utils import get_date_str, get_datetime
    creation = frappe.db.get_value("Purisol Coupon Booklet", booklet_name, "creation")
    creation_date = get_date_str(get_datetime(creation))
    sold_on = add_to_date(creation_date, days=gen_to_sale_days)
    depleted_on = add_to_date(creation_date, days=gen_to_sale_days + sale_to_deplete_days)
    frappe.db.set_value("Purisol Coupon Booklet", booklet_name, {
        "sold_on": sold_on,
        "depleted_on": depleted_on,
    })


class TestBookletLifecycleDuration(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_acceptance_scenario_2(self):
        """3 booklets with gen→sale=20d, sale→deplete=40d → averages 20/40/60."""
        item, pl = _setup_infra()
        cust = ensure_customer("BLD-Test-C1", default_price_list=pl.name)
        dm = make_employee("BldDmA")

        for _ in range(3):
            bk = _create_and_sell(cust.name)
            _deplete_with_offsets(bk, dm.name, gen_to_sale_days=20, sale_to_deplete_days=40)

        row = _run_report()
        self.assertIsNotNone(row.get("avg_generation_to_first_sale"))
        self.assertIsNotNone(row.get("avg_sale_to_depletion"))
        self.assertIsNotNone(row.get("avg_full_lifetime"))
        self.assertAlmostEqual(float(row["avg_generation_to_first_sale"]), 20.0, delta=1.0)
        self.assertAlmostEqual(float(row["avg_sale_to_depletion"]), 40.0, delta=1.0)
        self.assertAlmostEqual(float(row["avg_full_lifetime"]), 60.0, delta=1.0)

    def test_null_averages_when_no_depleted_booklets(self):
        """When no booklets are Depleted, avg_sale_to_depletion and avg_full_lifetime are null."""
        item, pl = _setup_infra()
        cust = ensure_customer("BLD-NoDepleted", default_price_list=pl.name)

        bk = _create_and_sell(cust.name)
        frappe.db.set_value("Purisol Coupon Booklet", bk, "sold_on", add_to_date(today(), days=-5))

        row = _run_report()
        self.assertIsNone(row.get("avg_sale_to_depletion"))
        self.assertIsNone(row.get("avg_full_lifetime"))
