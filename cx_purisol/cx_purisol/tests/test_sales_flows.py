import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.api.sell_booklets import purisol_create_sales_invoice_for_booklets
from cx_purisol.cx_purisol.tests.fixtures import (
    configure_purisol_settings,
    ensure_coupon_item,
    ensure_customer,
    ensure_item_price,
    ensure_price_list,
    make_booklet_in_stock,
    make_employee,
    submit_assign,
)

test_ignore = ["Customer", "Employee", "Sales Invoice", "Subscription", "Subscription Plan"]


class TestSalesFlows(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        frappe.local.role_permissions = {}
        frappe.local.user_roles = None
        frappe.utils.get_roles = lambda user=None: [
            "Purisol Administrator",
            "Administrator",
            "System Manager",
            "All",
        ]

    def _setup_basics(self, pl_name="Test-SalesFlow-PL", customer_name="Test-SalesFlow-Cust", rate=100):
        item = ensure_coupon_item()
        pl = ensure_price_list(pl_name)
        ensure_item_price(item.name, pl.name, rate)
        customer = ensure_customer(customer_name)
        configure_purisol_settings(coupon_item=item.name, default_price_list=pl.name)
        return item, pl, customer

    # --- US1 integration tests ---

    def test_submit_single_in_stock_booklet_transitions_to_sold(self):
        _item, _pl, customer = self._setup_basics("PL-Submit-InStock", "Cust-Submit-InStock")
        booklet = make_booklet_in_stock()

        result = purisol_create_sales_invoice_for_booklets(customer.name, [booklet.name])
        inv = frappe.get_doc("Sales Invoice", result["name"])
        inv.submit()

        booklet.reload()
        self.assertEqual(booklet.status, "Sold")
        self.assertEqual(booklet.customer, customer.name)
        self.assertIsNotNone(booklet.sold_on)
        self.assertEqual(booklet.sales_invoice, inv.name)
        self.assertFalse(booklet.current_delivery_man)

    def test_submit_single_in_custody_booklet_clears_current_delivery_man(self):
        _item, _pl, customer = self._setup_basics("PL-Submit-Custody", "Cust-Submit-Custody")
        employee = make_employee("CustodyTest", "DeliveryMan")
        booklet = make_booklet_in_stock()
        submit_assign([booklet.name], employee.name)

        booklet.reload()
        self.assertEqual(booklet.status, "In Custody")
        self.assertEqual(booklet.current_delivery_man, employee.name)

        result = purisol_create_sales_invoice_for_booklets(customer.name, [booklet.name])
        inv = frappe.get_doc("Sales Invoice", result["name"])
        inv.submit()

        booklet.reload()
        self.assertEqual(booklet.status, "Sold")
        self.assertFalse(booklet.current_delivery_man)

    def test_draft_invoice_does_not_change_booklet_status(self):
        _item, _pl, customer = self._setup_basics("PL-DraftNoChange", "Cust-DraftNoChange")
        booklet = make_booklet_in_stock()

        purisol_create_sales_invoice_for_booklets(customer.name, [booklet.name])

        booklet.reload()
        self.assertEqual(booklet.status, "In Stock")
        self.assertFalse(booklet.customer)
        self.assertFalse(booklet.sales_invoice)

    def test_sold_booklet_cannot_be_added_to_new_invoice(self):
        _item, _pl, customer = self._setup_basics("PL-SoldReject", "Cust-SoldReject")
        booklet = make_booklet_in_stock()

        result = purisol_create_sales_invoice_for_booklets(customer.name, [booklet.name])
        inv = frappe.get_doc("Sales Invoice", result["name"])
        inv.submit()
        booklet.reload()
        self.assertEqual(booklet.status, "Sold")

        self.assertRaises(
            frappe.ValidationError,
            purisol_create_sales_invoice_for_booklets,
            customer.name,
            [booklet.name],
        )

    # --- US2 integration tests ---

    def test_multi_booklet_submit_mixed_sources_all_transition_to_sold(self):
        _item, _pl, customer = self._setup_basics("PL-MultiSell", "Cust-MultiSell")
        employee = make_employee("MultiSell", "DM2")
        b1 = make_booklet_in_stock()
        b2 = make_booklet_in_stock()
        b3 = make_booklet_in_stock()
        submit_assign([b3.name], employee.name)
        b3.reload()
        self.assertEqual(b3.status, "In Custody")

        result = purisol_create_sales_invoice_for_booklets(
            customer.name, [b1.name, b2.name, b3.name]
        )
        inv = frappe.get_doc("Sales Invoice", result["name"])
        inv.submit()

        for booklet in (b1, b2, b3):
            booklet.reload()
            self.assertEqual(booklet.status, "Sold")
            self.assertEqual(booklet.sales_invoice, inv.name)
            self.assertIsNotNone(booklet.sold_on)

        sold_ons = {b1.sold_on, b2.sold_on, b3.sold_on}
        self.assertEqual(len(sold_ons), 1)
        self.assertFalse(b3.current_delivery_man)

    def test_duplicate_booklet_on_invoice_rejected_at_submit(self):
        item, pl, customer = self._setup_basics("PL-DupSubmit", "Cust-DupSubmit")
        booklet = make_booklet_in_stock()

        inv = frappe.new_doc("Sales Invoice")
        inv.customer = customer.name
        inv.selling_price_list = pl.name
        for _ in range(2):
            inv.append("items", {"item_code": item.name, "qty": 1, "purisol_booklet": booklet.name})
        inv.set_missing_values()
        inv.calculate_taxes_and_totals()
        inv.flags.ignore_validate = True
        inv.insert(ignore_permissions=False)

        inv.flags.ignore_validate = False
        self.assertRaises(frappe.ValidationError, inv.submit)

        inv.reload()
        self.assertEqual(inv.docstatus, 0)
        booklet.reload()
        self.assertEqual(booklet.status, "In Stock")

    def test_stale_draft_with_booklet_sold_elsewhere_rejected(self):
        _item, _pl, customer = self._setup_basics("PL-StaleDraft", "Cust-StaleDraft")
        booklet_x = make_booklet_in_stock()
        booklet_y = make_booklet_in_stock()

        result_a = purisol_create_sales_invoice_for_booklets(
            customer.name, [booklet_x.name, booklet_y.name]
        )
        inv_a = frappe.get_doc("Sales Invoice", result_a["name"])

        result_b = purisol_create_sales_invoice_for_booklets(customer.name, [booklet_x.name])
        inv_b = frappe.get_doc("Sales Invoice", result_b["name"])
        inv_b.submit()

        booklet_x.reload()
        self.assertEqual(booklet_x.status, "Sold")

        with self.assertRaises(frappe.ValidationError) as cm:
            inv_a.submit()
        self.assertIn(booklet_x.name, str(cm.exception))

        inv_a.reload()
        self.assertEqual(inv_a.docstatus, 0)
        booklet_y.reload()
        self.assertEqual(booklet_y.status, "In Stock")

    def test_changing_price_list_on_draft_updates_all_lines(self):
        item = ensure_coupon_item()
        pl_retail = ensure_price_list("PL-Retail-Draft")
        pl_wholesale = ensure_price_list("PL-Wholesale-Draft")
        ensure_item_price(item.name, pl_retail.name, 100)
        ensure_item_price(item.name, pl_wholesale.name, 60)
        customer = ensure_customer("Cust-PLDraftChange")
        configure_purisol_settings(coupon_item=item.name, default_price_list=pl_retail.name)

        b1 = make_booklet_in_stock()
        b2 = make_booklet_in_stock()

        result = purisol_create_sales_invoice_for_booklets(customer.name, [b1.name, b2.name])
        inv = frappe.get_doc("Sales Invoice", result["name"])
        self.assertEqual(inv.selling_price_list, pl_retail.name)

        inv.selling_price_list = pl_wholesale.name
        for line in inv.items:
            if getattr(line, "purisol_booklet", None):
                line.price_list_rate = 60
                line.rate = 60
        inv.calculate_taxes_and_totals()
        inv.save(ignore_permissions=True)
        inv.submit()

        inv.reload()
        self.assertEqual(inv.selling_price_list, pl_wholesale.name)
        for line in inv.items:
            if getattr(line, "purisol_booklet", None):
                self.assertEqual(line.rate, 60)

    def test_all_or_nothing_no_partial_updates(self):
        item, pl, customer = self._setup_basics("PL-AllOrNothing", "Cust-AllOrNothing")

        good = [make_booklet_in_stock() for _ in range(3)]
        bad = make_booklet_in_stock()
        frappe.db.set_value("Purisol Coupon Booklet", bad.name, "status", "Sold")

        inv = frappe.new_doc("Sales Invoice")
        inv.customer = customer.name
        inv.selling_price_list = pl.name
        for bname in [b.name for b in good] + [bad.name]:
            inv.append("items", {"item_code": item.name, "qty": 1, "purisol_booklet": bname})
        inv.set_missing_values()
        inv.calculate_taxes_and_totals()
        inv.flags.ignore_validate = True
        inv.insert(ignore_permissions=False)

        inv.flags.ignore_validate = False
        self.assertRaises(frappe.ValidationError, inv.submit)

        for booklet in good:
            booklet.reload()
            self.assertEqual(booklet.status, "In Stock")

    # --- US3 integration tests ---

    def _make_coupon_for_booklet(self, booklet_name, page_number=1):
        # Use a hash-based name to avoid conflicts with the CP-.##### naming
        # series (which may have committed records from prior test runs).
        coupon_number = f"TC-{frappe.generate_hash('', 8)}"
        coupon = frappe.get_doc({
            "doctype": "Purisol Coupon",
            "booklet": booklet_name,
            "page_number": page_number,
            "status": "Available",
        })
        # Pre-set name so before_insert (which runs before set_new_name) can
        # copy it into coupon_number correctly.
        coupon.name = coupon_number
        coupon.insert(ignore_permissions=True, set_name=coupon_number)
        return coupon

    def test_cancel_safe_reverses_booklet_to_in_stock(self):
        _item, _pl, customer = self._setup_basics("PL-CancelSafe", "Cust-CancelSafe")
        booklet = make_booklet_in_stock()

        result = purisol_create_sales_invoice_for_booklets(customer.name, [booklet.name])
        inv = frappe.get_doc("Sales Invoice", result["name"])
        inv.submit()

        booklet.reload()
        self.assertEqual(booklet.status, "Sold")

        inv.cancel()

        booklet.reload()
        self.assertEqual(booklet.status, "In Stock")
        self.assertFalse(booklet.customer)
        self.assertIsNone(booklet.sold_on)
        self.assertFalse(booklet.sales_invoice)
        self.assertFalse(booklet.current_delivery_man)

        comments = frappe.get_all(
            "Comment",
            filters={
                "reference_doctype": "Purisol Coupon Booklet",
                "reference_name": booklet.name,
                "comment_type": "Info",
            },
            fields=["content"],
        )
        self.assertTrue(any("Sale reversed" in c["content"] for c in comments))

    def test_cancel_blocked_by_consumption_on_single_booklet(self):
        _item, _pl, customer = self._setup_basics("PL-CancelBlocked", "Cust-CancelBlocked")
        booklet = make_booklet_in_stock()
        coupon = self._make_coupon_for_booklet(booklet.name)

        result = purisol_create_sales_invoice_for_booklets(customer.name, [booklet.name])
        inv = frappe.get_doc("Sales Invoice", result["name"])
        inv.submit()

        booklet.reload()
        self.assertEqual(booklet.status, "Sold")

        frappe.db.set_value("Purisol Coupon", coupon.name, "status", "Consumed")

        with self.assertRaises(frappe.ValidationError):
            inv.cancel()

        booklet.reload()
        self.assertEqual(booklet.status, "Sold")

    def test_cancel_multi_booklet_all_or_nothing_when_one_has_consumption(self):
        _item, _pl, customer = self._setup_basics("PL-CancelMultiBlock", "Cust-CancelMultiBlock")
        b1 = make_booklet_in_stock()
        b2 = make_booklet_in_stock()
        b3 = make_booklet_in_stock()
        coupon = self._make_coupon_for_booklet(b3.name)

        result = purisol_create_sales_invoice_for_booklets(customer.name, [b1.name, b2.name, b3.name])
        inv = frappe.get_doc("Sales Invoice", result["name"])
        inv.submit()

        for b in (b1, b2, b3):
            b.reload()
            self.assertEqual(b.status, "Sold")

        frappe.db.set_value("Purisol Coupon", coupon.name, "status", "Consumed")

        with self.assertRaises(frappe.ValidationError) as cm:
            inv.cancel()
        self.assertIn(b3.name, str(cm.exception))

        for b in (b1, b2, b3):
            b.reload()
            self.assertEqual(b.status, "Sold")

    def test_cancel_of_draft_has_no_side_effects(self):
        _item, _pl, customer = self._setup_basics("PL-DraftNoSideEffect", "Cust-DraftNoSideEffect")
        booklet = make_booklet_in_stock()

        result = purisol_create_sales_invoice_for_booklets(customer.name, [booklet.name])

        frappe.delete_doc("Sales Invoice", result["name"], ignore_permissions=True)

        booklet.reload()
        self.assertEqual(booklet.status, "In Stock")
        self.assertFalse(booklet.customer)
        self.assertFalse(booklet.sales_invoice)

    def test_trash_refused_while_booklets_reference_invoice(self):
        _item, _pl, customer = self._setup_basics("PL-TrashGuard", "Cust-TrashGuard")
        booklet = make_booklet_in_stock()

        result = purisol_create_sales_invoice_for_booklets(customer.name, [booklet.name])
        inv = frappe.get_doc("Sales Invoice", result["name"])
        inv.submit()

        booklet.reload()
        self.assertEqual(booklet.status, "Sold")
        self.assertEqual(booklet.sales_invoice, inv.name)

        # Force docstatus=2 without going through on_cancel so the booklet
        # reference remains intact — this is the state guard_trash must block.
        frappe.db.set_value("Sales Invoice", inv.name, "docstatus", 2)

        self.assertRaises(
            frappe.ValidationError,
            frappe.delete_doc,
            "Sales Invoice",
            inv.name,
            ignore_permissions=True,
        )

        booklet.reload()
        self.assertEqual(booklet.sales_invoice, inv.name)

    # --- US1 continued ---

    def test_settings_default_price_list_drives_rate_when_no_other_choice(self):
        item = ensure_coupon_item()
        pl = ensure_price_list("PL-SettingsRate")
        ensure_item_price(item.name, pl.name, 150)
        # Customer with no default_price_list
        customer = ensure_customer("Cust-SettingsRate")
        frappe.db.set_value("Customer", customer.name, "default_price_list", None)

        settings = frappe.get_single("Purisol Settings")
        settings.coupon_item = item.name
        settings.default_price_list = pl.name
        settings.save(ignore_permissions=True)

        booklet = make_booklet_in_stock()
        result = purisol_create_sales_invoice_for_booklets(customer.name, [booklet.name])
        inv = frappe.get_doc("Sales Invoice", result["name"])

        self.assertEqual(inv.selling_price_list, pl.name)
        booklet_line = next(
            i for i in inv.items if getattr(i, "purisol_booklet", None) == booklet.name
        )
        self.assertEqual(booklet_line.rate, 150)

    # --- US4 integration tests ---

    def test_price_list_explicit_workflow_choice_wins(self):
        item = ensure_coupon_item()
        pl_retail = ensure_price_list("PL-US4-Retail")
        pl_wholesale = ensure_price_list("PL-US4-Wholesale")
        ensure_item_price(item.name, pl_retail.name, 120)
        ensure_item_price(item.name, pl_wholesale.name, 80)
        customer = ensure_customer("Cust-US4-Explicit", default_price_list=pl_wholesale.name)
        configure_purisol_settings(coupon_item=item.name, default_price_list=pl_retail.name)

        booklet = make_booklet_in_stock()
        result = purisol_create_sales_invoice_for_booklets(
            customer.name, [booklet.name], price_list=pl_retail.name
        )
        inv = frappe.get_doc("Sales Invoice", result["name"])

        self.assertEqual(inv.selling_price_list, pl_retail.name)
        line = next(i for i in inv.items if getattr(i, "purisol_booklet", None) == booklet.name)
        self.assertEqual(line.rate, 120)

    def test_price_list_customer_default_used_when_no_explicit(self):
        item = ensure_coupon_item()
        pl_retail = ensure_price_list("PL-US4-CustRetail")
        pl_wholesale = ensure_price_list("PL-US4-CustWholesale")
        ensure_item_price(item.name, pl_retail.name, 120)
        ensure_item_price(item.name, pl_wholesale.name, 80)
        customer = ensure_customer("Cust-US4-CustDefault", default_price_list=pl_wholesale.name)
        configure_purisol_settings(coupon_item=item.name, default_price_list=pl_retail.name)

        booklet = make_booklet_in_stock()
        result = purisol_create_sales_invoice_for_booklets(customer.name, [booklet.name])
        inv = frappe.get_doc("Sales Invoice", result["name"])

        self.assertEqual(inv.selling_price_list, pl_wholesale.name)
        line = next(i for i in inv.items if getattr(i, "purisol_booklet", None) == booklet.name)
        self.assertEqual(line.rate, 80)

    def test_price_list_settings_default_used_when_no_customer_default_and_no_explicit(self):
        item = ensure_coupon_item()
        pl_retail = ensure_price_list("PL-US4-SettRetail")
        ensure_item_price(item.name, pl_retail.name, 120)
        customer = ensure_customer("Cust-US4-SettDefault")
        frappe.db.set_value("Customer", customer.name, "default_price_list", None)
        configure_purisol_settings(coupon_item=item.name, default_price_list=pl_retail.name)

        booklet = make_booklet_in_stock()
        result = purisol_create_sales_invoice_for_booklets(customer.name, [booklet.name])
        inv = frappe.get_doc("Sales Invoice", result["name"])

        self.assertEqual(inv.selling_price_list, pl_retail.name)
        line = next(i for i in inv.items if getattr(i, "purisol_booklet", None) == booklet.name)
        self.assertEqual(line.rate, 120)

    def test_price_list_misconfigured_surfaces_rate_lookup_error(self):
        item = ensure_coupon_item()
        # Price list with no Item Price for the coupon item
        empty_pl = ensure_price_list("PL-US4-Empty")
        customer = ensure_customer("Cust-US4-EmptyPL")
        frappe.db.set_value("Customer", customer.name, "default_price_list", None)
        configure_purisol_settings(coupon_item=item.name, default_price_list=empty_pl.name)

        booklet = make_booklet_in_stock()
        result = purisol_create_sales_invoice_for_booklets(customer.name, [booklet.name])
        inv = frappe.get_doc("Sales Invoice", result["name"])

        # The resolved price list name is visible on the draft so the Administrator
        # can identify and correct the misconfigured Price List.
        self.assertEqual(inv.selling_price_list, empty_pl.name)
        line = next(i for i in inv.items if getattr(i, "purisol_booklet", None) == booklet.name)
        self.assertEqual(line.rate, 0)

    def test_no_price_list_resolvable_raises_configure_error(self):
        item = ensure_coupon_item()
        customer = ensure_customer("Cust-US4-NoPL")
        frappe.db.set_value("Customer", customer.name, "default_price_list", None)
        settings = frappe.get_single("Purisol Settings")
        original_pl = settings.default_price_list
        settings.coupon_item = item.name
        settings.default_price_list = None
        settings.save(ignore_permissions=True)

        booklet = make_booklet_in_stock()
        try:
            with self.assertRaises(frappe.ValidationError) as cm:
                purisol_create_sales_invoice_for_booklets(customer.name, [booklet.name])
            self.assertIn("Purisol Settings", str(cm.exception))
        finally:
            settings.default_price_list = original_pl
            settings.save(ignore_permissions=True)

    # --- SC-010 audit trail (T032) ---

    def test_sell_cancel_resell_audit_trail(self):
        _item, _pl, customer = self._setup_basics("PL-AuditTrail", "Cust-AuditTrail")
        booklet = make_booklet_in_stock()

        result_a = purisol_create_sales_invoice_for_booklets(customer.name, [booklet.name])
        inv_a = frappe.get_doc("Sales Invoice", result_a["name"])
        inv_a.submit()

        inv_a.cancel()

        booklet.reload()
        self.assertEqual(booklet.status, "In Stock")

        result_b = purisol_create_sales_invoice_for_booklets(customer.name, [booklet.name])
        inv_b = frappe.get_doc("Sales Invoice", result_b["name"])
        inv_b.submit()

        booklet.reload()
        self.assertEqual(booklet.status, "Sold")
        self.assertEqual(booklet.sales_invoice, inv_b.name)

        comments = frappe.get_all(
            "Comment",
            filters={
                "reference_doctype": "Purisol Coupon Booklet",
                "reference_name": booklet.name,
                "comment_type": "Info",
            },
            fields=["content", "creation"],
            order_by="creation asc",
        )
        contents = [c["content"] for c in comments]
        sale_a = next((c for c in contents if inv_a.name in c and "Sold via" in c), None)
        reversal = next((c for c in contents if "Sale reversed" in c and inv_a.name in c), None)
        sale_b = next((c for c in contents if inv_b.name in c and "Sold via" in c), None)

        self.assertIsNotNone(sale_a, "Missing 'Sold via INV-A' comment")
        self.assertIsNotNone(reversal, "Missing 'Sale reversed' comment")
        self.assertIsNotNone(sale_b, "Missing 'Sold via INV-B' comment")

        idx_a = contents.index(sale_a)
        idx_r = contents.index(reversal)
        idx_b = contents.index(sale_b)
        self.assertLess(idx_a, idx_r, "Sale-A comment must precede reversal comment")
        self.assertLess(idx_r, idx_b, "Reversal comment must precede Sale-B comment")
