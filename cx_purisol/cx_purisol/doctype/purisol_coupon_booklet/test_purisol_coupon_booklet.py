import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.api.booklet_generation import purisol_generate_booklets

test_ignore = ["Customer", "Employee", "Sales Invoice", "Subscription", "Subscription Plan"]


class TestPurisolCouponBooklet(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def _generate(self, qty=1, batch_id=None):
        frappe.local.role_permissions = {}
        frappe.local.user_roles = None
        frappe.utils.get_roles = lambda user=None: ["Purisol Administrator", "Administrator", "System Manager", "All"]
        return purisol_generate_booklets(qty, batch_id=batch_id)

    def test_computed_fields_on_create(self):
        result = self._generate(1)
        booklet_name = result["first_booklet"]
        doc = frappe.get_doc("Purisol Coupon Booklet", booklet_name)
        k = int(booklet_name.split("-")[1])
        self.assertEqual(doc.booklet_number, booklet_name)
        self.assertEqual(doc.first_coupon, f"CP-{(k-1)*20+1:05d}")
        self.assertEqual(doc.last_coupon, f"CP-{k*20:05d}")
        self.assertEqual(doc.total_coupons, 20)
        self.assertEqual(doc.consumed_count, 0)
        self.assertEqual(doc.remaining_count, 20)

    def test_immutable_fields_reject_modification(self):
        result = self._generate(1)
        doc = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])
        doc.booklet_number = "WP-99999"
        self.assertRaises(frappe.ValidationError, doc.save)

    def test_status_rejects_depleted(self):
        result = self._generate(1)
        doc = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])
        doc.status = "Depleted"
        self.assertRaises(frappe.ValidationError, doc.save)

    def test_status_allows_in_custody(self):
        result = self._generate(1)
        doc = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])
        doc.status = "In Custody"
        doc.save()
        doc.reload()
        self.assertEqual(doc.status, "In Custody")

    # --- Phase 3: widened state machine tests ---

    def test_in_stock_to_sold_via_db_set_allowed(self):
        result = self._generate(1)
        booklet = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])
        self.assertEqual(booklet.status, "In Stock")
        booklet.db_set("status", "Sold", update_modified=True)
        booklet.reload()
        self.assertEqual(booklet.status, "Sold")

    def test_in_custody_to_sold_via_db_set_allowed(self):
        result = self._generate(1)
        booklet = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])
        booklet.db_set("status", "In Custody", update_modified=True)
        booklet.reload()
        self.assertEqual(booklet.status, "In Custody")
        booklet.db_set("status", "Sold", update_modified=True)
        booklet.reload()
        self.assertEqual(booklet.status, "Sold")

    def test_sold_to_in_stock_via_db_set_allowed(self):
        result = self._generate(1)
        booklet = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])
        booklet.db_set("status", "Sold", update_modified=True)
        booklet.reload()
        booklet.db_set("status", "In Stock", update_modified=True)
        booklet.reload()
        self.assertEqual(booklet.status, "In Stock")

    def test_sold_to_in_custody_rejected(self):
        result = self._generate(1)
        booklet = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])
        booklet.db_set("status", "Sold", update_modified=True)
        booklet.reload()
        booklet.status = "In Custody"
        self.assertRaises(frappe.ValidationError, booklet.save)

    def test_sold_to_sold_rejected(self):
        """validate_booklet_lines (V3) rejects re-selling a booklet that is already Sold."""
        import types

        from cx_purisol.cx_purisol.sales_invoice.sales_invoice_hooks import validate_booklet_lines
        from cx_purisol.cx_purisol.tests.fixtures import (
            configure_purisol_settings,
            ensure_coupon_item,
        )

        item = ensure_coupon_item()
        configure_purisol_settings(coupon_item=item.name)

        result = self._generate(1)
        booklet = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])
        booklet.db_set("status", "Sold", update_modified=True)

        fake_line = types.SimpleNamespace(
            purisol_booklet=booklet.name,
            item_code=item.name,
            qty=1,
        )
        fake_inv = types.SimpleNamespace(items=[fake_line])

        self.assertRaises(frappe.ValidationError, validate_booklet_lines, fake_inv)

    def test_depleted_still_unreachable(self):
        result = self._generate(1)
        doc = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])
        doc.status = "Depleted"
        self.assertRaises(frappe.ValidationError, doc.save)

    # --- Phase 4: US3 Sold → Depleted / Depleted → Sold transition tests ---

    def test_sold_to_depleted_permitted(self):
        result = self._generate(1)
        booklet = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])
        booklet.db_set("status", "Sold", update_modified=True)
        booklet.reload()
        booklet.status = "Depleted"
        booklet.save(ignore_permissions=True)
        booklet.reload()
        self.assertEqual(booklet.status, "Depleted")

    def test_depleted_to_sold_permitted(self):
        result = self._generate(1)
        booklet = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])
        booklet.db_set("status", "Sold", update_modified=True)
        booklet.reload()
        booklet.status = "Depleted"
        booklet.save(ignore_permissions=True)
        booklet.status = "Sold"
        booklet.save(ignore_permissions=True)
        booklet.reload()
        self.assertEqual(booklet.status, "Sold")

    def test_depleted_to_in_stock_rejected(self):
        result = self._generate(1)
        booklet = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])
        booklet.db_set("status", "Sold", update_modified=True)
        booklet.reload()
        booklet.status = "Depleted"
        booklet.save(ignore_permissions=True)
        booklet.status = "In Stock"
        self.assertRaises(frappe.ValidationError, booklet.save)

    def test_depleted_to_in_custody_rejected(self):
        result = self._generate(1)
        booklet = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])
        booklet.db_set("status", "Sold", update_modified=True)
        booklet.reload()
        booklet.status = "Depleted"
        booklet.save(ignore_permissions=True)
        booklet.status = "In Custody"
        self.assertRaises(frappe.ValidationError, booklet.save)

    def test_in_stock_to_depleted_rejected(self):
        result = self._generate(1)
        booklet = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])
        self.assertEqual(booklet.status, "In Stock")
        booklet.status = "Depleted"
        self.assertRaises(frappe.ValidationError, booklet.save)

    def test_in_custody_to_depleted_rejected(self):
        result = self._generate(1)
        booklet = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])
        booklet.db_set("status", "In Custody", update_modified=True)
        booklet.reload()
        booklet.status = "Depleted"
        self.assertRaises(frappe.ValidationError, booklet.save)

    # --- Phase 5: US3 cancel reversal tests ---

    def test_sold_to_in_stock_on_cancel_allowed_via_db_set(self):
        result = self._generate(1)
        booklet = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])

        booklet.db_set(
            {
                "status": "Sold",
                "customer": "_Test Customer",
                "sold_on": frappe.utils.now_datetime(),
                "sales_invoice": "SINV-TEST-CANCEL-001",
            },
            update_modified=True,
        )
        booklet.reload()
        self.assertEqual(booklet.status, "Sold")
        self.assertEqual(booklet.customer, "_Test Customer")
        self.assertTrue(booklet.sold_on)
        self.assertEqual(booklet.sales_invoice, "SINV-TEST-CANCEL-001")

        booklet.db_set(
            {
                "status": "In Stock",
                "customer": None,
                "sold_on": None,
                "sales_invoice": None,
            },
            update_modified=True,
        )
        booklet.reload()

        self.assertEqual(booklet.status, "In Stock")
        self.assertFalse(booklet.customer)
        self.assertIsNone(booklet.sold_on)
        self.assertFalse(booklet.sales_invoice)
