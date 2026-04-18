import frappe
from frappe import _
from frappe.model.document import Document


class PurisolSettings(Document):
    def validate(self):
        if self.customer_low_stock_threshold < 0:
            frappe.throw(_("Customer Low-Stock Threshold must be a non-negative integer."))
        if self.warehouse_low_stock_threshold < 0:
            frappe.throw(_("Warehouse Low-Stock Threshold must be a non-negative integer."))
