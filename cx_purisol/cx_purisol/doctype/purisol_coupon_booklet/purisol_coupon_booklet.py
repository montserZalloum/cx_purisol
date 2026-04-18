import frappe
from frappe import _
from frappe.model.document import Document

_ALLOWED_STATUSES = {"In Stock", "In Custody", "Sold", "Depleted"}
_ALLOWED_TRANSITIONS = {
    ("In Stock",   "In Custody"),
    ("In Custody", "In Stock"),
    ("In Stock",   "Sold"),
    ("In Custody", "Sold"),
    ("Sold",       "In Stock"),
    ("Sold",       "Depleted"),
    ("Depleted",   "Sold"),
}


class PurisolCouponBooklet(Document):
    def autoname(self):
        pass  # name is set by autoname series; we copy it in before_insert

    def before_insert(self):
        self.booklet_number = self.name
        k = int(self.name.split("-")[1])
        self.first_coupon = f"CP-{(k - 1) * 20 + 1:05d}"
        self.last_coupon = f"CP-{k * 20:05d}"
        self.total_coupons = 20
        self.consumed_count = 0
        self.remaining_count = 20

    def validate(self):
        if self.status not in _ALLOWED_STATUSES:
            frappe.throw(
                _("Booklet status {0} is not allowed in this phase.").format(self.status),
                frappe.ValidationError,
            )

        prior = self.get_doc_before_save()
        if prior:
            immutable = ("booklet_number", "first_coupon", "last_coupon", "total_coupons", "batch_id")
            for field in immutable:
                if getattr(self, field) != getattr(prior, field):
                    frappe.throw(_("Field {0} cannot be modified after creation.").format(field))

            if prior.status != self.status and (prior.status, self.status) not in _ALLOWED_TRANSITIONS:
                frappe.throw(
                    _("Booklet status transition from {0} to {1} is not allowed.").format(
                        prior.status, self.status
                    ),
                    frappe.ValidationError,
                )
