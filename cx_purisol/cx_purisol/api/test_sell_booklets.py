import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.api.sell_booklets import (
    _resolve_price_list,
    purisol_create_sales_invoice_for_booklets,
)
from cx_purisol.cx_purisol.tests.fixtures import (
    COUPON_ITEM_CODE,
    configure_purisol_settings,
    ensure_coupon_item,
    ensure_customer,
    ensure_item_price,
    ensure_price_list,
    make_booklet_in_stock,
)

test_ignore = ["Customer", "Employee", "Sales Invoice", "Subscription", "Subscription Plan"]


class TestSellBookletsAPI(FrappeTestCase):
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

    # --- _resolve_price_list unit tests ---

    def test_resolve_price_list_prefers_explicit(self):
        ensure_price_list("Test-Explicit-PL")
        ensure_customer("Test-Cust-ExplPL")
        result = _resolve_price_list("Test-Cust-ExplPL", "Test-Explicit-PL")
        self.assertEqual(result, "Test-Explicit-PL")

    def test_resolve_price_list_falls_back_to_customer_default(self):
        pl = ensure_price_list("Test-CustDefault-PL")
        ensure_customer("Test-Cust-CustDefault", default_price_list=pl.name)
        result = _resolve_price_list("Test-Cust-CustDefault", None)
        self.assertEqual(result, pl.name)

    def test_resolve_price_list_falls_back_to_settings_default(self):
        pl = ensure_price_list("Test-SettingsDefault-PL")
        configure_purisol_settings(default_price_list=pl.name)
        # Customer with no default_price_list
        customer = ensure_customer("Test-Cust-SettDefault")
        frappe.db.set_value("Customer", customer.name, "default_price_list", None)
        result = _resolve_price_list(customer.name, None)
        self.assertEqual(result, pl.name)

    def test_resolve_price_list_raises_when_nothing_configured(self):
        settings = frappe.get_single("Purisol Settings")
        original_pl = settings.default_price_list
        settings.default_price_list = None
        settings.save(ignore_permissions=True)
        customer = ensure_customer("Test-Cust-NoPL")
        frappe.db.set_value("Customer", customer.name, "default_price_list", None)
        try:
            self.assertRaises(frappe.ValidationError, _resolve_price_list, customer.name, None)
        finally:
            settings.default_price_list = original_pl
            settings.save(ignore_permissions=True)

    # --- purisol_create_sales_invoice_for_booklets precondition tests ---

    def test_api_rejects_non_administrator(self):
        # frappe.only_for is a no-op when local.flags.in_test is True;
        # disable it temporarily so the role check actually runs.
        frappe.local.flags.in_test = False
        frappe.set_user("Guest")
        try:
            self.assertRaises(
                frappe.PermissionError,
                purisol_create_sales_invoice_for_booklets,
                "AnyCustomer",
                ["AnyBooklet"],
            )
        finally:
            frappe.set_user("Administrator")
            frappe.local.flags.in_test = True

    def test_api_rejects_when_coupon_item_unset(self):
        settings = frappe.get_single("Purisol Settings")
        original = settings.coupon_item
        settings.coupon_item = None
        settings.save(ignore_permissions=True)
        try:
            self.assertRaises(
                frappe.ValidationError,
                purisol_create_sales_invoice_for_booklets,
                "AnyCustomer",
                ["AnyBooklet"],
            )
        finally:
            settings.coupon_item = original
            settings.save(ignore_permissions=True)

    def test_api_rejects_empty_booklets_list(self):
        item = ensure_coupon_item()
        configure_purisol_settings(coupon_item=item.name)
        customer = ensure_customer("Test-Cust-EmptyBL")
        self.assertRaises(
            frappe.ValidationError,
            purisol_create_sales_invoice_for_booklets,
            customer.name,
            [],
        )

    def test_api_rejects_duplicate_booklet_input(self):
        item = ensure_coupon_item()
        pl = ensure_price_list("Test-DupBL-PL")
        ensure_item_price(item.name, pl.name, 100)
        configure_purisol_settings(coupon_item=item.name, default_price_list=pl.name)
        customer = ensure_customer("Test-Cust-DupBL")
        booklet = make_booklet_in_stock()
        self.assertRaises(
            frappe.ValidationError,
            purisol_create_sales_invoice_for_booklets,
            customer.name,
            [booklet.name, booklet.name],
        )

    def test_api_rejects_booklet_in_wrong_status(self):
        item = ensure_coupon_item()
        pl = ensure_price_list("Test-WrongStatus-PL")
        ensure_item_price(item.name, pl.name, 100)
        configure_purisol_settings(coupon_item=item.name, default_price_list=pl.name)
        customer = ensure_customer("Test-Cust-WrongStatus")
        booklet = make_booklet_in_stock()
        booklet.db_set("status", "Sold")
        self.assertRaises(
            frappe.ValidationError,
            purisol_create_sales_invoice_for_booklets,
            customer.name,
            [booklet.name],
        )

    def test_api_creates_draft_invoice_with_one_line_per_booklet(self):
        item = ensure_coupon_item()
        pl = ensure_price_list("Test-DraftInv-PL")
        ensure_item_price(item.name, pl.name, 100)
        customer = ensure_customer("Test-Cust-DraftInv")
        configure_purisol_settings(coupon_item=item.name, default_price_list=pl.name)
        booklets = [make_booklet_in_stock().name, make_booklet_in_stock().name]

        result = purisol_create_sales_invoice_for_booklets(customer.name, booklets)

        self.assertIn("name", result)
        inv = frappe.get_doc("Sales Invoice", result["name"])
        self.assertEqual(inv.docstatus, 0)
        self.assertEqual(inv.customer, customer.name)
        booklet_lines = [i for i in inv.items if getattr(i, "purisol_booklet", None)]
        self.assertEqual(len(booklet_lines), 2)
        self.assertCountEqual(
            [l.purisol_booklet for l in booklet_lines],
            booklets,
        )
