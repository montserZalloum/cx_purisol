import frappe
from frappe.model.naming import make_autoname
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.tests.fixtures import ensure_customer

test_ignore = [
    "Customer",
    "Purisol Coupon Booklet",
]

_REPORT_SQL = """
SELECT customer, total_remaining
FROM (
    SELECT
        b.customer,
        SUM(b.remaining_count) AS total_remaining
    FROM `tabPurisol Coupon Booklet` b
    WHERE b.status = 'Sold'
      AND b.customer IS NOT NULL
    GROUP BY b.customer
) agg
WHERE total_remaining <= COALESCE(
    (SELECT CAST(value AS UNSIGNED) FROM `tabSingles`
     WHERE doctype = 'Purisol Settings' AND field = 'customer_low_stock_threshold'),
    3
)
ORDER BY total_remaining ASC
LIMIT 10
"""


def _run_report():
    return frappe.db.sql(_REPORT_SQL, as_dict=True)


def _make_sold_booklet(customer_name, remaining):
    booklet_name = make_autoname("TLC-.#####")
    booklet = frappe.get_doc({
        "doctype": "Purisol Coupon Booklet",
        "booklet_number": booklet_name,
        "status": "Sold",
        "customer": customer_name,
        "total_coupons": 20,
        "consumed_count": max(0, 20 - remaining),
        "remaining_count": remaining,
    })
    booklet.flags.ignore_permissions = True
    booklet.flags.ignore_mandatory = True
    booklet.insert(ignore_permissions=True, set_name=booklet_name)
    return booklet_name


class TestCustomersLowOnCoupons(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._orig_threshold = (
            frappe.db.get_single_value("Purisol Settings", "customer_low_stock_threshold") or 3
        )

    def tearDown(self):
        frappe.db.set_single_value(
            "Purisol Settings", "customer_low_stock_threshold", self._orig_threshold
        )

    def test_threshold_edge_case(self):
        """Customers with totals 0/1/2/3 qualify at threshold=3; total=4 is excluded."""
        frappe.db.set_single_value("Purisol Settings", "customer_low_stock_threshold", 3)
        for v in range(5):
            cust = ensure_customer(f"TLC-Edge-{v}")
            _make_sold_booklet(cust.name, v)

        rows = _run_report()
        customer_totals = {r["customer"]: int(r["total_remaining"]) for r in rows}

        for v in range(4):  # 0, 1, 2, 3 all qualify
            self.assertIn(f"TLC-Edge-{v}", customer_totals)
        self.assertNotIn("TLC-Edge-4", customer_totals)

    def test_limit_10_cap(self):
        """When 12 customers qualify, at most 10 rows are returned (lowest-first)."""
        frappe.db.set_single_value("Purisol Settings", "customer_low_stock_threshold", 20)
        for i in range(12):
            cust = ensure_customer(f"TLC-Lim-{i:02d}")
            _make_sold_booklet(cust.name, i + 1)  # totals 1..12, all <= 20

        rows = _run_report()
        self.assertLessEqual(len(rows), 10)
        if len(rows) >= 2:
            totals = [int(r["total_remaining"]) for r in rows]
            self.assertEqual(totals, sorted(totals))

    def test_depleted_excluded(self):
        """A customer whose only booklet is Depleted does not appear."""
        cust = ensure_customer("TLC-Depleted-Cust")
        bk_name = make_autoname("TLC-.#####")
        bk = frappe.get_doc({
            "doctype": "Purisol Coupon Booklet",
            "booklet_number": bk_name,
            "status": "Depleted",
            "customer": cust.name,
            "total_coupons": 20,
            "consumed_count": 20,
            "remaining_count": 0,
        })
        bk.flags.ignore_permissions = True
        bk.flags.ignore_mandatory = True
        bk.insert(ignore_permissions=True, set_name=bk_name)

        frappe.db.set_single_value("Purisol Settings", "customer_low_stock_threshold", 5)
        rows = _run_report()
        customers = [r["customer"] for r in rows]
        self.assertNotIn(cust.name, customers)

    def test_live_threshold_read(self):
        """Changing Purisol Settings threshold immediately expands report results."""
        cust3 = ensure_customer("TLC-Live-3")
        cust4 = ensure_customer("TLC-Live-4")
        cust5 = ensure_customer("TLC-Live-5")
        _make_sold_booklet(cust3.name, 3)
        _make_sold_booklet(cust4.name, 4)
        _make_sold_booklet(cust5.name, 5)

        frappe.db.set_single_value("Purisol Settings", "customer_low_stock_threshold", 3)
        rows_at_3 = {r["customer"] for r in _run_report()}
        self.assertIn(cust3.name, rows_at_3)
        self.assertNotIn(cust4.name, rows_at_3)
        self.assertNotIn(cust5.name, rows_at_3)

        frappe.db.set_single_value("Purisol Settings", "customer_low_stock_threshold", 5)
        rows_at_5 = {r["customer"] for r in _run_report()}
        self.assertIn(cust3.name, rows_at_5)
        self.assertIn(cust4.name, rows_at_5)
        self.assertIn(cust5.name, rows_at_5)

    def test_zero_sold_booklets_excluded(self):
        """A customer with no Sold booklets does not appear in results."""
        cust = ensure_customer("TLC-NoSold-Cust")
        frappe.db.set_single_value("Purisol Settings", "customer_low_stock_threshold", 10)
        rows = _run_report()
        customers = [r["customer"] for r in rows]
        self.assertNotIn(cust.name, customers)
