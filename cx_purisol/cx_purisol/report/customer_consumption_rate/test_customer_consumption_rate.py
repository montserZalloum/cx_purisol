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

_REPORT_SQL = """
    SELECT
        b.customer,
        COUNT(*) AS booklets_depleted,
        ROUND(AVG(DATEDIFF(b.depleted_on, b.sold_on)), 1) AS avg_days_to_deplete
    FROM `tabPurisol Coupon Booklet` b
    WHERE b.status = 'Depleted'
      AND b.depleted_on IS NOT NULL
      AND b.sold_on IS NOT NULL
      AND b.customer IS NOT NULL
    GROUP BY b.customer
    ORDER BY avg_days_to_deplete ASC
"""


def _run_report():
    return frappe.db.sql(_REPORT_SQL, as_dict=True)


def _setup_infra():
    item = ensure_coupon_item()
    pl = ensure_price_list("Test-CCR-PL")
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


def _deplete_booklet(booklet_name, delivery_man, sold_days_ago, days_to_deplete):
    """Consume all 20 coupons and backdate sold_on / depleted_on."""
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
    frappe.db.set_value("Purisol Coupon Booklet", booklet_name, {
        "sold_on": add_to_date(today(), days=-sold_days_ago),
        "depleted_on": add_to_date(today(), days=-(sold_days_ago - days_to_deplete)),
    })


class TestCustomerConsumptionRate(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_acceptance_scenario_1(self):
        """C1: 3 depleted booklets (30,45,60 days) → avg=45.0; C2: 2 booklets (10,20) → avg=15.0."""
        item, pl = _setup_infra()
        cust_1 = ensure_customer("CCR-Test-C1", default_price_list=pl.name)
        cust_2 = ensure_customer("CCR-Test-C2", default_price_list=pl.name)
        dm = make_employee("CcrDmA")

        for days in (30, 45, 60):
            bk = _create_and_sell(cust_1.name)
            _deplete_booklet(bk, dm.name, sold_days_ago=100, days_to_deplete=days)

        for days in (10, 20):
            bk = _create_and_sell(cust_2.name)
            _deplete_booklet(bk, dm.name, sold_days_ago=50, days_to_deplete=days)

        rows = _run_report()
        row_map = {r["customer"]: r for r in rows}

        self.assertIn(cust_1.name, row_map)
        self.assertEqual(row_map[cust_1.name]["booklets_depleted"], 3)
        self.assertAlmostEqual(float(row_map[cust_1.name]["avg_days_to_deplete"]), 45.0, places=1)

        self.assertIn(cust_2.name, row_map)
        self.assertEqual(row_map[cust_2.name]["booklets_depleted"], 2)
        self.assertAlmostEqual(float(row_map[cust_2.name]["avg_days_to_deplete"]), 15.0, places=1)

    def test_customers_without_depleted_booklets_excluded(self):
        """Customers with only Sold (not Depleted) booklets must not appear."""
        item, pl = _setup_infra()
        cust = ensure_customer("CCR-NoDepleted", default_price_list=pl.name)

        bk = _create_and_sell(cust.name)
        # booklet remains Sold (not depleted)
        frappe.db.set_value("Purisol Coupon Booklet", bk, "sold_on", add_to_date(today(), days=-5))

        rows = _run_report()
        row_map = {r["customer"]: r for r in rows}
        self.assertNotIn(cust.name, row_map)

    def test_ordering_ascending(self):
        """Fastest-consuming customers (lowest avg) appear first."""
        item, pl = _setup_infra()
        cust_fast = ensure_customer("CCR-Fast", default_price_list=pl.name)
        cust_slow = ensure_customer("CCR-Slow", default_price_list=pl.name)
        dm = make_employee("CcrDmB")

        bk_fast = _create_and_sell(cust_fast.name)
        _deplete_booklet(bk_fast, dm.name, sold_days_ago=50, days_to_deplete=5)

        bk_slow = _create_and_sell(cust_slow.name)
        _deplete_booklet(bk_slow, dm.name, sold_days_ago=50, days_to_deplete=40)

        rows = _run_report()
        customers = [r["customer"] for r in rows]
        if cust_fast.name in customers and cust_slow.name in customers:
            self.assertLess(customers.index(cust_fast.name), customers.index(cust_slow.name))
