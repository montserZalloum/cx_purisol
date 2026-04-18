import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.tests.fixtures import make_sold_booklet_ready_for_consumption

test_ignore = ["Customer", "Employee", "Sales Invoice", "Purisol Coupon Booklet", "Purisol Coupon"]


class TestPurisolCouponConsumptionEntry(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._customer, self._emp, self._booklet, self._coupons = (
            make_sold_booklet_ready_for_consumption()
        )

    def _make_entry(self, coupons=None, delivery_man=None):
        doc = frappe.get_doc({
            "doctype": "Purisol Coupon Consumption Entry",
            "posting_date": frappe.utils.today(),
            "posting_time": frappe.utils.nowtime(),
            "delivery_man": delivery_man or self._emp.name,
            "coupons": [{"coupon": c} for c in (coupons or [])],
        })
        return doc

    # --- validate rules ---

    def test_validate_rejects_empty_coupons(self):
        doc = self._make_entry(coupons=[])
        with self.assertRaises(frappe.ValidationError) as ctx:
            doc.insert(ignore_permissions=True)
        self.assertIn("at least one coupon", str(ctx.exception))

    def test_validate_rejects_duplicate_coupon(self):
        c = self._coupons[0]
        doc = self._make_entry(coupons=[c, c])
        with self.assertRaises(frappe.ValidationError) as ctx:
            doc.insert(ignore_permissions=True)
        self.assertIn(c, str(ctx.exception))

    def test_has_warnings_field_is_read_only(self):
        meta = frappe.get_meta("Purisol Coupon Consumption Entry")
        field = meta.get_field("has_warnings")
        self.assertIsNotNone(field, "has_warnings field must exist on the DocType")
        self.assertEqual(field.read_only, 1, "has_warnings must be read_only = 1 (controller-owned)")

    def test_discrepancies_detected_field_is_read_only(self):
        meta = frappe.get_meta("Purisol Coupon Consumption Entry")
        field = meta.get_field("discrepancies_detected")
        self.assertIsNotNone(field, "discrepancies_detected field must exist on the DocType")
        self.assertEqual(field.read_only, 1, "discrepancies_detected must be read_only = 1 (controller-owned)")

    def test_before_insert_stamps_received_by(self):
        doc = self._make_entry(coupons=[self._coupons[0]])
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.received_by, frappe.session.user)
        reloaded = frappe.get_doc("Purisol Coupon Consumption Entry", doc.name)
        self.assertEqual(reloaded.received_by, frappe.session.user)

    def test_total_coupons_computed_on_validate(self):
        coupons = self._coupons[:3]
        doc = self._make_entry(coupons=coupons)
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.total_coupons, 3)


class TestConsumptionEntryPermissions(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._customer, self._emp, self._booklet, self._coupons = (
            make_sold_booklet_ready_for_consumption()
        )

    def test_non_admin_cannot_create(self):
        """Non-Purisol Administrator cannot insert a Consumption Entry (FR-070)."""
        doc = frappe.get_doc({
            "doctype": "Purisol Coupon Consumption Entry",
            "posting_date": frappe.utils.today(),
            "posting_time": frappe.utils.nowtime(),
            "delivery_man": self._emp.name,
            "coupons": [{"coupon": self._coupons[0]}],
        })
        frappe.set_user("Guest")
        try:
            with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
                doc.insert()
        finally:
            frappe.set_user("Administrator")

    def test_received_by_is_stamped_and_not_editable_after_insert(self):
        """received_by is auto-stamped at insert and reflected on reload (FR-071)."""
        doc = frappe.get_doc({
            "doctype": "Purisol Coupon Consumption Entry",
            "posting_date": frappe.utils.today(),
            "posting_time": frappe.utils.nowtime(),
            "delivery_man": self._emp.name,
            "coupons": [{"coupon": self._coupons[0]}],
        })
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.received_by, "Administrator")
        reloaded = frappe.get_doc("Purisol Coupon Consumption Entry", doc.name)
        self.assertEqual(reloaded.received_by, "Administrator")
