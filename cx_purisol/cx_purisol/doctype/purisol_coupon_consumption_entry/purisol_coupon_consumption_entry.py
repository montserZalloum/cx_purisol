import frappe
from frappe import _
from frappe.model.document import Document


class PurisolCouponConsumptionEntry(Document):
    @property
    def posting_datetime(self):
        return frappe.utils.get_datetime(f"{self.posting_date} {self.posting_time}")

    def before_insert(self):
        self.received_by = frappe.session.user

    def validate(self):
        self.total_coupons = len(self.coupons or [])

        if not self.coupons:
            frappe.throw(_("Consumption Entry must list at least one coupon."))

        seen = set()
        for row in self.coupons:
            if row.coupon in seen:
                frappe.throw(_("Coupon {0} appears more than once in this entry.").format(row.coupon))
            seen.add(row.coupon)

        # has_warnings and discrepancies_detected are controller-owned — populated by detect_for_entry in on_submit.

    def before_submit(self):
        coupon_names = [row.coupon for row in self.coupons]
        live = frappe.get_all(
            "Purisol Coupon",
            filters={"name": ["in", coupon_names]},
            fields=["name", "status", "consumption_entry"],
        )
        live_map = {r["name"]: r for r in live}

        errors = []
        for name in coupon_names:
            if name not in live_map:
                errors.append(_("Coupon {0} does not exist.").format(name))
            elif live_map[name]["status"] == "Consumed":
                prior = live_map[name]["consumption_entry"]
                errors.append(
                    _("Coupon {0} is already Consumed (recorded on entry {1}).").format(name, prior)
                )
        if errors:
            frappe.throw("<br>".join(errors))

    def on_submit(self):
        posting_dt = self.posting_datetime
        for row in self.coupons:
            frappe.db.set_value(
                "Purisol Coupon",
                row.coupon,
                {
                    "status": "Consumed",
                    "consumed_on": posting_dt,
                    "consumed_by_delivery_man": self.delivery_man,
                    "consumption_entry": self.name,
                },
                update_modified=True,
            )

        booklets = {row.booklet for row in self.coupons if row.booklet}
        for b in booklets:
            consumed_count = frappe.db.count("Purisol Coupon", {"booklet": b, "status": "Consumed"})
            remaining_count = 20 - consumed_count
            booklet = frappe.get_doc("Purisol Coupon Booklet", b)
            booklet.consumed_count = consumed_count
            booklet.remaining_count = remaining_count
            triggered_depletion = consumed_count == 20 and booklet.status == "Sold"
            if triggered_depletion:
                booklet.status = "Depleted"
                booklet.depleted_on = posting_dt
            booklet.save(ignore_permissions=True)
            if triggered_depletion:
                booklet.add_comment("Info", _("Depleted via {0}").format(self.name))

        # Phase 5: detect discrepancies and append to discrepancies_detected.
        from cx_purisol.cx_purisol.api.discrepancy import detect_for_entry

        created_names = detect_for_entry(self)
        if created_names:
            self.has_warnings = 1
            for name in created_names:
                self.append("discrepancies_detected", {"discrepancy": name})
            self.db_update()
            for row in self.discrepancies_detected:
                row.db_insert()

    def on_cancel(self):
        for row in self.coupons:
            frappe.db.set_value(
                "Purisol Coupon",
                row.coupon,
                {
                    "status": "Available",
                    "consumed_on": None,
                    "consumed_by_delivery_man": None,
                    "consumption_entry": None,
                },
                update_modified=True,
            )

        booklets = {row.booklet for row in self.coupons if row.booklet}
        for b in booklets:
            consumed_count = frappe.db.count("Purisol Coupon", {"booklet": b, "status": "Consumed"})
            remaining_count = 20 - consumed_count
            booklet = frappe.get_doc("Purisol Coupon Booklet", b)
            booklet.consumed_count = consumed_count
            booklet.remaining_count = remaining_count
            if booklet.status == "Depleted" and consumed_count < 20:
                booklet.status = "Sold"
                booklet.depleted_on = None
                booklet.save(ignore_permissions=True)
                booklet.add_comment(
                    "Info",
                    _("Depletion reverted — entry {0} cancelled.").format(self.name),
                )
            else:
                booklet.save(ignore_permissions=True)
