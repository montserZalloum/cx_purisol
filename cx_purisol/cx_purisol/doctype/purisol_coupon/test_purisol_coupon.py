import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.api.booklet_generation import purisol_generate_booklets


class TestPurisolCoupon(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def _generate(self, qty=1):
        frappe.utils.get_roles = lambda user=None: ["Purisol Administrator", "Administrator", "System Manager", "All"]
        return purisol_generate_booklets(qty)

    def test_coupon_number_is_name(self):
        result = self._generate(1)
        booklet_name = result["first_booklet"]
        coupons = frappe.get_all(
            "Purisol Coupon", filters={"booklet": booklet_name}, fields=["name", "coupon_number"]
        )
        for c in coupons:
            self.assertEqual(c["name"], c["coupon_number"])

    def test_page_number_range(self):
        result = self._generate(1)
        booklet_name = result["first_booklet"]
        coupons = frappe.get_all(
            "Purisol Coupon",
            filters={"booklet": booklet_name},
            fields=["page_number"],
        )
        pages = sorted(c["page_number"] for c in coupons)
        self.assertEqual(pages, list(range(1, 21)))

    def test_immutable_fields_reject_modification(self):
        result = self._generate(1)
        booklet_name = result["first_booklet"]
        coupon_name = frappe.get_value(
            "Purisol Coupon", {"booklet": booklet_name, "page_number": 1}, "name"
        )
        doc = frappe.get_doc("Purisol Coupon", coupon_name)
        doc.page_number = 5
        self.assertRaises(frappe.ValidationError, doc.save)

    def test_status_only_available(self):
        result = self._generate(1)
        booklet_name = result["first_booklet"]
        coupon_name = frappe.get_value(
            "Purisol Coupon", {"booklet": booklet_name, "page_number": 1}, "name"
        )
        doc = frappe.get_doc("Purisol Coupon", coupon_name)
        doc.status = "Consumed"
        self.assertRaises(frappe.ValidationError, doc.save)
