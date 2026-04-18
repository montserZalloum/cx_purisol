import frappe
from frappe.tests.utils import FrappeTestCase


class TestPurisolSettings(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_singleton_exists_after_install(self):
        doc = frappe.get_single("Purisol Settings")
        self.assertIsNotNone(doc)
        self.assertEqual(doc.doctype, "Purisol Settings")

    def test_cannot_duplicate_singleton(self):
        meta = frappe.get_meta("Purisol Settings")
        self.assertEqual(meta.issingle, 1, "Purisol Settings must be a singleton (issingle=1)")

    def test_defaults(self):
        doc = frappe.get_single("Purisol Settings")
        self.assertEqual(doc.customer_low_stock_threshold, 3)
        self.assertEqual(doc.warehouse_low_stock_threshold, 5)
        self.assertEqual(doc.enable_consumption_warnings, 1)

    def test_validate_rejects_negative_threshold(self):
        doc = frappe.get_single("Purisol Settings")
        original_customer = doc.customer_low_stock_threshold
        original_warehouse = doc.warehouse_low_stock_threshold
        try:
            doc.customer_low_stock_threshold = -1
            self.assertRaises(frappe.ValidationError, doc.save)
            doc.customer_low_stock_threshold = original_customer
            doc.warehouse_low_stock_threshold = -1
            self.assertRaises(frappe.ValidationError, doc.save)
        finally:
            doc.customer_low_stock_threshold = original_customer
            doc.warehouse_low_stock_threshold = original_warehouse
