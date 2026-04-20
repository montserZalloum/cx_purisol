import frappe
from frappe import _
from frappe.model.document import Document


class PurisolCouponDiscrepancy(Document):
    def before_insert(self):
        if not self.status:
            self.status = "Open"
        if not self.opened_on:
            self.opened_on = frappe.utils.now_datetime()

    def after_insert(self):
        """Phase 6 US1: notify Purisol Administrator users on discrepancy open.

        Runs inside the caller's transaction (typically the Consumption Entry
        on_submit via Phase-5 detection, or a direct seed_open_discrepancy).
        A raise propagates and rolls the whole stack back.
        """
        from cx_purisol.cx_purisol.api import notify

        delivery_man = (
            frappe.db.get_value(
                "Purisol Coupon Consumption Entry",
                self.triggering_consumption_entry,
                "delivery_man",
            )
            if self.triggering_consumption_entry
            else None
        )

        notify.send(
            recipient="Purisol Administrator",
            subject=_("Discrepancy {0} opened").format(self.name),
            message=_(
                "Discrepancy {0} opened: {1} in booklet {2}, delivery man {3}."
            ).format(
                self.name,
                _(self.discrepancy_type or ""),
                self.booklet or _("(unknown)"),
                delivery_man or _("(unknown)"),
            ),
            reference_doctype="Purisol Coupon Discrepancy",
            reference_name=self.name,
        )

    def validate(self):
        prior = self.get_doc_before_save()
        if prior is None:
            return

        errors: list[str] = []

        # V1-V5: detection-time fields are immutable after insert
        for fieldname in (
            "discrepancy_type",
            "triggering_consumption_entry",
            "booklet",
            "customer",
            "opened_on",
        ):
            if str(getattr(self, fieldname) or "") != str(getattr(prior, fieldname) or ""):
                errors.append(_("{0} cannot be changed after creation.").format(fieldname))

        # V6: affected_coupons rows immutable (same coupon per row, same order)
        prior_coupons = [(r.coupon,) for r in (prior.affected_coupons or [])]
        curr_coupons = [(r.coupon,) for r in (self.affected_coupons or [])]
        if prior_coupons != curr_coupons:
            errors.append(_("affected_coupons cannot be edited after creation."))

        # V7: related_delivery_men rows immutable (same delivery_man+role per row, same order)
        prior_related = [
            (r.delivery_man, r.role) for r in (prior.related_delivery_men or [])
        ]
        curr_related = [
            (r.delivery_man, r.role) for r in (self.related_delivery_men or [])
        ]
        if prior_related != curr_related:
            errors.append(_("related_delivery_men cannot be edited after creation."))

        if errors:
            frappe.throw("<br>".join(errors))

        # V8: only Open ↔ Under Review are allowed as save-time status values
        if self.status not in {"Open", "Under Review"}:
            frappe.throw(
                _("Status transition from {0} to {1} is not allowed on save.").format(
                    prior.status, self.status
                )
            )

        # V9: auto-recompute estimated_amount if admin hasn't changed it in this save
        if self.estimated_amount == prior.estimated_amount:
            from cx_purisol.cx_purisol.api.discrepancy import _compute_estimated_amount

            booklet_doc = frappe.get_doc("Purisol Coupon Booklet", self.booklet)
            self.estimated_amount = _compute_estimated_amount(
                booklet_doc, len(self.affected_coupons or [])
            )

    def before_submit(self):
        errors: list[str] = []

        if not self.resolution_action:
            frappe.throw(_("Please choose a resolution action before submitting."))

        if self.resolution_action == "None":
            self.status = "Resolved - Admin Error"
            self.resolved_on = frappe.utils.now_datetime()

        elif self.resolution_action == "Add to Liability Ledger":
            settings = frappe.get_cached_doc("Purisol Settings")
            if not self.liable_delivery_man:
                errors.append(_("Liable Delivery Man is required for 'Add to Liability Ledger'."))
            if not settings.employee_liability_account:
                errors.append(_("Employee liability account is not configured in Purisol Settings."))
            if not settings.discrepancy_offset_account:
                errors.append(_("Discrepancy offset account is not configured in Purisol Settings."))
            if not self.estimated_amount or self.estimated_amount <= 0:
                errors.append(_("Estimated Amount must be greater than zero for 'Add to Liability Ledger'."))
            if errors:
                frappe.throw("<br>".join(errors))
            je = _create_liability_journal_entry(self)
            self.journal_entry = je.name
            self.status = "Resolved - Delivery Man Liable"
            self.resolved_on = frappe.utils.now_datetime()

        elif self.resolution_action == "Immediate Cash Payment":
            settings = frappe.get_cached_doc("Purisol Settings")
            if not self.liable_delivery_man:
                errors.append(_("Liable Delivery Man is required for 'Immediate Cash Payment'."))
            if not settings.discrepancy_offset_account:
                errors.append(_("Discrepancy offset account is not configured in Purisol Settings."))
            if not settings.default_cash_account:
                errors.append(_("Default cash account is not configured in Purisol Settings."))
            if not self.estimated_amount or self.estimated_amount <= 0:
                errors.append(_("Estimated Amount must be greater than zero for 'Immediate Cash Payment'."))
            if errors:
                frappe.throw("<br>".join(errors))
            pe = _create_cash_payment_entry(self)
            self.payment_entry = pe.name
            self.status = "Resolved - Paid"
            self.resolved_on = frappe.utils.now_datetime()

    def on_submit(self):
        pass

    def on_cancel(self):
        frappe.throw(
            _(
                "Cancelling a resolved discrepancy is not permitted. "
                "Corrections must go through a reversing Journal Entry or Payment Entry."
            )
        )


def _create_liability_journal_entry(doc):
    """Create and submit a Journal Entry debiting the employee liability account."""
    import erpnext

    settings = frappe.get_cached_doc("Purisol Settings")
    company = settings.get("company") or erpnext.get_default_company()

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.posting_date = frappe.utils.today()
    je.company = company
    je.user_remark = _("Discrepancy {0} — liable {1}").format(
        doc.name, doc.liable_delivery_man
    )

    je.append(
        "accounts",
        {
            "account": settings.employee_liability_account,
            "party_type": "Employee",
            "party": doc.liable_delivery_man,
            "debit_in_account_currency": doc.estimated_amount,
            "credit_in_account_currency": 0,
        },
    )
    je.append(
        "accounts",
        {
            "account": settings.discrepancy_offset_account,
            "debit_in_account_currency": 0,
            "credit_in_account_currency": doc.estimated_amount,
        },
    )

    je.insert(ignore_permissions=True)
    je.submit()
    return je


def _create_cash_payment_entry(doc):
    """Create and submit a Payment Entry receiving cash against the discrepancy offset account."""
    import erpnext

    settings = frappe.get_cached_doc("Purisol Settings")
    company = settings.get("company") or erpnext.get_default_company()

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.posting_date = frappe.utils.today()
    pe.company = company
    pe.paid_from = settings.discrepancy_offset_account
    pe.paid_to = settings.default_cash_account
    pe.paid_amount = doc.estimated_amount
    pe.received_amount = doc.estimated_amount
    pe.party_type = "Employee"
    pe.party = doc.liable_delivery_man

    pe.append(
        "references",
        {
            "reference_doctype": "Purisol Coupon Discrepancy",
            "reference_name": doc.name,
            "allocated_amount": doc.estimated_amount,
        },
    )

    pe.insert(ignore_permissions=True)
    pe.submit()
    return pe
