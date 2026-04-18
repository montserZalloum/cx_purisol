import frappe
from frappe import _
from frappe.model.document import Document


class PurisolCoupon(Document):
    def before_insert(self):
        self.coupon_number = self.name

    def validate(self):
        if self.status != "Available":
            frappe.throw(_("Coupon status must be 'Available' in this phase."))

        if not (1 <= (self.page_number or 0) <= 20):
            frappe.throw(_("Page number must be between 1 and 20."))

        prior = self.get_doc_before_save()
        if prior:
            for field in ("booklet", "page_number", "coupon_number"):
                if getattr(self, field) != getattr(prior, field):
                    frappe.throw(_("Field {0} cannot be modified after creation.").format(field))
