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
        c.consumed_on,
        c.name AS coupon,
        c.booklet,
        b.customer,
        c.consumed_by_delivery_man AS delivery_man,
        c.consumption_entry
    FROM `tabPurisol Coupon` c
    JOIN `tabPurisol Coupon Booklet` b ON b.name = c.booklet
    JOIN `tabPurisol Coupon Consumption Entry` cce ON cce.name = c.consumption_entry
    WHERE c.status = 'Consumed'
      AND cce.docstatus = 1
      AND (%(from_date)s IS NULL OR DATE(c.consumed_on) >= %(from_date)s)
      AND (%(to_date)s IS NULL OR DATE(c.consumed_on) <= %(to_date)s)
      AND (%(delivery_man)s IS NULL OR c.consumed_by_delivery_man = %(delivery_man)s)
      AND (%(customer)s IS NULL OR b.customer = %(customer)s)
      AND (%(booklet)s IS NULL OR c.booklet = %(booklet)s)
    ORDER BY c.consumed_on DESC, c.name
"""


def _run_report(from_date=None, to_date=None, delivery_man=None, customer=None, booklet=None):
    return frappe.db.sql(
        _REPORT_SQL,
        {
            "from_date": from_date,
            "to_date": to_date,
            "delivery_man": delivery_man,
            "customer": customer,
            "booklet": booklet,
        },
        as_dict=True,
    )


def _setup_infra():
    item = ensure_coupon_item()
    pl = ensure_price_list("Test-CCL-PL")
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


def _consume_all(booklet_name, delivery_man, posting_date=None):
    coupons = frappe.get_all(
        "Purisol Coupon", filters={"booklet": booklet_name}, fields=["name"]
    )
    entry = frappe.get_doc({
        "doctype": "Purisol Coupon Consumption Entry",
        "posting_date": posting_date or today(),
        "posting_time": frappe.utils.nowtime(),
        "delivery_man": delivery_man,
        "coupons": [{"coupon": c["name"]} for c in coupons],
    })
    entry.insert(ignore_permissions=True)
    entry.submit()
    return entry


class TestCouponConsumptionLog(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_acceptance_scenario_4(self):
        """40 coupons consumed within a week → exactly 40 rows for week-range filter."""
        item, pl = _setup_infra()
        customer = ensure_customer("CCL-Test-Cust", default_price_list=pl.name)
        dm = make_employee("CclDmA")

        # 2 booklets × 20 coupons = 40 consumed within the last 7 days
        bk1 = _create_and_sell(customer.name)
        bk2 = _create_and_sell(customer.name)
        _consume_all(bk1, dm.name, posting_date=add_to_date(today(), days=-3))
        _consume_all(bk2, dm.name, posting_date=add_to_date(today(), days=-1))

        week_ago = add_to_date(today(), days=-7)
        rows = _run_report(from_date=week_ago, to_date=today(), customer=customer.name)

        self.assertEqual(len(rows), 40)

        # Verify all expected columns are present
        for row in rows:
            self.assertIn("consumed_on", row)
            self.assertIn("coupon", row)
            self.assertIn("booklet", row)
            self.assertIn("customer", row)
            self.assertIn("delivery_man", row)
            self.assertIn("consumption_entry", row)
            self.assertEqual(row["customer"], customer.name)
            self.assertEqual(row["delivery_man"], dm.name)

    def test_date_filter_excludes_outside_range(self):
        """Coupons consumed before from_date must not appear."""
        item, pl = _setup_infra()
        customer = ensure_customer("CCL-Filter-Cust", default_price_list=pl.name)
        dm = make_employee("CclDmB")

        bk = _create_and_sell(customer.name)
        old_date = add_to_date(today(), days=-30)
        _consume_all(bk, dm.name, posting_date=old_date)

        rows = _run_report(
            from_date=add_to_date(today(), days=-7),
            to_date=today(),
            customer=customer.name,
        )
        self.assertEqual(len(rows), 0)

    def test_booklet_filter(self):
        """Booklet filter narrows results to that booklet only."""
        item, pl = _setup_infra()
        customer = ensure_customer("CCL-Bk-Cust", default_price_list=pl.name)
        dm = make_employee("CclDmC")

        bk1 = _create_and_sell(customer.name)
        bk2 = _create_and_sell(customer.name)
        _consume_all(bk1, dm.name)
        _consume_all(bk2, dm.name)

        rows = _run_report(booklet=bk1)
        self.assertTrue(all(r["booklet"] == bk1 for r in rows))
        self.assertEqual(len(rows), 20)
