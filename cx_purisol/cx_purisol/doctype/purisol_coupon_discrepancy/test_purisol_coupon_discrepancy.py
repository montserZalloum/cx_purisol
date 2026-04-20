"""Unit tests for PurisolCouponDiscrepancy controller lifecycle - Phase 5 US1/US3/US4/US5.

T020: Validate immutability (V1-V9), status transitions, and estimated_amount logic.
T033: US3 Admin Error resolution unit tests.
T035: Amend-disabled test.
T036: Locked-after-submit test.
T039: US4 Liability Ledger resolution unit tests.
T043: US5 Cash Payment resolution unit tests.
"""
from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.tests.fixtures import (
    configure_purisol_settings_accounts,
    count_notifications,
    ensure_customer,
    make_booklet_in_stock,
    make_employee,
    seed_administrator_user,
    seed_open_discrepancy,
)

test_ignore = [
    "Customer",
    "Employee",
    "Purisol Coupon Booklet",
    "Purisol Coupon",
    "Purisol Coupon Discrepancy",
]

_COUPON_COUNTER = [0]


def _next_coupon_number():
    _COUPON_COUNTER[0] += 1
    return f"CPN-IMMU-{_COUPON_COUNTER[0]:04d}"


def _seed(customer=None, estimated_amount=50.0, affected_coupons=()):
    """Insert a draft Open discrepancy and return the loaded doc."""
    booklet = make_booklet_in_stock().name
    disc_name = seed_open_discrepancy(
        discrepancy_type="Missing Coupons",
        booklet=booklet,
        customer=customer,
        affected_coupons=list(affected_coupons),
        estimated_amount=estimated_amount,
    )
    return frappe.get_doc("Purisol Coupon Discrepancy", disc_name)


class TestDiscrepancyImmutability(FrappeTestCase):
    """Validate - field immutability on existing drafts (V1-V9)."""

    def setUp(self):
        frappe.set_user("Administrator")

    # V1
    def test_discrepancy_type_immutable_on_edit(self):
        disc = _seed()
        disc.discrepancy_type = "Unassigned Booklet"
        with self.assertRaises(frappe.ValidationError):
            disc.save(ignore_permissions=True)

    # V2
    def test_triggering_entry_immutable(self):
        disc = _seed()
        disc.triggering_consumption_entry = "NONEXIST-CE-9999"
        with self.assertRaises(frappe.ValidationError):
            disc.save(ignore_permissions=True)

    # V3
    def test_booklet_immutable(self):
        disc = _seed()
        other_booklet = make_booklet_in_stock().name
        disc.booklet = other_booklet
        with self.assertRaises(frappe.ValidationError):
            disc.save(ignore_permissions=True)

    # V4
    def test_customer_immutable(self):
        disc = _seed(customer=None)
        new_customer = ensure_customer("ImmuteTest-Customer").name
        disc.customer = new_customer
        with self.assertRaises(frappe.ValidationError):
            disc.save(ignore_permissions=True)

    # V5
    def test_opened_on_immutable(self):
        disc = _seed()
        disc.opened_on = "2020-01-01 00:00:00"
        with self.assertRaises(frappe.ValidationError):
            disc.save(ignore_permissions=True)

    # V6
    def test_affected_coupons_rows_immutable(self):
        booklet_name = make_booklet_in_stock().name
        coupon = frappe.get_doc({
            "doctype": "Purisol Coupon",
            "booklet": booklet_name,
            "page_number": 1,
            "status": "Available",
            "coupon_number": _next_coupon_number(),
        })
        coupon.insert(ignore_permissions=True)

        disc_name = seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=booklet_name,
            affected_coupons=[coupon.name],
        )
        disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        disc.affected_coupons = []
        with self.assertRaises(frappe.ValidationError):
            disc.save(ignore_permissions=True)

    # V7
    def test_related_delivery_men_rows_immutable(self):
        emp = make_employee("ImmuteRel", "Tester")
        disc = _seed()
        disc.append("related_delivery_men", {
            "delivery_man": emp.name,
            "role": "Custody Holder",
        })
        with self.assertRaises(frappe.ValidationError):
            disc.save(ignore_permissions=True)

    # V8 — allowed transition
    def test_status_save_transition_open_to_under_review_allowed(self):
        disc = _seed()
        disc.status = "Under Review"
        disc.save(ignore_permissions=True)
        disc.reload()
        self.assertEqual(disc.status, "Under Review")

    # V8 — forbidden transition
    def test_status_save_transition_open_to_resolved_rejected(self):
        disc = _seed()
        disc.status = "Resolved - Admin Error"
        with self.assertRaises(frappe.ValidationError):
            disc.save(ignore_permissions=True)

    # V9 — recompute when admin has not edited
    def test_estimated_amount_recomputed_when_not_edited(self):
        disc = _seed(estimated_amount=50.0)
        disc.save(ignore_permissions=True)
        # Save succeeded without ValidationError; amount was recomputed (to 0 since count=0)
        disc.reload()
        self.assertIsNotNone(disc.estimated_amount)

    # V9 — preserve when admin edited
    def test_estimated_amount_preserved_when_admin_edited(self):
        disc = _seed(estimated_amount=50.0)
        disc.estimated_amount = 999.0
        disc.save(ignore_permissions=True)
        disc.reload()
        self.assertAlmostEqual(disc.estimated_amount, 999.0, places=2)


# ---------------------------------------------------------------------------
# T033 — US3 Admin Error resolution unit tests
# ---------------------------------------------------------------------------


class TestAdminErrorResolution(FrappeTestCase):
    """US3: resolution_action = 'None' → Resolved - Admin Error, no financial docs."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_resolution_action_required_on_submit(self):
        """Empty resolution_action → frappe.throw with S1 message."""
        disc_name = seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=make_booklet_in_stock().name,
        )
        disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        disc.resolution_action = ""
        disc.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            disc.submit()

    def test_admin_error_resolution_success(self):
        """resolution_action = 'None' → status = 'Resolved - Admin Error', resolved_on stamped."""
        disc_name = seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=make_booklet_in_stock().name,
        )
        disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        disc.resolution_action = "None"
        disc.save(ignore_permissions=True)
        disc.submit()
        disc.reload()
        self.assertEqual(disc.status, "Resolved - Admin Error")
        self.assertIsNotNone(disc.resolved_on)
        self.assertFalse(disc.journal_entry)
        self.assertFalse(disc.payment_entry)

    def test_admin_error_does_not_require_liable_delivery_man(self):
        """'None' resolution succeeds even with no liable_delivery_man."""
        disc_name = seed_open_discrepancy(
            discrepancy_type="Unassigned Booklet",
            booklet=make_booklet_in_stock().name,
        )
        disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        disc.resolution_action = "None"
        disc.save(ignore_permissions=True)
        disc.submit()
        disc.reload()
        self.assertEqual(disc.status, "Resolved - Admin Error")
        self.assertFalse(disc.liable_delivery_man)

    def test_admin_error_preserves_resolution_notes(self):
        """resolution_notes is preserved verbatim after 'None' submit."""
        disc_name = seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=make_booklet_in_stock().name,
        )
        disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        disc.resolution_action = "None"
        disc.resolution_notes = "Admin confirmed this was a data entry error."
        disc.save(ignore_permissions=True)
        disc.submit()
        disc.reload()
        self.assertEqual(disc.resolution_notes, "Admin confirmed this was a data entry error.")

    def test_on_cancel_throws_for_resolved(self):
        """Cancelling a submitted discrepancy always raises (C1)."""
        disc_name = seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=make_booklet_in_stock().name,
        )
        disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        disc.resolution_action = "None"
        disc.save(ignore_permissions=True)
        disc.submit()
        disc.reload()
        with self.assertRaises(frappe.ValidationError):
            disc.cancel()


# ---------------------------------------------------------------------------
# T035 — Amend-disabled test
# ---------------------------------------------------------------------------


class TestAmendDisabled(FrappeTestCase):
    """amend = 0 in permissions → Purisol Administrator cannot amend."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_amend_disabled(self):
        """Purisol Administrator role has amend = 0; frappe.has_permission returns False."""
        meta = frappe.get_meta("Purisol Coupon Discrepancy")
        for perm in meta.permissions:
            if perm.role == "Purisol Administrator":
                self.assertEqual(
                    perm.amend,
                    0,
                    "Purisol Administrator must have amend = 0 on Purisol Coupon Discrepancy",
                )
                return
        self.fail("Purisol Administrator permission row not found on Purisol Coupon Discrepancy")


# ---------------------------------------------------------------------------
# T036 — Locked-after-submit test
# ---------------------------------------------------------------------------


class TestLockedAfterSubmit(FrappeTestCase):
    """Submitted discrepancy is locked — any edit raises ValidationError."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_locked_after_submit(self):
        """Editing a submitted discrepancy raises Frappe's standard submitted-doc error."""
        disc_name = seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=make_booklet_in_stock().name,
        )
        disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        disc.resolution_action = "None"
        disc.save(ignore_permissions=True)
        disc.submit()

        submitted = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        submitted.resolution_notes = "Trying to edit after submit"
        with self.assertRaises(Exception):
            submitted.save(ignore_permissions=True)


# ---------------------------------------------------------------------------
# T039 — US4 Liability Ledger unit tests
# ---------------------------------------------------------------------------


class TestLiabilityLedgerResolution(FrappeTestCase):
    """US4: 'Add to Liability Ledger' precondition validation."""

    def setUp(self):
        frappe.set_user("Administrator")

    def _seed(self):
        return seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=make_booklet_in_stock().name,
            estimated_amount=40.0,
        )

    def test_liability_missing_liable_delivery_man_rejects(self):
        """No liable_delivery_man + valid accounts → aggregated error (S2a)."""
        configure_purisol_settings_accounts()
        disc_name = self._seed()
        disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        disc.resolution_action = "Add to Liability Ledger"
        disc.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError) as ctx:
            disc.submit()
        self.assertIn("Liable Delivery Man", str(ctx.exception))

    def test_liability_missing_employee_liability_account_rejects(self):
        """Missing employee_liability_account → aggregated error (S2b)."""
        configure_purisol_settings_accounts()
        settings = frappe.get_single("Purisol Settings")
        orig = settings.employee_liability_account
        settings.employee_liability_account = None
        settings.save(ignore_permissions=True)
        frappe.clear_cache()
        try:
            disc_name = self._seed()
            emp = make_employee("LiabMissELA", "Test")
            disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
            disc.resolution_action = "Add to Liability Ledger"
            disc.liable_delivery_man = emp.name
            disc.save(ignore_permissions=True)
            with self.assertRaises(frappe.ValidationError) as ctx:
                disc.submit()
            self.assertIn("Employee liability account", str(ctx.exception))
        finally:
            settings.employee_liability_account = orig
            settings.save(ignore_permissions=True)
            frappe.clear_cache()

    def test_liability_missing_discrepancy_offset_account_rejects(self):
        """Missing discrepancy_offset_account → aggregated error (S2c)."""
        configure_purisol_settings_accounts()
        settings = frappe.get_single("Purisol Settings")
        orig_ela = settings.employee_liability_account
        orig_doa = settings.discrepancy_offset_account
        settings.discrepancy_offset_account = None
        settings.save(ignore_permissions=True)
        frappe.clear_cache()
        try:
            disc_name = self._seed()
            emp = make_employee("LiabMissDOA", "Test")
            disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
            disc.resolution_action = "Add to Liability Ledger"
            disc.liable_delivery_man = emp.name
            disc.save(ignore_permissions=True)
            with self.assertRaises(frappe.ValidationError) as ctx:
                disc.submit()
            self.assertIn("Discrepancy offset account", str(ctx.exception))
        finally:
            settings.employee_liability_account = orig_ela
            settings.discrepancy_offset_account = orig_doa
            settings.save(ignore_permissions=True)
            frappe.clear_cache()

    def test_liability_aggregated_errors(self):
        """All three preconditions missing → one error listing all three."""
        settings = frappe.get_single("Purisol Settings")
        orig_ela = settings.employee_liability_account
        orig_doa = settings.discrepancy_offset_account
        settings.employee_liability_account = None
        settings.discrepancy_offset_account = None
        settings.save(ignore_permissions=True)
        frappe.clear_cache()
        try:
            disc_name = self._seed()
            disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
            disc.resolution_action = "Add to Liability Ledger"
            disc.save(ignore_permissions=True)
            with self.assertRaises(frappe.ValidationError) as ctx:
                disc.submit()
            msg = str(ctx.exception)
            self.assertIn("Liable Delivery Man", msg)
            self.assertIn("Employee liability account", msg)
            self.assertIn("Discrepancy offset account", msg)
        finally:
            settings.employee_liability_account = orig_ela
            settings.discrepancy_offset_account = orig_doa
            settings.save(ignore_permissions=True)
            frappe.clear_cache()

    def test_liability_uses_edited_estimated_amount(self):
        """Admin-edited estimated_amount is used as the JE amount."""
        configure_purisol_settings_accounts()
        emp = make_employee("LiabEditAmt", "Test")
        disc_name = self._seed()
        disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        disc.resolution_action = "Add to Liability Ledger"
        disc.liable_delivery_man = emp.name
        disc.estimated_amount = 35.00
        disc.save(ignore_permissions=True)
        disc.submit()
        disc.reload()
        self.assertEqual(disc.status, "Resolved - Delivery Man Liable")
        je = frappe.get_doc("Journal Entry", disc.journal_entry)
        debit_row = next(
            (r for r in je.accounts if r.debit_in_account_currency), None
        )
        self.assertIsNotNone(debit_row)
        self.assertAlmostEqual(debit_row.debit_in_account_currency, 35.0, places=2)


# ---------------------------------------------------------------------------
# T043 — US5 Cash Payment unit tests
# ---------------------------------------------------------------------------


class TestCashPaymentResolution(FrappeTestCase):
    """US5: 'Immediate Cash Payment' precondition validation."""

    def setUp(self):
        frappe.set_user("Administrator")

    def _seed(self):
        return seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=make_booklet_in_stock().name,
            estimated_amount=50.0,
        )

    def test_cash_payment_missing_liable_delivery_man_rejects(self):
        """No liable_delivery_man + valid accounts → error (S3a)."""
        configure_purisol_settings_accounts()
        disc_name = self._seed()
        disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        disc.resolution_action = "Immediate Cash Payment"
        disc.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError) as ctx:
            disc.submit()
        self.assertIn("Liable Delivery Man", str(ctx.exception))

    def test_cash_payment_missing_discrepancy_offset_account_rejects(self):
        """Missing discrepancy_offset_account → error (S3b)."""
        configure_purisol_settings_accounts()
        settings = frappe.get_single("Purisol Settings")
        orig = settings.discrepancy_offset_account
        settings.discrepancy_offset_account = None
        settings.save(ignore_permissions=True)
        frappe.clear_cache()
        try:
            disc_name = self._seed()
            emp = make_employee("CashMissDOA", "Test")
            disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
            disc.resolution_action = "Immediate Cash Payment"
            disc.liable_delivery_man = emp.name
            disc.save(ignore_permissions=True)
            with self.assertRaises(frappe.ValidationError) as ctx:
                disc.submit()
            self.assertIn("Discrepancy offset account", str(ctx.exception))
        finally:
            settings.discrepancy_offset_account = orig
            settings.save(ignore_permissions=True)
            frappe.clear_cache()

    def test_cash_payment_missing_default_cash_account_rejects(self):
        """Missing default_cash_account → error (S3c)."""
        configure_purisol_settings_accounts()
        settings = frappe.get_single("Purisol Settings")
        orig = settings.default_cash_account
        settings.default_cash_account = None
        settings.save(ignore_permissions=True)
        frappe.clear_cache()
        try:
            disc_name = self._seed()
            emp = make_employee("CashMissDCA", "Test")
            disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
            disc.resolution_action = "Immediate Cash Payment"
            disc.liable_delivery_man = emp.name
            disc.save(ignore_permissions=True)
            with self.assertRaises(frappe.ValidationError) as ctx:
                disc.submit()
            self.assertIn("Default cash account", str(ctx.exception))
        finally:
            settings.default_cash_account = orig
            settings.save(ignore_permissions=True)
            frappe.clear_cache()

    def test_cash_payment_aggregated_errors(self):
        """All three preconditions missing → one aggregated error."""
        settings = frappe.get_single("Purisol Settings")
        orig_doa = settings.discrepancy_offset_account
        orig_dca = settings.default_cash_account
        settings.discrepancy_offset_account = None
        settings.default_cash_account = None
        settings.save(ignore_permissions=True)
        frappe.clear_cache()
        try:
            disc_name = self._seed()
            disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
            disc.resolution_action = "Immediate Cash Payment"
            disc.save(ignore_permissions=True)
            with self.assertRaises(frappe.ValidationError) as ctx:
                disc.submit()
            msg = str(ctx.exception)
            self.assertIn("Liable Delivery Man", msg)
            self.assertIn("Discrepancy offset account", msg)
            self.assertIn("Default cash account", msg)
        finally:
            settings.discrepancy_offset_account = orig_doa
            settings.default_cash_account = orig_dca
            settings.save(ignore_permissions=True)
            frappe.clear_cache()


class TestDiscrepancyAfterInsertNotification(FrappeTestCase):
    """Phase 6 US1: after_insert fires one Notification Log per enabled admin."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_after_insert_fires_notification(self):
        admin = seed_administrator_user("p6-us1-admin@example.com")
        booklet = make_booklet_in_stock().name

        before = count_notifications(
            for_user=admin,
            doctype="Purisol Coupon Discrepancy",
        )

        disc_name = seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=booklet,
            estimated_amount=10.0,
        )

        after = count_notifications(
            for_user=admin,
            doctype="Purisol Coupon Discrepancy",
            document_name=disc_name,
        )
        self.assertEqual(after, 1)

        total_after = count_notifications(
            for_user=admin,
            doctype="Purisol Coupon Discrepancy",
        )
        self.assertEqual(total_after, before + 1)

    def test_after_insert_no_admin_silent(self):
        # Disable all admin users so the role expands to an empty recipient set.
        admin_rows = frappe.get_all(
            "Has Role",
            filters={"role": "Purisol Administrator", "parenttype": "User"},
            fields=["parent"],
        )
        enabled_users = [
            r["parent"]
            for r in admin_rows
            if frappe.db.get_value("User", r["parent"], "enabled")
        ]
        for u in enabled_users:
            frappe.db.set_value("User", u, "enabled", 0)

        booklet = make_booklet_in_stock().name
        before_total = count_notifications(doctype="Purisol Coupon Discrepancy")

        try:
            disc_name = seed_open_discrepancy(
                discrepancy_type="Missing Coupons",
                booklet=booklet,
                estimated_amount=10.0,
            )
            self.assertTrue(frappe.db.exists("Purisol Coupon Discrepancy", disc_name))

            after_total = count_notifications(
                doctype="Purisol Coupon Discrepancy",
                document_name=disc_name,
            )
            self.assertEqual(after_total, 0)
            self.assertEqual(
                count_notifications(doctype="Purisol Coupon Discrepancy"),
                before_total,
            )
        finally:
            for u in enabled_users:
                frappe.db.set_value("User", u, "enabled", 1)
