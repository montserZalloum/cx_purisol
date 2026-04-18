"""Integration tests for Discrepancy Detection & Resolution flows - Phase 5 US1-US6.

T019: US1 acceptance scenarios (Missing Coupons end-to-end).
T030: US2 acceptance scenarios (Unassigned Booklet end-to-end).
T034: US3 Admin Error resolution end-to-end.
T040: US4 Liability Ledger resolution end-to-end.
T044: US5 Cash Payment resolution end-to-end.
T045: Resolution precondition parametrized failures.
T049: US6 investigation surfaces (list-view order, discrepancies_detected data shape).
"""
from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.tests.fixtures import (
    configure_purisol_settings_accounts,
    ensure_customer,
    make_booklet_in_stock,
    make_booklet_with_consumed_coupons,
    make_employee,
    make_sold_booklet_ready_for_consumption,
    seed_open_discrepancy,
    submit_assign,
)

test_ignore = [
    "Customer",
    "Employee",
    "Sales Invoice",
    "Purisol Coupon Booklet",
    "Purisol Coupon",
    "Purisol Coupon Discrepancy",
    "Purisol Coupon Consumption Entry",
]


def _submit_entry(delivery_man, coupon_names, posting_date=None):
    doc = frappe.get_doc({
        "doctype": "Purisol Coupon Consumption Entry",
        "posting_date": posting_date or frappe.utils.today(),
        "posting_time": frappe.utils.nowtime(),
        "delivery_man": delivery_man,
        "coupons": [{"coupon": c} for c in coupon_names],
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc


def _page_map(booklet_name):
    rows = frappe.get_all(
        "Purisol Coupon",
        filters={"booklet": booklet_name},
        fields=["name", "page_number"],
        order_by="page_number asc",
    )
    return {r["page_number"]: r["name"] for r in rows}


class TestMissingCouponsDetection(FrappeTestCase):
    """US1 acceptance scenarios — end-to-end Missing Coupons detection."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.customer_name = "MissCoups-Customer"
        self.emp = make_employee("MissCoups", "Employee")
        ensure_customer(self.customer_name)

    # ------------------------------------------------------------------
    # Scenario 1 / 2 — gap created when second entry reveals interior gap
    # ------------------------------------------------------------------

    def test_missing_coupons_scenario_1_gap_from_first_entry(self):
        """Prior consumed {1,2}, new entry consumes {7,8} → discrepancy for gap {3,4,5,6}."""
        booklet_name, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1, 2)
        )
        pm = _page_map(booklet_name)

        second = _submit_entry(self.emp.name, [pm[7], pm[8]])

        self.assertEqual(second.has_warnings, 1)
        self.assertEqual(len(second.discrepancies_detected), 1)
        disc = frappe.get_doc(
            "Purisol Coupon Discrepancy", second.discrepancies_detected[0].discrepancy
        )
        self.assertEqual(disc.discrepancy_type, "Missing Coupons")
        self.assertEqual(disc.status, "Open")
        self.assertEqual(disc.booklet, booklet_name)
        self.assertEqual(disc.triggering_consumption_entry, second.name)
        affected = {r.coupon for r in disc.affected_coupons}
        self.assertEqual(affected, {pm[p] for p in (3, 4, 5, 6)})

    def test_missing_coupons_scenario_2_union_of_prior_and_current(self):
        """Union of prior (1,2) and new (7,8) consumed → gap {3,4,5,6} (4 affected rows)."""
        booklet_name, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1, 2)
        )
        pm = _page_map(booklet_name)

        second = _submit_entry(self.emp.name, [pm[7], pm[8]])

        self.assertEqual(second.has_warnings, 1)
        disc = frappe.get_doc(
            "Purisol Coupon Discrepancy", second.discrepancies_detected[0].discrepancy
        )
        self.assertEqual(len(disc.affected_coupons), 4)
        self.assertAlmostEqual(disc.estimated_amount, 4 * (200 / 20), places=2)

    # ------------------------------------------------------------------
    # Scenario 3 — no gap when consumption is contiguous
    # ------------------------------------------------------------------

    def test_missing_coupons_scenario_3_no_gap_when_contiguous(self):
        """Consuming {3,4} after prior {1,2} → contiguous, no discrepancy."""
        booklet_name, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1, 2)
        )
        pm = _page_map(booklet_name)

        second = _submit_entry(self.emp.name, [pm[3], pm[4]])

        self.assertEqual(second.has_warnings, 0)
        self.assertEqual(len(second.discrepancies_detected), 0)

    # ------------------------------------------------------------------
    # Scenario 4 — dedup against fully-covered open discrepancy
    # ------------------------------------------------------------------

    def test_missing_coupons_scenario_4_dedup_against_open(self):
        """Open discrepancy already covers entire gap → second entry produces no new discrepancy."""
        booklet_name, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1, 2)
        )
        pm = _page_map(booklet_name)

        seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=booklet_name,
            customer=self.customer_name,
            affected_coupons=[pm[p] for p in (3, 4, 5, 6)],
        )

        second = _submit_entry(self.emp.name, [pm[7], pm[8]])

        self.assertEqual(second.has_warnings, 0)
        self.assertEqual(len(second.discrepancies_detected), 0)

    # ------------------------------------------------------------------
    # Scenario 5 — partial overlap: only newly-revealed coupons get flagged
    # ------------------------------------------------------------------

    def test_missing_coupons_scenario_5_partial_overlap_new_coupon_only(self):
        """Open discrepancy covers {3,4}; new entry reveals {5,6} → one new discrepancy."""
        booklet_name, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1, 2)
        )
        pm = _page_map(booklet_name)

        seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=booklet_name,
            customer=self.customer_name,
            affected_coupons=[pm[3], pm[4]],
        )

        second = _submit_entry(self.emp.name, [pm[7], pm[8]])

        self.assertEqual(second.has_warnings, 1)
        self.assertEqual(len(second.discrepancies_detected), 1)
        disc = frappe.get_doc(
            "Purisol Coupon Discrepancy", second.discrepancies_detected[0].discrepancy
        )
        affected = {r.coupon for r in disc.affected_coupons}
        self.assertEqual(affected, {pm[5], pm[6]})

    # ------------------------------------------------------------------
    # Scenario 6 — two booklets in one entry, both produce discrepancies
    # ------------------------------------------------------------------

    def test_missing_coupons_scenario_6_two_booklets_two_discrepancies(self):
        """One entry touches two booklets each with a gap → two distinct discrepancies."""
        booklet1, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1, 2)
        )
        booklet2, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1, 2)
        )
        pm1 = _page_map(booklet1)
        pm2 = _page_map(booklet2)

        entry = _submit_entry(
            self.emp.name,
            [pm1[7], pm1[8], pm2[7], pm2[8]],
        )

        self.assertEqual(entry.has_warnings, 1)
        self.assertEqual(len(entry.discrepancies_detected), 2)
        booklets_flagged = set()
        for row in entry.discrepancies_detected:
            disc = frappe.get_doc("Purisol Coupon Discrepancy", row.discrepancy)
            booklets_flagged.add(disc.booklet)
            self.assertEqual(disc.discrepancy_type, "Missing Coupons")
        self.assertIn(booklet1, booklets_flagged)
        self.assertIn(booklet2, booklets_flagged)


# ---------------------------------------------------------------------------
# T030 — US2 acceptance scenarios: Unassigned Booklet detection
# ---------------------------------------------------------------------------


def _coupons_for_booklet(booklet_name):
    """Return all coupon names for booklet_name ordered by page_number."""
    return frappe.get_all(
        "Purisol Coupon",
        filters={"booklet": booklet_name},
        fields=["name"],
        order_by="page_number asc",
        pluck="name",
    )


class TestUS2UnassignedBooklet(FrappeTestCase):
    """US2 acceptance scenarios — end-to-end Unassigned Booklet detection."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.emp = make_employee("US2Integ", "Tester")

    # ------------------------------------------------------------------
    # Scenario 1 — In Stock booklet
    # ------------------------------------------------------------------

    def test_unassigned_scenario_1_in_stock_booklet(self):
        """Submit one coupon from an In Stock booklet → one Unassigned Booklet discrepancy."""
        from cx_purisol.cx_purisol.api.booklet_generation import _create_booklet_and_coupons

        booklet_name, _ = _create_booklet_and_coupons(batch_id=None)
        # booklet is In Stock with 20 Available coupons
        coupons = _coupons_for_booklet(booklet_name)

        entry = _submit_entry(self.emp.name, [coupons[0]])

        self.assertEqual(entry.has_warnings, 1)
        self.assertEqual(len(entry.discrepancies_detected), 1)
        disc = frappe.get_doc(
            "Purisol Coupon Discrepancy", entry.discrepancies_detected[0].discrepancy
        )
        self.assertEqual(disc.discrepancy_type, "Unassigned Booklet")
        self.assertEqual(disc.status, "Open")
        self.assertEqual(disc.booklet, booklet_name)
        self.assertIsNone(disc.customer)
        self.assertEqual(len(disc.affected_coupons), 1)
        self.assertEqual(disc.affected_coupons[0].coupon, coupons[0])
        self.assertEqual(disc.triggering_consumption_entry, entry.name)

    # ------------------------------------------------------------------
    # Scenario 2 — In Custody booklet (not Sold)
    # ------------------------------------------------------------------

    def test_unassigned_scenario_2_in_custody_booklet_not_sold(self):
        """Coupon from an In Custody booklet triggers Unassigned Booklet discrepancy."""
        from cx_purisol.cx_purisol.api.booklet_generation import _create_booklet_and_coupons

        booklet_name, _ = _create_booklet_and_coupons(batch_id=None)
        submit_assign([booklet_name], to_delivery_man=self.emp.name)
        coupons = _coupons_for_booklet(booklet_name)

        entry = _submit_entry(self.emp.name, [coupons[0]])

        self.assertEqual(entry.has_warnings, 1)
        disc = frappe.get_doc(
            "Purisol Coupon Discrepancy", entry.discrepancies_detected[0].discrepancy
        )
        self.assertEqual(disc.discrepancy_type, "Unassigned Booklet")

    # ------------------------------------------------------------------
    # Scenario 3 — three coupons from the same In Stock booklet → three records
    # ------------------------------------------------------------------

    def test_unassigned_scenario_3_three_coupons_three_records(self):
        """Three coupons from one In Stock booklet → three distinct Unassigned Booklet records."""
        from cx_purisol.cx_purisol.api.booklet_generation import _create_booklet_and_coupons

        booklet_name, _ = _create_booklet_and_coupons(batch_id=None)
        coupons = _coupons_for_booklet(booklet_name)

        entry = _submit_entry(self.emp.name, coupons[:3])

        self.assertEqual(entry.has_warnings, 1)
        self.assertEqual(len(entry.discrepancies_detected), 3)
        disc_types = {
            frappe.get_doc("Purisol Coupon Discrepancy", r.discrepancy).discrepancy_type
            for r in entry.discrepancies_detected
        }
        self.assertEqual(disc_types, {"Unassigned Booklet"})
        # Each discrepancy covers exactly one coupon
        for row in entry.discrepancies_detected:
            disc = frappe.get_doc("Purisol Coupon Discrepancy", row.discrepancy)
            self.assertEqual(len(disc.affected_coupons), 1)

    # ------------------------------------------------------------------
    # Scenario 4 — mixed entry: Sold coupon is silent, In Stock coupon is flagged
    # ------------------------------------------------------------------

    def test_unassigned_scenario_4_mixed_sold_and_unassigned_in_one_entry(self):
        """One entry with a Sold-booklet coupon + an In Stock coupon → one discrepancy only."""
        from cx_purisol.cx_purisol.api.booklet_generation import _create_booklet_and_coupons

        _, _, _sold_booklet, sold_coupons = make_sold_booklet_ready_for_consumption(
            customer_name="US2Mixed-Customer",
            employee_name="US2Mixed-Emp",
        )
        in_stock_booklet, _ = _create_booklet_and_coupons(batch_id=None)
        in_stock_coupons = _coupons_for_booklet(in_stock_booklet)

        entry = _submit_entry(self.emp.name, [sold_coupons[0], in_stock_coupons[0]])

        self.assertEqual(entry.has_warnings, 1)
        # Exactly one discrepancy: the In Stock coupon
        self.assertEqual(len(entry.discrepancies_detected), 1)
        disc = frappe.get_doc(
            "Purisol Coupon Discrepancy", entry.discrepancies_detected[0].discrepancy
        )
        self.assertEqual(disc.discrepancy_type, "Unassigned Booklet")
        self.assertEqual(disc.affected_coupons[0].coupon, in_stock_coupons[0])

    # ------------------------------------------------------------------
    # Scenario 5 — both anomaly types in one entry (FR-020)
    # ------------------------------------------------------------------

    def test_unassigned_scenario_5_both_anomaly_types_in_one_entry(self):
        """One entry triggers Missing Coupons (Sold booklet gap) AND Unassigned Booklet."""
        from cx_purisol.cx_purisol.api.booklet_generation import _create_booklet_and_coupons

        # Sold booklet: consume pages 1,2 first, then pages 7,8 → gap {3,4,5,6}
        booklet_sold, _ = make_booklet_with_consumed_coupons(
            "US2Both-Customer", self.emp, consumed_pages=(1, 2)
        )
        pm = _page_map(booklet_sold)

        # In Stock booklet
        in_stock_booklet, _ = _create_booklet_and_coupons(batch_id=None)
        in_stock_coupons = _coupons_for_booklet(in_stock_booklet)

        # Single entry: triggers gap on sold booklet + unassigned on In Stock booklet
        entry = _submit_entry(self.emp.name, [pm[7], pm[8], in_stock_coupons[0]])

        self.assertEqual(entry.has_warnings, 1)
        self.assertEqual(len(entry.discrepancies_detected), 2)

        disc_types = set()
        for row in entry.discrepancies_detected:
            disc = frappe.get_doc("Purisol Coupon Discrepancy", row.discrepancy)
            disc_types.add(disc.discrepancy_type)
        self.assertIn("Missing Coupons", disc_types)
        self.assertIn("Unassigned Booklet", disc_types)


# ---------------------------------------------------------------------------
# T034 — US3 Admin Error resolution end-to-end
# ---------------------------------------------------------------------------


class TestAdminErrorResolutionFlow(FrappeTestCase):
    """US3: seeding via detection path → resolve via 'None', no financial docs created."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.emp = make_employee("US3Flow", "Tester")
        self.customer_name = "US3Flow-Customer"
        ensure_customer(self.customer_name)

    def test_admin_error_resolution_end_to_end(self):
        """Full cycle: detection → open discrepancy → Admin Error submit."""
        booklet_name, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1, 2)
        )
        pm = _page_map(booklet_name)
        entry = _submit_entry(self.emp.name, [pm[7], pm[8]])

        self.assertEqual(entry.has_warnings, 1)
        disc_name = entry.discrepancies_detected[0].discrepancy
        disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        self.assertEqual(disc.status, "Open")

        disc.resolution_action = "None"
        disc.resolution_notes = "Confirmed admin error."
        disc.save(ignore_permissions=True)
        disc.submit()
        disc.reload()

        self.assertEqual(disc.status, "Resolved - Admin Error")
        self.assertIsNotNone(disc.resolved_on)
        self.assertFalse(disc.journal_entry)
        self.assertFalse(disc.payment_entry)
        # No JE or PE created
        self.assertFalse(
            frappe.db.exists(
                "Journal Entry", {"user_remark": ["like", f"%{disc_name}%"]}
            )
        )


# ---------------------------------------------------------------------------
# T040 — US4 Liability Ledger resolution end-to-end
# ---------------------------------------------------------------------------


class TestLiabilityResolutionFlow(FrappeTestCase):
    """US4: detection → open discrepancy → 'Add to Liability Ledger' submit → JE created."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.emp = make_employee("US4Flow", "Tester")
        self.customer_name = "US4Flow-Customer"
        ensure_customer(self.customer_name)

    def test_liability_resolution_creates_je(self):
        """End-to-end: detection → open discrepancy → liability submit → JE with correct amounts."""
        configure_purisol_settings_accounts()
        settings = frappe.get_single("Purisol Settings")

        booklet_name, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1, 2)
        )
        pm = _page_map(booklet_name)
        entry = _submit_entry(self.emp.name, [pm[7], pm[8]])
        disc_name = entry.discrepancies_detected[0].discrepancy

        disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        disc.resolution_action = "Add to Liability Ledger"
        disc.liable_delivery_man = self.emp.name
        disc.save(ignore_permissions=True)
        disc.submit()
        disc.reload()

        self.assertEqual(disc.status, "Resolved - Delivery Man Liable")
        self.assertIsNotNone(disc.resolved_on)
        self.assertTrue(disc.journal_entry)
        self.assertFalse(disc.payment_entry)

        je = frappe.get_doc("Journal Entry", disc.journal_entry)
        self.assertEqual(je.docstatus, 1)
        self.assertEqual(je.total_debit, disc.estimated_amount)
        self.assertEqual(je.total_credit, disc.estimated_amount)

        debit_row = next((r for r in je.accounts if r.debit_in_account_currency), None)
        self.assertIsNotNone(debit_row)
        self.assertEqual(debit_row.account, settings.employee_liability_account)
        self.assertEqual(debit_row.party_type, "Employee")
        self.assertEqual(debit_row.party, self.emp.name)

        credit_row = next((r for r in je.accounts if r.credit_in_account_currency), None)
        self.assertIsNotNone(credit_row)
        self.assertEqual(credit_row.account, settings.discrepancy_offset_account)


# ---------------------------------------------------------------------------
# T044 — US5 Cash Payment resolution end-to-end
# ---------------------------------------------------------------------------


class TestCashPaymentResolutionFlow(FrappeTestCase):
    """US5: detection → open discrepancy → 'Immediate Cash Payment' submit → PE created."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.emp = make_employee("US5Flow", "Tester")
        self.customer_name = "US5Flow-Customer"
        ensure_customer(self.customer_name)

    def test_cash_payment_resolution_creates_pe(self):
        """End-to-end: detection → open discrepancy → cash payment submit → PE with correct shape."""
        configure_purisol_settings_accounts()
        settings = frappe.get_single("Purisol Settings")

        booklet_name, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1, 2)
        )
        pm = _page_map(booklet_name)
        entry = _submit_entry(self.emp.name, [pm[7], pm[8]])
        disc_name = entry.discrepancies_detected[0].discrepancy

        disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        disc.resolution_action = "Immediate Cash Payment"
        disc.liable_delivery_man = self.emp.name
        disc.save(ignore_permissions=True)
        disc.submit()
        disc.reload()

        self.assertEqual(disc.status, "Resolved - Paid")
        self.assertIsNotNone(disc.resolved_on)
        self.assertTrue(disc.payment_entry)
        self.assertFalse(disc.journal_entry)

        pe = frappe.get_doc("Payment Entry", disc.payment_entry)
        self.assertEqual(pe.docstatus, 1)
        self.assertEqual(pe.payment_type, "Receive")
        self.assertEqual(pe.paid_from, settings.discrepancy_offset_account)
        self.assertEqual(pe.paid_to, settings.default_cash_account)
        self.assertAlmostEqual(pe.paid_amount, disc.estimated_amount, places=2)
        self.assertAlmostEqual(pe.received_amount, disc.estimated_amount, places=2)
        self.assertEqual(pe.party_type, "Employee")
        self.assertEqual(pe.party, self.emp.name)

        self.assertEqual(len(pe.references), 1)
        ref = pe.references[0]
        self.assertEqual(ref.reference_doctype, "Purisol Coupon Discrepancy")
        self.assertEqual(ref.reference_name, disc_name)
        self.assertAlmostEqual(ref.allocated_amount, disc.estimated_amount, places=2)


# ---------------------------------------------------------------------------
# T045 — Resolution missing preconditions parametrized
# ---------------------------------------------------------------------------


class TestResolutionMissingPreconditions(FrappeTestCase):
    """Contracts §3.5: each of the seven failure modes produces the expected localized message."""

    def setUp(self):
        frappe.set_user("Administrator")
        configure_purisol_settings_accounts()

    def _disc(self):
        return seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=make_booklet_in_stock().name,
            estimated_amount=20.0,
        )

    def _save_settings(self, **kwargs):
        settings = frappe.get_single("Purisol Settings")
        for k, v in kwargs.items():
            setattr(settings, k, v)
        settings.save(ignore_permissions=True)
        frappe.clear_cache()

    def _restore_accounts(self):
        configure_purisol_settings_accounts()
        frappe.clear_cache()

    def test_s1_empty_resolution_action(self):
        disc = frappe.get_doc("Purisol Coupon Discrepancy", self._disc())
        disc.resolution_action = ""
        disc.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError) as ctx:
            disc.submit()
        self.assertIn("Please choose a resolution action", str(ctx.exception))

    def test_s2a_liability_missing_liable_delivery_man(self):
        disc_name = self._disc()
        disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        disc.resolution_action = "Add to Liability Ledger"
        disc.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError) as ctx:
            disc.submit()
        self.assertIn("Liable Delivery Man", str(ctx.exception))

    def test_s2b_liability_missing_employee_liability_account(self):
        self._save_settings(employee_liability_account=None)
        try:
            emp = make_employee("S2b", "Test")
            disc_name = self._disc()
            disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
            disc.resolution_action = "Add to Liability Ledger"
            disc.liable_delivery_man = emp.name
            disc.save(ignore_permissions=True)
            with self.assertRaises(frappe.ValidationError) as ctx:
                disc.submit()
            self.assertIn("Employee liability account", str(ctx.exception))
        finally:
            self._restore_accounts()

    def test_s2c_liability_missing_discrepancy_offset_account(self):
        self._save_settings(discrepancy_offset_account=None)
        try:
            emp = make_employee("S2c", "Test")
            disc_name = self._disc()
            disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
            disc.resolution_action = "Add to Liability Ledger"
            disc.liable_delivery_man = emp.name
            disc.save(ignore_permissions=True)
            with self.assertRaises(frappe.ValidationError) as ctx:
                disc.submit()
            self.assertIn("Discrepancy offset account", str(ctx.exception))
        finally:
            self._restore_accounts()

    def test_s3a_cash_missing_liable_delivery_man(self):
        disc_name = self._disc()
        disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        disc.resolution_action = "Immediate Cash Payment"
        disc.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError) as ctx:
            disc.submit()
        self.assertIn("Liable Delivery Man", str(ctx.exception))

    def test_s3b_cash_missing_discrepancy_offset_account(self):
        self._save_settings(discrepancy_offset_account=None)
        try:
            emp = make_employee("S3b", "Test")
            disc_name = self._disc()
            disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
            disc.resolution_action = "Immediate Cash Payment"
            disc.liable_delivery_man = emp.name
            disc.save(ignore_permissions=True)
            with self.assertRaises(frappe.ValidationError) as ctx:
                disc.submit()
            self.assertIn("Discrepancy offset account", str(ctx.exception))
        finally:
            self._restore_accounts()

    def test_s3c_cash_missing_default_cash_account(self):
        self._save_settings(default_cash_account=None)
        try:
            emp = make_employee("S3c", "Test")
            disc_name = self._disc()
            disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
            disc.resolution_action = "Immediate Cash Payment"
            disc.liable_delivery_man = emp.name
            disc.save(ignore_permissions=True)
            with self.assertRaises(frappe.ValidationError) as ctx:
                disc.submit()
            self.assertIn("Default cash account", str(ctx.exception))
        finally:
            self._restore_accounts()


# ---------------------------------------------------------------------------
# T049 — US6 investigation surfaces (server-side contract)
# ---------------------------------------------------------------------------


class TestUS6InvestigationSurfaces(FrappeTestCase):
    """US6: verify the data shape that the modal and list view read."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.emp = make_employee("US6Invest", "Tester")
        self.customer_name = "US6Invest-Customer"
        ensure_customer(self.customer_name)

    def test_us6_investigation_surfaces(self):
        """Post-submit discrepancies_detected row exists; list filtered to Open shows the record."""
        booklet_name, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1, 2)
        )
        pm = _page_map(booklet_name)
        entry = _submit_entry(self.emp.name, [pm[7], pm[8]])

        # The discrepancies_detected row on the entry is the data source for the modal
        self.assertEqual(entry.has_warnings, 1)
        self.assertGreater(len(entry.discrepancies_detected), 0)
        row = entry.discrepancies_detected[0]
        self.assertTrue(row.discrepancy)

        disc_name = row.discrepancy
        disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
        self.assertEqual(disc.status, "Open")

        # Server-side list-view contract: filter by status=Open returns the record
        open_discs = frappe.get_list(
            "Purisol Coupon Discrepancy",
            filters={"status": "Open"},
            fields=["name"],
            order_by="opened_on desc",
        )
        open_names = [d["name"] for d in open_discs]
        self.assertIn(disc_name, open_names)
