import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.api.booklet_generation import purisol_generate_booklets

test_ignore = ["Customer", "Employee", "Purisol Coupon Consumption Entry", "Sales Invoice", "Purisol Coupon Booklet"]


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

    def _get_coupon(self, booklet_name, page=1):
        name = frappe.get_value(
            "Purisol Coupon", {"booklet": booklet_name, "page_number": page}, "name"
        )
        return frappe.get_doc("Purisol Coupon", name)

    def test_available_to_consumed_permitted(self):
        result = self._generate(1)
        coupon = self._get_coupon(result["first_booklet"])
        frappe.db.set_value("Purisol Coupon", coupon.name, "status", "Consumed")
        reloaded = frappe.get_doc("Purisol Coupon", coupon.name)
        self.assertEqual(reloaded.status, "Consumed")

    def test_consumed_to_available_permitted(self):
        result = self._generate(1)
        coupon = self._get_coupon(result["first_booklet"])
        frappe.db.set_value("Purisol Coupon", coupon.name, "status", "Consumed")
        doc = frappe.get_doc("Purisol Coupon", coupon.name)
        doc.status = "Available"
        doc.save(ignore_permissions=True)
        self.assertEqual(doc.status, "Available")

    def test_disallowed_target_status_raises(self):
        result = self._generate(1)
        coupon = self._get_coupon(result["first_booklet"])
        doc = frappe.get_doc("Purisol Coupon", coupon.name)
        doc.status = "In Stock"
        with self.assertRaises(frappe.ValidationError) as ctx:
            doc.save(ignore_permissions=True)
        self.assertIn("not allowed", str(ctx.exception))

    def test_frozen_field_still_rejected_when_status_unchanged(self):
        result = self._generate(1)
        coupon = self._get_coupon(result["first_booklet"])
        doc = frappe.get_doc("Purisol Coupon", coupon.name)
        doc.page_number = 5
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)
