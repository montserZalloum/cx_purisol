import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.api.booklet_generation import purisol_generate_booklets


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

    def test_status_only_in_stock(self):
        result = self._generate(1)
        doc = frappe.get_doc("Purisol Coupon Booklet", result["first_booklet"])
        doc.status = "In Custody"
        self.assertRaises(frappe.ValidationError, doc.save)
