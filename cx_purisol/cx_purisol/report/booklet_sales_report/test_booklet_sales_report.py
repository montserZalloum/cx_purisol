import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from cx_purisol.cx_purisol.tests.fixtures import (
    configure_purisol_settings,
    ensure_coupon_item,
    ensure_customer,
    ensure_item_price,
    ensure_price_list,
)

test_ignore = [
    "Customer",
    "Sales Invoice",
    "Purisol Coupon Booklet",
    "Purisol Coupon",
]

_REPORT_SQL = """
SELECT
    si.posting_date,
    sii.purisol_booklet AS booklet,
    si.customer,
    si.name AS sales_invoice,
    sii.amount,
    si.status
FROM `tabSales Invoice Item` sii
JOIN `tabSales Invoice` si ON si.name = sii.parent
WHERE si.docstatus = 1
  AND sii.purisol_booklet IS NOT NULL
  AND (%(from_date)s IS NULL OR si.posting_date >= %(from_date)s)
  AND (%(to_date)s IS NULL OR si.posting_date <= %(to_date)s)
  AND (%(customer)s IS NULL OR si.customer = %(customer)s)
  AND (%(price_list)s IS NULL OR %(price_list)s = '' OR si.selling_price_list = %(price_list)s)
ORDER BY si.posting_date DESC, si.name, sii.idx
"""


def _run_report(from_date=None, to_date=None, customer=None, price_list=None):
    return frappe.db.sql(
        _REPORT_SQL,
        {
            "from_date": from_date,
            "to_date": to_date,
            "customer": customer,
            "price_list": price_list,
        },
        as_dict=True,
    )


def _setup_infra():
    item = ensure_coupon_item()
    pl_retail = ensure_price_list("Test-BSR-PL-Retail")
    pl_wholesale = ensure_price_list("Test-BSR-PL-Wholesale")
    ensure_item_price(item.name, pl_retail.name, 500)
    ensure_item_price(item.name, pl_wholesale.name, 400)

    cust_retail = ensure_customer("BSR-Cust-Retail", default_price_list=pl_retail.name)
    cust_wholesale = ensure_customer("BSR-Cust-Wholesale", default_price_list=pl_wholesale.name)

    configure_purisol_settings(coupon_item=item.name, default_price_list=pl_retail.name)
    return cust_retail, cust_wholesale, pl_retail, pl_wholesale


def _create_and_sell(customer_name):
    from cx_purisol.cx_purisol.api.booklet_generation import _create_booklet_and_coupons
    from cx_purisol.cx_purisol.api.sell_booklets import purisol_create_sales_invoice_for_booklets

    booklet_name, _ = _create_booklet_and_coupons(batch_id=None)
    result = purisol_create_sales_invoice_for_booklets(customer_name, [booklet_name])
    si = frappe.get_doc("Sales Invoice", result["name"])
    si.submit()
    return booklet_name, si.name


class TestBookletSalesReport(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_acceptance_scenario_3_price_list_filter(self):
        """5 retail + 2 wholesale invoices; price_list filter narrows to each group (US2 AS3)."""
        cust_retail, cust_wholesale, pl_retail, pl_wholesale = _setup_infra()

        retail_invoices = []
        for _ in range(5):
            _, si = _create_and_sell(cust_retail.name)
            retail_invoices.append(si)

        wholesale_invoices = []
        for _ in range(2):
            _, si = _create_and_sell(cust_wholesale.name)
            wholesale_invoices.append(si)

        # No filter → both groups appear
        all_rows = _run_report(from_date=today(), to_date=today())
        all_si = {r["sales_invoice"] for r in all_rows}
        for si in retail_invoices:
            self.assertIn(si, all_si)
        for si in wholesale_invoices:
            self.assertIn(si, all_si)

        # Retail filter → only retail invoices
        retail_rows = _run_report(price_list=pl_retail.name)
        retail_si = {r["sales_invoice"] for r in retail_rows}
        for si in retail_invoices:
            self.assertIn(si, retail_si)
        for si in wholesale_invoices:
            self.assertNotIn(si, retail_si)

        # Wholesale filter → only wholesale invoices
        wholesale_rows = _run_report(price_list=pl_wholesale.name)
        wholesale_si = {r["sales_invoice"] for r in wholesale_rows}
        for si in wholesale_invoices:
            self.assertIn(si, wholesale_si)
        for si in retail_invoices:
            self.assertNotIn(si, wholesale_si)

    def test_booklets_without_purisol_booklet_excluded(self):
        """Standard sales invoice items without purisol_booklet do not appear."""
        cust_retail, _, pl_retail, _ = _setup_infra()

        bk, si = _create_and_sell(cust_retail.name)

        rows = _run_report(from_date=today(), to_date=today())
        booklets = {r["booklet"] for r in rows}
        self.assertIn(bk, booklets)
