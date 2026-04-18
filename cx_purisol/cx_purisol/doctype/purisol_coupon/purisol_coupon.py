import frappe
from frappe import _
from frappe.model.document import Document

_ALLOWED_STATUSES = {"Available", "Consumed"}
_ALLOWED_TRANSITIONS = {
    ("Available", "Consumed"),
    ("Consumed", "Available"),
}


class PurisolCoupon(Document):
    def before_validate(self):
        if self.is_new() and not self.coupon_number:
            self.coupon_number = self.name

    def validate(self):
        if self.status not in _ALLOWED_STATUSES:
            frappe.throw(_("Coupon status {0} is not allowed.").format(self.status))

        if not (1 <= (self.page_number or 0) <= 20):
            frappe.throw(_("Page number must be between 1 and 20."))

        prior = self.get_doc_before_save()
        if prior:
            for field in ("booklet", "page_number", "coupon_number"):
                if getattr(self, field) != getattr(prior, field):
                    frappe.throw(_("Field {0} cannot be modified after creation.").format(field))

            if prior.status != self.status and (prior.status, self.status) not in _ALLOWED_TRANSITIONS:
                frappe.throw(
                    _("Coupon status transition from {0} to {1} is not allowed.").format(
                        prior.status, self.status
                    )
                )
