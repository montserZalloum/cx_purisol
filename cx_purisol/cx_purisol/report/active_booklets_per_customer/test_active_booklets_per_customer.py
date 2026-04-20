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
        b.name AS booklet,
        b.status,
        b.consumed_count,
        b.remaining_count,
        b.sold_on,
        DATEDIFF(NOW(), b.sold_on) AS days_since_sale
    FROM `tabPurisol Coupon Booklet` b
    WHERE b.status IN ('Sold', 'Depleted')
      AND b.customer IS NOT NULL
      AND (%(customer)s IS NULL OR %(customer)s = '' OR b.customer = %(customer)s)
    ORDER BY b.customer, b.sold_on DESC
"""


def _run_report(customer=None):
    return frappe.db.sql(_REPORT_SQL, {"customer": customer}, as_dict=True)


def _setup_infra():
    item = ensure_coupon_item()
    pl = ensure_price_list("Test-ABPC-PL")
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


class TestActiveBookletsPerCustomer(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_acceptance_scenario_2(self):
        """Cust-2 has 3 booklets: Depleted(20/0), Sold(12/8), Sold(0/20) → 3 rows."""
        item, pl = _setup_infra()
        customer = ensure_customer("ABPC-Test-Cust2", default_price_list=pl.name)
        dm = make_employee("AbpcDmA")

        # Booklet 1: Depleted — consume all 20 pages
        b_dep = _create_and_sell(customer.name)
        coupons_dep = frappe.get_all(
            "Purisol Coupon", filters={"booklet": b_dep},
            fields=["name", "page_number"], order_by="page_number"
        )
        entry_dep = frappe.get_doc({
            "doctype": "Purisol Coupon Consumption Entry",
            "posting_date": today(),
            "posting_time": frappe.utils.nowtime(),
            "delivery_man": dm.name,
            "coupons": [{"coupon": c["name"]} for c in coupons_dep],
        })
        entry_dep.insert(ignore_permissions=True)
        entry_dep.submit()
        frappe.db.set_value("Purisol Coupon Booklet", b_dep, {
            "sold_on": add_to_date(today(), days=-45),
            "depleted_on": add_to_date(today(), days=-15),
        })

        # Booklet 2: Sold, 12/20 consumed
        b_sold12 = _create_and_sell(customer.name)
        coupons_12 = frappe.get_all(
            "Purisol Coupon", filters={"booklet": b_sold12},
            fields=["name", "page_number"], order_by="page_number"
        )[:12]
        entry_12 = frappe.get_doc({
            "doctype": "Purisol Coupon Consumption Entry",
            "posting_date": today(),
            "posting_time": frappe.utils.nowtime(),
            "delivery_man": dm.name,
            "coupons": [{"coupon": c["name"]} for c in coupons_12],
        })
        entry_12.insert(ignore_permissions=True)
        entry_12.submit()
        frappe.db.set_value("Purisol Coupon Booklet", b_sold12, "sold_on", add_to_date(today(), days=-10))

        # Booklet 3: Sold, 0/20 consumed
        b_sold0 = _create_and_sell(customer.name)
        frappe.db.set_value("Purisol Coupon Booklet", b_sold0, "sold_on", add_to_date(today(), days=-5))

        rows = _run_report(customer=customer.name)
        self.assertEqual(len(rows), 3)

        booklet_map = {r["booklet"]: r for r in rows}
        self.assertIn(b_dep, booklet_map)
        self.assertIn(b_sold12, booklet_map)
        self.assertIn(b_sold0, booklet_map)

        dep_row = booklet_map[b_dep]
        self.assertEqual(dep_row["status"], "Depleted")
        self.assertEqual(dep_row["consumed_count"], 20)
        self.assertEqual(dep_row["remaining_count"], 0)
        self.assertGreaterEqual(dep_row["days_since_sale"], 44)

        sold12_row = booklet_map[b_sold12]
        self.assertEqual(sold12_row["status"], "Sold")
        self.assertEqual(sold12_row["consumed_count"], 12)
        self.assertEqual(sold12_row["remaining_count"], 8)
        self.assertGreaterEqual(sold12_row["days_since_sale"], 9)

        sold0_row = booklet_map[b_sold0]
        self.assertEqual(sold0_row["status"], "Sold")
        self.assertEqual(sold0_row["consumed_count"], 0)
        self.assertEqual(sold0_row["remaining_count"], 20)
        self.assertGreaterEqual(sold0_row["days_since_sale"], 4)

    def test_customer_filter(self):
        """Customer filter narrows rows to that customer only."""
        item, pl = _setup_infra()
        cust_a = ensure_customer("ABPC-FilterA", default_price_list=pl.name)
        cust_b = ensure_customer("ABPC-FilterB", default_price_list=pl.name)

        _create_and_sell(cust_a.name)
        _create_and_sell(cust_b.name)

        rows_a = _run_report(customer=cust_a.name)
        rows_b = _run_report(customer=cust_b.name)

        self.assertTrue(all(r["customer"] == cust_a.name for r in rows_a))
        self.assertTrue(all(r["customer"] == cust_b.name for r in rows_b))

    def test_in_stock_booklets_excluded(self):
        """In Stock booklets must not appear in the report."""
        from cx_purisol.cx_purisol.tests.fixtures import make_booklet_in_stock

        in_stock = make_booklet_in_stock().name
        rows = _run_report()
        booklet_names = {r["booklet"] for r in rows}
        self.assertNotIn(in_stock, booklet_names)
