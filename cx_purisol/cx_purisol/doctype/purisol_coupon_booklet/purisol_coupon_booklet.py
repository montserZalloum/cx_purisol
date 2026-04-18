import frappe
from frappe import _
from frappe.model.document import Document


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
        if self.status != "In Stock":
            frappe.throw(_("Status must be 'In Stock' in this phase."))

        prior = self.get_doc_before_save()
        if prior:
            immutable = ("booklet_number", "first_coupon", "last_coupon", "total_coupons", "batch_id")
            for field in immutable:
                if getattr(self, field) != getattr(prior, field):
                    frappe.throw(_("Field {0} cannot be modified after creation.").format(field))
