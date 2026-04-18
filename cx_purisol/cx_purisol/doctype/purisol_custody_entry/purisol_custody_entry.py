import frappe
from frappe import _
from frappe.model.document import Document


class PurisolCustodyEntry(Document):
    def before_insert(self):
        self.created_by = frappe.session.user

    # ------------------------------------------------------------------
    # validate
    # ------------------------------------------------------------------

    def validate(self):
        errors = []
        errors += self._check_booklets_not_empty()
        errors += self._check_no_duplicate_booklets()
        errors += self._check_delivery_men()
        errors += self._validate_by_entry_type()
        if errors:
            frappe.throw("<br>".join(errors))

    def _check_booklets_not_empty(self):
        if not self.booklets:
            return [_("Custody Entry must list at least one booklet.")]
        return []

    def _check_no_duplicate_booklets(self):
        seen, errors = set(), []
        for row in self.booklets:
            if row.booklet in seen:
                errors.append(_("Booklet {0} is listed more than once in this entry.").format(row.booklet))
            seen.add(row.booklet)
        return errors

    def _check_delivery_men(self):
        errors = []
        if self.entry_type == "Assign":
            if not self.to_delivery_man:
                errors.append(_("To Delivery Man is required for an Assign entry."))
            if self.from_delivery_man:
                errors.append(_("From Delivery Man must be empty for an Assign entry."))
        elif self.entry_type == "Transfer":
            if not self.from_delivery_man:
                errors.append(_("From Delivery Man is required for a Transfer entry."))
            if not self.to_delivery_man:
                errors.append(_("To Delivery Man is required for a Transfer entry."))
            if self.from_delivery_man and self.to_delivery_man and self.from_delivery_man == self.to_delivery_man:
                errors.append(_("A Transfer from a delivery man to themselves is not meaningful."))
        elif self.entry_type == "Return":
            if not self.from_delivery_man:
                errors.append(_("From Delivery Man is required for a Return entry."))
            if self.to_delivery_man:
                errors.append(_("To Delivery Man must be empty for a Return entry."))
        return errors

    def _validate_by_entry_type(self):
        if self.entry_type == "Assign":
            return self._validate_assign()
        if self.entry_type == "Transfer":
            return self._validate_transfer()
        if self.entry_type == "Return":
            return self._validate_return()
        return []

    def _validate_assign(self):
        errors = []
        booklet_names = [row.booklet for row in self.booklets if row.booklet]
        if not booklet_names:
            return errors
        live = {
            b["name"]: b
            for b in frappe.get_all(
                "Purisol Coupon Booklet",
                filters={"name": ["in", booklet_names]},
                fields=["name", "status", "current_delivery_man"],
            )
        }
        for row in self.booklets:
            state = live.get(row.booklet)
            if not state:
                continue
            if state.get("status") != "In Stock":
                errors.append(
                    _("Booklet {0} is not In Stock (current: {1}).").format(
                        row.booklet, state.get("status")
                    )
                )
        return errors

    def _validate_transfer(self):
        errors = []
        booklet_names = [row.booklet for row in self.booklets if row.booklet]
        if not booklet_names:
            return errors
        live = {
            b["name"]: b
            for b in frappe.get_all(
                "Purisol Coupon Booklet",
                filters={"name": ["in", booklet_names]},
                fields=["name", "status", "current_delivery_man"],
            )
        }
        for row in self.booklets:
            state = live.get(row.booklet)
            if not state:
                continue
            if state.get("status") != "In Custody":
                errors.append(
                    _("Booklet {0} is not In Custody (current: {1}).").format(
                        row.booklet, state.get("status")
                    )
                )
            elif state.get("current_delivery_man") != self.from_delivery_man:
                errors.append(
                    _("Booklet {0} is held by {1} (current holder), not by {2}.").format(
                        row.booklet,
                        state.get("current_delivery_man"),
                        self.from_delivery_man,
                    )
                )
        return errors

    def _validate_return(self):
        errors = []
        booklet_names = [row.booklet for row in self.booklets if row.booklet]
        if not booklet_names:
            return errors
        live = {
            b["name"]: b
            for b in frappe.get_all(
                "Purisol Coupon Booklet",
                filters={"name": ["in", booklet_names]},
                fields=["name", "status", "current_delivery_man"],
            )
        }
        for row in self.booklets:
            state = live.get(row.booklet)
            if not state:
                continue
            if state.get("status") != "In Custody":
                errors.append(
                    _("Booklet {0} is not In Custody (current: {1}).").format(
                        row.booklet, state.get("status")
                    )
                )
            elif state.get("current_delivery_man") != self.from_delivery_man:
                errors.append(
                    _("Booklet {0} is held by {1} (current holder), not by {2}.").format(
                        row.booklet,
                        state.get("current_delivery_man"),
                        self.from_delivery_man,
                    )
                )
        return errors

    # ------------------------------------------------------------------
    # before_submit — snapshot booklet state on every child row
    # ------------------------------------------------------------------

    def before_submit(self):
        booklet_names = [row.booklet for row in self.booklets]
        live = {
            b["name"]: b
            for b in frappe.get_all(
                "Purisol Coupon Booklet",
                filters={"name": ["in", booklet_names]},
                fields=["name", "status", "current_delivery_man"],
            )
        }
        for row in self.booklets:
            state = live.get(row.booklet, {})
            frappe.db.set_value(
                "Purisol Custody Entry Booklet",
                row.name,
                {
                    "booklet_status_at_entry": state.get("status"),
                    "delivery_man_at_entry": state.get("current_delivery_man"),
                },
                update_modified=False,
            )
            row.booklet_status_at_entry = state.get("status")
            row.delivery_man_at_entry = state.get("current_delivery_man")

    # ------------------------------------------------------------------
    # on_submit / on_cancel — dispatch to entry-type handlers
    # ------------------------------------------------------------------

    def on_submit(self):
        if self.entry_type == "Assign":
            self._on_submit_assign()
        elif self.entry_type == "Transfer":
            self._on_submit_transfer()
        elif self.entry_type == "Return":
            self._on_submit_return()

    def on_cancel(self):
        if self.entry_type == "Assign":
            self._on_cancel_assign()
        elif self.entry_type == "Transfer":
            self._on_cancel_transfer()
        elif self.entry_type == "Return":
            self._on_cancel_return()

    def _on_submit_assign(self):
        for row in self.booklets:
            booklet = frappe.get_doc("Purisol Coupon Booklet", row.booklet)
            booklet.status = "In Custody"
            booklet.current_delivery_man = self.to_delivery_man
            booklet.save(ignore_permissions=True)

    def _on_submit_transfer(self):
        for row in self.booklets:
            booklet = frappe.get_doc("Purisol Coupon Booklet", row.booklet)
            booklet.current_delivery_man = self.to_delivery_man
            booklet.save(ignore_permissions=True)

    def _on_submit_return(self):
        for row in self.booklets:
            booklet = frappe.get_doc("Purisol Coupon Booklet", row.booklet)
            booklet.status = "In Stock"
            booklet.current_delivery_man = None
            booklet.save(ignore_permissions=True)

    def _on_cancel_assign(self):
        booklet_names = [row.booklet for row in self.booklets]
        live = {
            b["name"]: b
            for b in frappe.get_all(
                "Purisol Coupon Booklet",
                filters={"name": ["in", booklet_names]},
                fields=["name", "status", "current_delivery_man"],
            )
        }
        errors = []
        for row in self.booklets:
            state = live.get(row.booklet, {})
            if (
                state.get("status") != "In Custody"
                or state.get("current_delivery_man") != self.to_delivery_man
            ):
                errors.append(
                    _(
                        "Cannot cancel: booklet {0} has since moved (current status: {1}, current holder: {2}). Cancel the subsequent custody event first."
                    ).format(
                        row.booklet,
                        state.get("status"),
                        state.get("current_delivery_man"),
                    )
                )
        if errors:
            frappe.throw("<br>".join(errors))
        for row in self.booklets:
            booklet = frappe.get_doc("Purisol Coupon Booklet", row.booklet)
            booklet.status = row.booklet_status_at_entry
            booklet.current_delivery_man = row.delivery_man_at_entry
            booklet.save(ignore_permissions=True)

    def _on_cancel_transfer(self):
        booklet_names = [row.booklet for row in self.booklets]
        live = {
            b["name"]: b
            for b in frappe.get_all(
                "Purisol Coupon Booklet",
                filters={"name": ["in", booklet_names]},
                fields=["name", "status", "current_delivery_man"],
            )
        }
        errors = []
        for row in self.booklets:
            state = live.get(row.booklet, {})
            if (
                state.get("status") != "In Custody"
                or state.get("current_delivery_man") != self.to_delivery_man
            ):
                errors.append(
                    _(
                        "Cannot cancel: booklet {0} has since moved (current status: {1}, current holder: {2}). Cancel the subsequent custody event first."
                    ).format(
                        row.booklet,
                        state.get("status"),
                        state.get("current_delivery_man"),
                    )
                )
        if errors:
            frappe.throw("<br>".join(errors))
        for row in self.booklets:
            booklet = frappe.get_doc("Purisol Coupon Booklet", row.booklet)
            booklet.current_delivery_man = row.delivery_man_at_entry
            booklet.save(ignore_permissions=True)

    def _on_cancel_return(self):
        booklet_names = [row.booklet for row in self.booklets]
        live = {
            b["name"]: b
            for b in frappe.get_all(
                "Purisol Coupon Booklet",
                filters={"name": ["in", booklet_names]},
                fields=["name", "status", "current_delivery_man"],
            )
        }
        errors = []
        for row in self.booklets:
            state = live.get(row.booklet, {})
            if state.get("status") != "In Stock" or state.get("current_delivery_man"):
                errors.append(
                    _(
                        "Cannot cancel: booklet {0} has since moved (current status: {1}, current holder: {2}). Cancel the subsequent custody event first."
                    ).format(
                        row.booklet,
                        state.get("status"),
                        state.get("current_delivery_man"),
                    )
                )
        if errors:
            frappe.throw("<br>".join(errors))
        for row in self.booklets:
            booklet = frappe.get_doc("Purisol Coupon Booklet", row.booklet)
            booklet.status = row.booklet_status_at_entry
            booklet.current_delivery_man = row.delivery_man_at_entry
            booklet.save(ignore_permissions=True)
