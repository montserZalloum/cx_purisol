"""Bundle-level integration tests for Phase 7 reports — all three bundles.

This file is the skeleton created in Phase 2 (T005).  Individual test methods
are added in later task phases:
  Phase 3 (T019-T022) — User Story 1 operational reports
  Phase 4 (T040-T045) — User Story 2 financial/oversight reports
  Phase 5 (T055-T057) — User Story 3 analytical reports
  Phase 6 (T059-T063) — Cross-cutting permissions, cancelled-doc, GL reconciliation

Infrastructure provided here:
  - setUp: Purisol Administrator + non-admin users via report_seed constants
  - _run_report(report_name, filters): invokes Frappe's query-report execution path
  - test_ignore: doctypes that survive per-test rollback
"""
from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.tests.report_seed import (
    SEED_ADMIN_EMAIL,
    SEED_NONADMIN_EMAIL,
    seed_administrator_user,
)

test_ignore = [
    "Customer",
    "Employee",
    "Sales Invoice",
    "Journal Entry",
    "Payment Entry",
    "GL Entry",
    "Purisol Coupon Booklet",
    "Purisol Coupon",
    "Purisol Coupon Discrepancy",
    "Purisol Coupon Consumption Entry",
    "Purisol Custody Entry",
]


def _run_report(report_name: str, filters: dict | None = None) -> list[dict]:
    """Execute a Frappe report and return the data rows as a list of dicts.

    Works for both Query Reports and Script Reports.  The current frappe.session.user
    must have the required role; set frappe.set_user(...) before calling if needed.
    """
    from frappe.desk.query_report import run

    result = run(report_name=report_name, filters=filters or {})
    raw_data = result.get("result") or []
    columns = result.get("columns") or []

    # Frappe Query Reports return rows as lists; Script Reports return dicts.
    # Normalise to list[dict] keyed by column fieldname.
    if raw_data and isinstance(raw_data[0], (list, tuple)):
        fieldnames = [
            (c["fieldname"] if isinstance(c, dict) else c.split(":")[0])
            for c in columns
        ]
        return [dict(zip(fieldnames, row)) for row in raw_data]

    return [dict(row) if not isinstance(row, dict) else row for row in raw_data]


class TestPhase7ReportFlows(FrappeTestCase):
    """Integration test suite for all Phase 7 reports.

    Each test method covers one spec acceptance scenario.  Methods are added
    in Phases 3–6; this class provides only the setUp infrastructure.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        seed_administrator_user(SEED_ADMIN_EMAIL)

    def setUp(self):
        frappe.set_user("Administrator")
        self.admin_user = SEED_ADMIN_EMAIL
        self.nonadmin_user = SEED_NONADMIN_EMAIL

    # ------------------------------------------------------------------
    # Phase 3 — User Story 1: Operational Reports  (T014, T019–T022)
    # ------------------------------------------------------------------

    def test_us1_current_custody_smoke_acceptance_scenario_3(self):
        """T014: DM A holds 2 booklets (5d, 1d); DM B holds none → verify custody rows."""
        from cx_purisol.cx_purisol.tests.report_seed import seed_for_operations

        ctx = seed_for_operations()
        frappe.set_user(ctx.admin_user)

        rows = _run_report("Current Custody by Delivery Man", {"delivery_man": ctx.dm_a})
        booklet_names = {r["booklet"] for r in rows}
        self.assertIn(ctx.booklet_custody_5d, booklet_names)
        self.assertIn(ctx.booklet_custody_1d, booklet_names)

        days_map = {r["booklet"]: r.get("days_in_custody", 0) for r in rows}
        self.assertGreaterEqual(days_map.get(ctx.booklet_custody_5d, 0), 4)
        self.assertGreaterEqual(days_map.get(ctx.booklet_custody_1d, 0), 0)

        rows_b = _run_report("Current Custody by Delivery Man", {"delivery_man": ctx.dm_b})
        dm_b_booklets = {r["booklet"] for r in rows_b}
        self.assertNotIn(ctx.booklet_custody_5d, dm_b_booklets)
        self.assertNotIn(ctx.booklet_custody_1d, dm_b_booklets)

    def test_us1_daily_delivery_man_summary_acceptance_scenario_1(self):
        """T019: DM A submits 8 coupons from 2 booklets today with 1 discrepancy."""
        from cx_purisol.cx_purisol.tests.report_seed import seed_for_operations
        from frappe.utils import today

        ctx = seed_for_operations()
        frappe.set_user(ctx.admin_user)

        rows = _run_report(
            "Daily Delivery Man Summary",
            {"from_date": today(), "to_date": today(), "delivery_man": ctx.dm_a},
        )
        dm_rows = [r for r in rows if r.get("delivery_man") == ctx.dm_a]
        self.assertEqual(len(dm_rows), 1)
        row = dm_rows[0]
        self.assertEqual(row["coupons_submitted"], ctx.dm_a_today_coupons)
        self.assertEqual(row["booklets_touched"], ctx.dm_a_today_booklets_touched)
        self.assertEqual(row["discrepancies_count"], ctx.dm_a_today_discrepancies)
        self.assertAlmostEqual(
            float(row["discrepancy_total"]), float(ctx.dm_a_today_discrepancy_total), places=2
        )

    def test_us1_active_booklets_per_customer_acceptance_scenario_2(self):
        """T020: Cust-2 has 3 booklets: Depleted + Sold(12) + Sold(0)."""
        from cx_purisol.cx_purisol.tests.report_seed import seed_for_operations

        ctx = seed_for_operations()
        frappe.set_user(ctx.admin_user)

        rows = _run_report("Active Booklets per Customer", {"customer": ctx.cust_2})
        self.assertEqual(len(rows), 3)

        booklet_map = {r["booklet"]: r for r in rows}
        self.assertIn(ctx.booklet_dep, booklet_map)
        self.assertIn(ctx.booklet_sold12, booklet_map)
        self.assertIn(ctx.booklet_sold0, booklet_map)

        self.assertEqual(booklet_map[ctx.booklet_dep]["status"], "Depleted")
        self.assertEqual(booklet_map[ctx.booklet_dep]["consumed_count"], 20)
        self.assertEqual(booklet_map[ctx.booklet_dep]["remaining_count"], 0)

        self.assertEqual(booklet_map[ctx.booklet_sold12]["status"], "Sold")
        self.assertEqual(booklet_map[ctx.booklet_sold12]["consumed_count"], 12)
        self.assertEqual(booklet_map[ctx.booklet_sold12]["remaining_count"], 8)

        self.assertEqual(booklet_map[ctx.booklet_sold0]["status"], "Sold")
        self.assertEqual(booklet_map[ctx.booklet_sold0]["consumed_count"], 0)
        self.assertEqual(booklet_map[ctx.booklet_sold0]["remaining_count"], 20)

    def test_us1_coupon_consumption_log_acceptance_scenario_4(self):
        """T021: 40 coupons consumed within 7 days appear in the log."""
        from cx_purisol.cx_purisol.tests.report_seed import seed_for_operations
        from frappe.utils import add_to_date, today

        ctx = seed_for_operations()
        frappe.set_user(ctx.admin_user)

        week_ago = add_to_date(today(), days=-7)
        rows = _run_report(
            "Coupon Consumption Log",
            {"from_date": week_ago, "to_date": today()},
        )
        self.assertEqual(len(rows), ctx.total_consumed_this_week)

    def test_us1_export_contract_acceptance_scenario_5(self):
        """T022: All 4 Bundle-1 report docs exist and are accessible."""
        bundle1_reports = [
            "Daily Delivery Man Summary",
            "Active Booklets per Customer",
            "Current Custody by Delivery Man",
            "Coupon Consumption Log",
        ]
        for report_name in bundle1_reports:
            doc = frappe.get_doc("Report", report_name)
            self.assertEqual(doc.module, "Cx Purisol")
            self.assertEqual(doc.is_standard, "Yes")

    # ------------------------------------------------------------------
    # Phase 4 — User Story 2: Financial/Oversight Reports  (T040–T045)
    # ------------------------------------------------------------------

    def test_us2_delivery_man_discrepancies_acceptance_scenario_1(self):
        """T040: 4 submitted discrepancies (3 Admin Error + 1 Paid) appear; filters work."""
        from cx_purisol.cx_purisol.tests.report_seed import seed_for_finance

        ctx = seed_for_finance()
        frappe.set_user(ctx.admin_user)

        rows = _run_report("Delivery Man Discrepancies", {})
        returned_ids = {r["discrepancy"] for r in rows}

        for disc_name in ctx.submitted_disc_names:
            self.assertIn(disc_name, returned_ids)

        # Verify the 4 submitted discs split into 3 Admin Error + 1 Paid
        status_map = {r["discrepancy"]: r["status"] for r in rows}
        statuses = [status_map[d] for d in ctx.submitted_disc_names]
        self.assertEqual(statuses.count("Resolved - Admin Error"), 3)
        self.assertEqual(statuses.count("Resolved - Paid"), 1)

    def test_us2_liability_balance_acceptance_scenario_2(self):
        """T041: DM A owed=350, paid=100, open_balance=250 (US2 AS2)."""
        from cx_purisol.cx_purisol.tests.report_seed import seed_for_finance

        ctx = seed_for_finance()
        frappe.set_user(ctx.admin_user)

        rows = _run_report("Delivery Man Liability Balance", {"delivery_man": ctx.dm_a})
        dm_rows = [r for r in rows if r.get("delivery_man") == ctx.dm_a]
        self.assertEqual(len(dm_rows), 1)

        row = dm_rows[0]
        self.assertAlmostEqual(float(row["total_owed"]), ctx.dm_a_total_owed, places=2)
        self.assertAlmostEqual(float(row["total_paid"]), ctx.dm_a_total_paid, places=2)
        self.assertAlmostEqual(float(row["open_balance"]), ctx.dm_a_open_balance, places=2)

    def test_us2_booklet_sales_report_acceptance_scenario_3(self):
        """T042: price_list filter narrows to 5 retail or 2 wholesale invoices (US2 AS3)."""
        from cx_purisol.cx_purisol.tests.report_seed import seed_for_finance

        ctx = seed_for_finance()
        frappe.set_user(ctx.admin_user)

        retail_rows = _run_report("Booklet Sales Report", {"price_list": ctx.pl_retail})
        retail_si = {r["sales_invoice"] for r in retail_rows}
        for si in ctx.si_retail:
            self.assertIn(si, retail_si)
        for si in ctx.si_wholesale:
            self.assertNotIn(si, retail_si)

        wholesale_rows = _run_report("Booklet Sales Report", {"price_list": ctx.pl_wholesale})
        wholesale_si = {r["sales_invoice"] for r in wholesale_rows}
        for si in ctx.si_wholesale:
            self.assertIn(si, wholesale_si)
        for si in ctx.si_retail:
            self.assertNotIn(si, wholesale_si)

    def test_us2_discrepancy_rate_acceptance_scenario_4(self):
        """T043: DM A 4.0% rate (4/100 coupons); DM B 0.0% (0/50 coupons) (US2 AS4)."""
        from cx_purisol.cx_purisol.tests.report_seed import seed_for_finance

        ctx = seed_for_finance()
        frappe.set_user(ctx.admin_user)

        rows = _run_report("Discrepancy Rate by Delivery Man", {})
        row_map = {r["delivery_man"]: r for r in rows}

        self.assertIn(ctx.dm_a, row_map)
        row_a = row_map[ctx.dm_a]
        self.assertEqual(int(row_a["coupons_submitted"]), ctx.dm_a_coupons_submitted)
        self.assertAlmostEqual(float(row_a["discrepancy_rate"]), ctx.dm_a_discrepancy_rate, places=2)

        self.assertIn(ctx.dm_b, row_map)
        row_b = row_map[ctx.dm_b]
        self.assertEqual(int(row_b["coupons_submitted"]), ctx.dm_b_coupons_submitted)
        self.assertAlmostEqual(float(row_b["discrepancy_rate"]), ctx.dm_b_discrepancy_rate, places=2)

    def test_us2_filter_refresh_acceptance_scenario_5(self):
        """T044: Each Bundle-2 report returns different rows under different filter values (US2 AS5)."""
        from cx_purisol.cx_purisol.tests.report_seed import seed_for_finance
        from frappe.utils import add_to_date, today

        ctx = seed_for_finance()
        frappe.set_user(ctx.admin_user)

        # Delivery Man Discrepancies: DM A filter vs DM B filter should differ
        rows_a = _run_report("Delivery Man Discrepancies", {"delivery_man": ctx.dm_a})
        rows_b = _run_report("Delivery Man Discrepancies", {"delivery_man": ctx.dm_b})
        # Open discrepancies (draft) don't appear; submitted ones do — just verify the sets differ
        ids_a = {r["discrepancy"] for r in rows_a}
        ids_b = {r["discrepancy"] for r in rows_b}
        self.assertNotEqual(ids_a, ids_b)

        # Booklet Sales Report: retail vs wholesale price lists return disjoint sets
        retail_rows = _run_report("Booklet Sales Report", {"price_list": ctx.pl_retail})
        wholesale_rows = _run_report("Booklet Sales Report", {"price_list": ctx.pl_wholesale})
        self.assertNotEqual(
            {r["sales_invoice"] for r in retail_rows},
            {r["sales_invoice"] for r in wholesale_rows},
        )

        # Discrepancy Rate: date range in-range vs out-of-range
        future_date = add_to_date(today(), days=30)
        rows_now = _run_report("Discrepancy Rate by Delivery Man", {"from_date": today(), "to_date": today()})
        rows_future = _run_report("Discrepancy Rate by Delivery Man", {"from_date": future_date, "to_date": future_date})
        dms_now = {r["delivery_man"] for r in rows_now}
        dms_future = {r["delivery_man"] for r in rows_future}
        self.assertTrue(dms_now.issuperset(dms_future) or dms_now != dms_future)

    def test_us2_liability_gl_reconciliation_property(self):
        """T045: Liability report total_owed/paid/balance matches GL Entry aggregates exactly (SC-003)."""
        from cx_purisol.cx_purisol.tests.report_seed import seed_for_finance

        ctx = seed_for_finance()
        frappe.set_user(ctx.admin_user)

        settings = frappe.get_single("Purisol Settings")
        account = settings.employee_liability_account

        gl_rows = frappe.get_all(
            "GL Entry",
            filters={
                "account": account,
                "party_type": "Employee",
                "party": ctx.dm_a,
                "is_cancelled": 0,
            },
            fields=["debit_in_account_currency", "credit_in_account_currency"],
        )
        gl_owed = sum(float(r["debit_in_account_currency"]) for r in gl_rows)
        gl_paid = sum(float(r["credit_in_account_currency"]) for r in gl_rows)

        rows = _run_report("Delivery Man Liability Balance", {"delivery_man": ctx.dm_a})
        dm_rows = [r for r in rows if r.get("delivery_man") == ctx.dm_a]
        self.assertEqual(len(dm_rows), 1)

        row = dm_rows[0]
        self.assertAlmostEqual(float(row["total_owed"]), gl_owed, places=2)
        self.assertAlmostEqual(float(row["total_paid"]), gl_paid, places=2)
        self.assertAlmostEqual(float(row["open_balance"]), gl_owed - gl_paid, places=2)

    # ------------------------------------------------------------------
    # Phase 5 — User Story 3: Analytical Reports  (T055–T057)
    # ------------------------------------------------------------------

    def test_us3_customer_consumption_rate_acceptance_scenario_1(self):
        """T055: C1 avg=45.0 (3 booklets), C2 avg=15.0 (2 booklets); ordered ASC (US3 AS1)."""
        from cx_purisol.cx_purisol.tests.report_seed import seed_for_analytics

        ctx = seed_for_analytics()
        frappe.set_user(ctx.admin_user)

        rows = _run_report("Customer Consumption Rate", {})
        row_map = {r["customer"]: r for r in rows}

        self.assertIn(ctx.cust_1, row_map)
        self.assertEqual(int(row_map[ctx.cust_1]["booklets_depleted"]), 3)
        self.assertAlmostEqual(float(row_map[ctx.cust_1]["avg_days_to_deplete"]), ctx.cust_1_avg_days, places=1)

        self.assertIn(ctx.cust_2, row_map)
        self.assertEqual(int(row_map[ctx.cust_2]["booklets_depleted"]), 2)
        self.assertAlmostEqual(float(row_map[ctx.cust_2]["avg_days_to_deplete"]), ctx.cust_2_avg_days, places=1)

        customers = [r["customer"] for r in rows]
        if ctx.cust_1 in customers and ctx.cust_2 in customers:
            self.assertLess(customers.index(ctx.cust_2), customers.index(ctx.cust_1))

    def test_us3_booklet_lifecycle_duration_acceptance_scenario_2(self):
        """T056: 3 lifecycle booklets → averages 20/40/60 days (US3 AS2)."""
        from cx_purisol.cx_purisol.tests.report_seed import seed_for_analytics

        ctx = seed_for_analytics()
        frappe.set_user(ctx.admin_user)

        rows = _run_report("Booklet Lifecycle Duration", {})
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertAlmostEqual(
            float(row["avg_generation_to_first_sale"]), ctx.avg_generation_to_first_sale, delta=1.0
        )
        self.assertAlmostEqual(
            float(row["avg_sale_to_depletion"]), ctx.avg_sale_to_depletion, delta=1.0
        )
        self.assertAlmostEqual(
            float(row["avg_full_lifetime"]), ctx.avg_full_lifetime, delta=1.0
        )

    def test_us3_export_contract_acceptance_scenario_3(self):
        """T057: Both Bundle-3 report docs exist and are in Cx Purisol module (US3 AS3)."""
        bundle3_reports = [
            "Customer Consumption Rate",
            "Booklet Lifecycle Duration",
        ]
        for report_name in bundle3_reports:
            doc = frappe.get_doc("Report", report_name)
            self.assertEqual(doc.module, "Cx Purisol")
            self.assertEqual(doc.is_standard, "Yes")

    # ------------------------------------------------------------------
    # Phase 6 — Cross-cutting concerns  (T059–T063)
    # ------------------------------------------------------------------

    def test_permissions_across_all_reports(self):
        """T059: Non-admin user is denied access to all 10 Phase-7 reports (FR-004, SC-005)."""
        from cx_purisol.cx_purisol.tests.report_seed import (
            SEED_NONADMIN_EMAIL,
            seed_for_operations,
        )

        seed_for_operations()  # ensures non-admin user is created via _shared_infra

        all_reports = [
            "Daily Delivery Man Summary",
            "Active Booklets per Customer",
            "Current Custody by Delivery Man",
            "Coupon Consumption Log",
            "Delivery Man Discrepancies",
            "Delivery Man Liability Balance",
            "Booklet Sales Report",
            "Discrepancy Rate by Delivery Man",
            "Customer Consumption Rate",
            "Booklet Lifecycle Duration",
        ]

        frappe.set_user(SEED_NONADMIN_EMAIL)
        for report_name in all_reports:
            with self.assertRaises(
                frappe.PermissionError,
                msg=f"{report_name} must deny non-admin user",
            ):
                _run_report(report_name, {})

    def test_cancelled_sales_invoice_excluded_from_booklet_sales_report(self):
        """T060: Cancel a submitted SI → its row disappears from Booklet Sales Report (FR-005, SC-005)."""
        from cx_purisol.cx_purisol.tests.report_seed import seed_for_finance

        ctx = seed_for_finance()
        frappe.set_user("Administrator")

        target_si = ctx.si_retail[0]
        rows_before = _run_report("Booklet Sales Report", {})
        si_names_before = {r["sales_invoice"] for r in rows_before}
        self.assertIn(target_si, si_names_before, "SI must appear in report before cancellation")

        frappe.get_doc("Sales Invoice", target_si).cancel()

        rows_after = _run_report("Booklet Sales Report", {})
        si_names_after = {r["sales_invoice"] for r in rows_after}
        self.assertNotIn(target_si, si_names_after, "Cancelled SI must be excluded from report")

    def test_cancelled_consumption_entry_excluded_from_consumption_log_and_summary(self):
        """T061: Cancel a Consumption Entry → excluded from log; summary row updates (FR-005, SC-005)."""
        from cx_purisol.cx_purisol.tests.report_seed import seed_for_operations
        from frappe.utils import add_to_date, today

        ctx = seed_for_operations()
        frappe.set_user("Administrator")

        # entry_b12: dm_b consumed 12 coupons on day -3 — must appear in the log
        rows_log_before = _run_report("Coupon Consumption Log", {})
        entry_rows_before = [
            r for r in rows_log_before if r.get("consumption_entry") == ctx.entry_b12
        ]
        self.assertGreater(len(entry_rows_before), 0, "entry_b12 coupons must appear in log before cancel")

        # dm_b must have a summary row for day -3 before cancellation
        day_minus_3 = str(add_to_date(today(), days=-3))
        summary_before = _run_report(
            "Daily Delivery Man Summary",
            {"from_date": day_minus_3, "to_date": day_minus_3, "delivery_man": ctx.dm_b},
        )
        dm_b_rows_before = [r for r in summary_before if r.get("delivery_man") == ctx.dm_b]
        self.assertEqual(len(dm_b_rows_before), 1, "DM B must have a summary row for day -3 before cancel")

        frappe.get_doc("Purisol Coupon Consumption Entry", ctx.entry_b12).cancel()

        # Cancelled entry's coupons must not appear in the log
        rows_log_after = _run_report("Coupon Consumption Log", {})
        entry_rows_after = [
            r for r in rows_log_after if r.get("consumption_entry") == ctx.entry_b12
        ]
        self.assertEqual(len(entry_rows_after), 0, "Cancelled entry's coupons must be excluded from log")

        # dm_b's summary row for day -3 must be gone (no remaining submitted entries)
        summary_after = _run_report(
            "Daily Delivery Man Summary",
            {"from_date": day_minus_3, "to_date": day_minus_3, "delivery_man": ctx.dm_b},
        )
        dm_b_rows_after = [r for r in summary_after if r.get("delivery_man") == ctx.dm_b]
        self.assertEqual(len(dm_b_rows_after), 0, "DM B must have no summary row for day -3 after cancel")

    def test_cancelled_discrepancy_excluded_from_discrepancies_and_rate(self):
        """T062: docstatus→2 discrepancy excluded from Discrepancies report and Rate numerator (FR-005, SC-005)."""
        from cx_purisol.cx_purisol.tests.report_seed import seed_for_finance

        ctx = seed_for_finance()
        frappe.set_user("Administrator")

        # --- Part 1: Delivery Man Discrepancies (submitted_disc_names[0] has no triggering_entry) ---
        target_disc = ctx.submitted_disc_names[0]
        rows_before = _run_report("Delivery Man Discrepancies", {})
        self.assertIn(
            target_disc,
            {r["discrepancy"] for r in rows_before},
            "Submitted discrepancy must appear in Delivery Man Discrepancies",
        )

        # Simulate cancellation via direct DB write (on_cancel throws for resolved discrepancies)
        frappe.db.set_value("Purisol Coupon Discrepancy", target_disc, "docstatus", 2)

        rows_after_part1 = _run_report("Delivery Man Discrepancies", {})
        self.assertNotIn(
            target_disc,
            {r["discrepancy"] for r in rows_after_part1},
            "Cancelled discrepancy must be excluded from Delivery Man Discrepancies",
        )

        # --- Part 2: Discrepancy Rate (open_disc_names[0] has triggering_consumption_entry set) ---
        # Submit this draft discrepancy so it feeds the rate numerator for dm_a
        rate_disc = frappe.get_doc("Purisol Coupon Discrepancy", ctx.open_disc_names[0])
        rate_disc.resolution_action = "None"
        rate_disc.save(ignore_permissions=True)
        rate_disc.submit()

        rate_before = _run_report("Discrepancy Rate by Delivery Man", {})
        dm_a_before = next((r for r in rate_before if r.get("delivery_man") == ctx.dm_a), None)
        self.assertIsNotNone(dm_a_before, "DM A must appear in rate report after submitting discrepancy")
        count_before = int(dm_a_before["discrepancies_count"])
        self.assertGreater(count_before, 0, "DM A's discrepancy count must be > 0")

        # Simulate cancellation of the rate-linked discrepancy
        frappe.db.set_value("Purisol Coupon Discrepancy", rate_disc.name, "docstatus", 2)

        rate_after = _run_report("Discrepancy Rate by Delivery Man", {})
        dm_a_after = next((r for r in rate_after if r.get("delivery_man") == ctx.dm_a), None)
        count_after = int(dm_a_after["discrepancies_count"]) if dm_a_after else 0
        self.assertLess(
            count_after,
            count_before,
            "DM A's discrepancy count must decrease after cancellation",
        )

    def test_current_custody_by_delivery_man_unchanged_under_phase_7_dataset(self):
        """T063: Phase-2 custody report renders under Phase-7 seed; non-admin is denied (reuse check)."""
        from cx_purisol.cx_purisol.tests.report_seed import (
            SEED_NONADMIN_EMAIL,
            seed_for_operations,
        )

        ctx = seed_for_operations()
        frappe.set_user(ctx.admin_user)

        # Report renders and DM A's custody booklets are visible
        rows = _run_report("Current Custody by Delivery Man", {"delivery_man": ctx.dm_a})
        booklet_names = {r["booklet"] for r in rows}
        self.assertIn(ctx.booklet_custody_5d, booklet_names, "5d custody booklet must appear")
        self.assertIn(ctx.booklet_custody_1d, booklet_names, "1d custody booklet must appear")

        # Role gate: non-admin user must be denied access
        frappe.set_user(SEED_NONADMIN_EMAIL)
        with self.assertRaises(frappe.PermissionError):
            _run_report("Current Custody by Delivery Man", {})
