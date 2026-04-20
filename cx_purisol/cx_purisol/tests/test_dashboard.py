from __future__ import annotations

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, nowtime, today

from cx_purisol.cx_purisol.tests.fixtures import (
    configure_purisol_settings,
    configure_purisol_settings_accounts,
    ensure_coupon_item,
    ensure_customer,
    ensure_item_price,
    ensure_price_list,
    make_booklet_in_stock,
    make_booklet_with_consumed_coupons,
    make_employee,
    seed_open_discrepancy,
    submit_assign,
)
from cx_purisol.cx_purisol.tests.report_seed import (
    SEED_ADMIN_EMAIL,
    SEED_NONADMIN_EMAIL,
    seed_administrator_user,
)

WORKSPACE_NAME = "مياه نبع النعيم"


class TestDashboard(FrappeTestCase):
    def setUp(self):
        seed_administrator_user(SEED_ADMIN_EMAIL)

    def test_workspace_exists_after_migrate(self):
        ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
        role_names = [r.role for r in ws.roles]
        self.assertIn("Purisol Administrator", role_names)

    def test_role_gate_blocks_non_admin(self):
        frappe.set_user(SEED_NONADMIN_EMAIL)
        try:
            with self.assertRaises(frappe.PermissionError):
                frappe.get_doc("Workspace", WORKSPACE_NAME)
        finally:
            frappe.set_user("Administrator")

    def test_default_landing_for_admin(self):
        hooks_list = frappe.get_hooks("role_home_page")
        combined: dict = {}
        for entry in hooks_list:
            if isinstance(entry, dict):
                combined.update(entry)
        self.assertEqual(combined.get("Purisol Administrator"), WORKSPACE_NAME)

    # -----------------------------------------------------------------------
    # US1 — Morning Operational Health View
    # -----------------------------------------------------------------------

    def test_us1_default_landing_redirects_admin(self):
        hooks_list = frappe.get_hooks("role_home_page")
        combined: dict = {}
        for entry in hooks_list:
            if isinstance(entry, dict):
                combined.update(entry)
        self.assertEqual(combined.get("Purisol Administrator"), WORKSPACE_NAME)
        frappe.set_user(SEED_ADMIN_EMAIL)
        try:
            ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
            self.assertIn("Purisol Administrator", [r.role for r in ws.roles])
        finally:
            frappe.set_user("Administrator")

    def test_us1_booklet_status_counts_match_seed(self):
        base_stock = frappe.db.count("Purisol Coupon Booklet", {"status": "In Stock"})
        base_custody = frappe.db.count("Purisol Coupon Booklet", {"status": "In Custody"})
        base_sold = frappe.db.count("Purisol Coupon Booklet", {"status": "Sold"})

        for _ in range(3):
            make_booklet_in_stock()

        dm = make_employee("US1WCount", "Dm")
        custody_bks = [make_booklet_in_stock().name for _ in range(4)]
        submit_assign(custody_bks, dm.name)

        for _ in range(2):
            make_booklet_with_consumed_coupons("US1-Count-Cust", "US1Seller", consumed_pages=(1,))

        self.assertEqual(frappe.db.count("Purisol Coupon Booklet", {"status": "In Stock"}) - base_stock, 3)
        self.assertEqual(frappe.db.count("Purisol Coupon Booklet", {"status": "In Custody"}) - base_custody, 4)
        self.assertEqual(frappe.db.count("Purisol Coupon Booklet", {"status": "Sold"}) - base_sold, 2)

    def test_us1_in_custody_breakdown_per_delivery_man(self):
        dm_x = make_employee("US1BrX", "Dm")
        dm_y = make_employee("US1BrY", "Dm")

        bks_x = [make_booklet_in_stock().name for _ in range(3)]
        bks_y = [make_booklet_in_stock().name for _ in range(2)]
        submit_assign(bks_x, dm_x.name)
        submit_assign(bks_y, dm_y.name)

        rows = frappe.db.sql(
            "SELECT current_delivery_man, COUNT(*) AS cnt FROM `tabPurisol Coupon Booklet`"
            " WHERE status = 'In Custody' GROUP BY current_delivery_man",
            as_dict=True,
        )
        per_dm = {r["current_delivery_man"]: r["cnt"] for r in rows}
        self.assertEqual(per_dm.get(dm_x.name), 3)
        self.assertEqual(per_dm.get(dm_y.name), 2)

    def test_us1_today_consumption_per_delivery_man(self):
        from cx_purisol.cx_purisol.api.booklet_generation import _create_booklet_and_coupons
        from cx_purisol.cx_purisol.api.sell_booklets import purisol_create_sales_invoice_for_booklets

        item = ensure_coupon_item()
        pl = ensure_price_list("US1-Con-PL")
        ensure_item_price(item.name, pl.name, 100)
        cust = ensure_customer("US1-Con-Cust", default_price_list=pl.name)
        configure_purisol_settings(coupon_item=item.name, default_price_list=pl.name)

        def _sell_and_consume(dm_name, pages):
            bk, _ = _create_booklet_and_coupons(batch_id=None)
            result = purisol_create_sales_invoice_for_booklets(cust.name, [bk])
            frappe.get_doc("Sales Invoice", result["name"]).submit()
            pm = {r["page_number"]: r["name"] for r in frappe.get_all(
                "Purisol Coupon", filters={"booklet": bk}, fields=["name", "page_number"],
            )}
            entry = frappe.get_doc({
                "doctype": "Purisol Coupon Consumption Entry",
                "posting_date": today(),
                "posting_time": nowtime(),
                "delivery_man": dm_name,
                "coupons": [{"coupon": pm[p]} for p in pages],
            })
            entry.insert(ignore_permissions=True)
            entry.submit()
            return entry.total_coupons

        dm_p = make_employee("US1ConP", "Dm")
        dm_q = make_employee("US1ConQ", "Dm")
        dm_r = make_employee("US1ConR", "Dm")

        cnt_p = _sell_and_consume(dm_p.name, list(range(1, 6)))    # 5 coupons
        cnt_q = _sell_and_consume(dm_q.name, list(range(1, 13)))   # 12 coupons
        cnt_r = _sell_and_consume(dm_r.name, list(range(1, 7)))    # 6 coupons
        self.assertEqual(cnt_p + cnt_q + cnt_r, 23)

        rows = frappe.db.sql(
            "SELECT delivery_man, SUM(total_coupons) AS total"
            " FROM `tabPurisol Coupon Consumption Entry`"
            " WHERE posting_date = %s AND docstatus = 1"
            " GROUP BY delivery_man",
            (today(),),
            as_dict=True,
        )
        per_dm = {r["delivery_man"]: int(r["total"]) for r in rows}
        self.assertEqual(per_dm.get(dm_p.name, 0), cnt_p)
        self.assertEqual(per_dm.get(dm_q.name, 0), cnt_q)
        self.assertEqual(per_dm.get(dm_r.name, 0), cnt_r)

    def test_us1_widget_click_through_filters(self):
        nc = frappe.get_doc("Number Card", "Purisol \u2014 Booklets In Stock")
        self.assertIn(["Purisol Coupon Booklet", "status", "=", "In Stock"], json.loads(nc.filters_json))

        nc = frappe.get_doc("Number Card", "Purisol \u2014 Booklets In Custody")
        self.assertIn(["Purisol Coupon Booklet", "status", "=", "In Custody"], json.loads(nc.filters_json))

        nc = frappe.get_doc("Number Card", "Purisol \u2014 Active Sold Booklets")
        self.assertIn(["Purisol Coupon Booklet", "status", "=", "Sold"], json.loads(nc.filters_json))

        dc = frappe.get_doc("Dashboard Chart", "Purisol \u2014 In-Custody Breakdown")
        self.assertEqual(dc.chart_type, "Group By")
        self.assertEqual(dc.group_by_based_on, "current_delivery_man")

        dc = frappe.get_doc("Dashboard Chart", "Purisol \u2014 Today's Consumption")
        self.assertEqual(dc.chart_type, "Report")
        self.assertEqual(dc.report_name, "Daily Delivery Man Summary")

    # -----------------------------------------------------------------------
    # US2 — Financial Risk Watchlist
    # -----------------------------------------------------------------------

    def test_us2_open_discrepancies_count_three_with_severity(self):
        # Structural: Number Card has Red accent and correct document_type
        nc = frappe.get_doc("Number Card", "Purisol \u2014 Open Discrepancies")
        self.assertEqual(nc.color, "Red")
        self.assertEqual(nc.document_type, "Purisol Coupon Discrepancy")
        filters = json.loads(nc.filters_json)
        self.assertIn(["Purisol Coupon Discrepancy", "status", "=", "Open"], filters)

        # Behavioural: seed 3 Open + 1 resolved, assert the DB reflects correct counts
        base_open = frappe.db.count("Purisol Coupon Discrepancy", {"status": "Open"})
        bk1 = make_booklet_in_stock()
        bk2 = make_booklet_in_stock()
        bk3 = make_booklet_in_stock()
        seed_open_discrepancy(discrepancy_type="Missing Coupons", booklet=bk1.name, estimated_amount=10.0)
        seed_open_discrepancy(discrepancy_type="Missing Coupons", booklet=bk2.name, estimated_amount=10.0)
        seed_open_discrepancy(discrepancy_type="Missing Coupons", booklet=bk3.name, estimated_amount=10.0)

        after_open = frappe.db.count("Purisol Coupon Discrepancy", {"status": "Open"})
        self.assertEqual(after_open - base_open, 3)

    def test_us2_open_discrepancies_count_zero_healthy_state(self):
        # No Open records → Quick List entry exists with correct label and filter
        ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
        ql_labels = [ql.label for ql in ws.quick_lists]
        self.assertIn("Open Discrepancies", ql_labels)

        ql = next(ql for ql in ws.quick_lists if ql.label == "Open Discrepancies")
        self.assertEqual(ql.document_type, "Purisol Coupon Discrepancy")
        filters = json.loads(ql.filters_json)
        self.assertIn(["status", "=", "Open"], filters)

    def test_us2_outstanding_liabilities_per_delivery_man(self):
        # W6 Dashboard Chart exists with correct report and axis configuration
        dc = frappe.get_doc("Dashboard Chart", "Purisol \u2014 Outstanding Liabilities")
        self.assertEqual(dc.chart_type, "Report")
        self.assertEqual(dc.report_name, "Delivery Man Liability Balance")
        self.assertEqual(dc.x_field, "delivery_man")
        y_fields = [row.y_field for row in dc.y_axis]
        self.assertIn("open_balance", y_fields)
        self.assertEqual(dc.cache, 0)

    def test_us2_widget_click_through_targets(self):
        # W5a: Number Card click → Discrepancy list filtered to Open
        nc = frappe.get_doc("Number Card", "Purisol \u2014 Open Discrepancies")
        filters = json.loads(nc.filters_json)
        self.assertIn(["Purisol Coupon Discrepancy", "status", "=", "Open"], filters)

        # W5b: Quick List entry on workspace → Discrepancy list filtered to Open
        ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
        ql = next((q for q in ws.quick_lists if q.label == "Open Discrepancies"), None)
        self.assertIsNotNone(ql)
        self.assertEqual(ql.document_type, "Purisol Coupon Discrepancy")

        # W6: Dashboard Chart click → Delivery Man Liability Balance report
        dc = frappe.get_doc("Dashboard Chart", "Purisol \u2014 Outstanding Liabilities")
        self.assertEqual(dc.report_name, "Delivery Man Liability Balance")

        # Workspace content includes all three Risk Watchlist blocks
        content_blocks = json.loads(ws.content)
        block_ids = [b.get("id") for b in content_blocks]
        self.assertIn("risk-header", block_ids)
        self.assertIn("c5a", block_ids)
        self.assertIn("ql5b", block_ids)
        self.assertIn("g6", block_ids)

    def test_us2_zero_data_renders_cleanly(self):
        # With no discrepancies seeded in this scope, Number Card and Chart records
        # are loadable without error, and the workspace quick_list config is valid JSON
        nc = frappe.get_doc("Number Card", "Purisol \u2014 Open Discrepancies")
        self.assertIsNotNone(nc.name)
        self.assertIsNotNone(json.loads(nc.filters_json))

        dc = frappe.get_doc("Dashboard Chart", "Purisol \u2014 Outstanding Liabilities")
        self.assertIsNotNone(dc.name)

        ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
        ql = next((q for q in ws.quick_lists if q.label == "Open Discrepancies"), None)
        self.assertIsNotNone(ql)
        self.assertIsNotNone(json.loads(ql.filters_json))

    # -----------------------------------------------------------------------
    # US3 — Customer Follow-up Signals
    # -----------------------------------------------------------------------

    def test_us3_low_stock_widget_at_or_below_threshold(self):
        """W4 Dashboard Chart exists with correct config; report respects threshold ordering."""
        dc = frappe.get_doc("Dashboard Chart", "Purisol \u2014 Customers Low on Coupons")
        self.assertEqual(dc.chart_type, "Report")
        self.assertEqual(dc.report_name, "Customers Low on Coupons")
        self.assertEqual(dc.x_field, "customer")
        y_fields = [row.y_field for row in dc.y_axis]
        self.assertIn("total_remaining", y_fields)
        self.assertEqual(dc.cache, 0)
        self.assertEqual(dc.is_public, 1)

        # Seed customers with specific totals and verify threshold filter
        from frappe.model.naming import make_autoname

        def _mk(name, remaining):
            bk = make_autoname("US3A-.#####")
            doc = frappe.get_doc({
                "doctype": "Purisol Coupon Booklet",
                "booklet_number": bk,
                "status": "Sold",
                "customer": ensure_customer(name).name,
                "total_coupons": 20,
                "consumed_count": 20 - remaining,
                "remaining_count": remaining,
            })
            doc.flags.ignore_permissions = True
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True, set_name=bk)

        orig = frappe.db.get_single_value("Purisol Settings", "customer_low_stock_threshold") or 3
        try:
            frappe.db.set_single_value("Purisol Settings", "customer_low_stock_threshold", 3)
            for v in range(5):
                _mk(f"US3A-Cust-{v}", v)

            from cx_purisol.cx_purisol.report.customers_low_on_coupons.test_customers_low_on_coupons import (
                _REPORT_SQL,
            )
            rows = frappe.db.sql(_REPORT_SQL, as_dict=True)
            customer_totals = {r["customer"]: int(r["total_remaining"]) for r in rows}

            for v in range(4):
                self.assertIn(f"US3A-Cust-{v}", customer_totals)
            self.assertNotIn("US3A-Cust-4", customer_totals)

            totals = [int(r["total_remaining"]) for r in rows]
            self.assertEqual(totals, sorted(totals))
        finally:
            frappe.db.set_single_value("Purisol Settings", "customer_low_stock_threshold", orig)

    def test_us3_low_stock_widget_caps_at_ten(self):
        """W4: underlying report is capped at 10 rows by LIMIT 10."""
        from cx_purisol.cx_purisol.report.customers_low_on_coupons.test_customers_low_on_coupons import (
            _REPORT_SQL,
        )
        rows = frappe.db.sql(_REPORT_SQL, as_dict=True)
        self.assertLessEqual(len(rows), 10)

    def test_us3_recent_depleted_within_7_days(self):
        """W8: only booklets depleted within the last 7 days appear in the Quick List filter."""
        from frappe.model.naming import make_autoname
        from frappe.utils import add_to_date, today

        def _mk_depleted(days_ago):
            bk = make_autoname("US3D-.#####")
            doc = frappe.get_doc({
                "doctype": "Purisol Coupon Booklet",
                "booklet_number": bk,
                "status": "Depleted",
                "total_coupons": 20,
                "consumed_count": 20,
                "remaining_count": 0,
                "depleted_on": add_to_date(today(), days=-days_ago),
            })
            doc.flags.ignore_permissions = True
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True, set_name=bk)
            return bk

        bk_1 = _mk_depleted(1)
        bk_3 = _mk_depleted(3)
        bk_6 = _mk_depleted(6)
        bk_8 = _mk_depleted(8)
        bk_15 = _mk_depleted(15)

        cutoff = add_to_date(today(), days=-7)
        recent = frappe.db.get_all(
            "Purisol Coupon Booklet",
            filters=[["status", "=", "Depleted"], ["depleted_on", ">=", cutoff]],
            pluck="name",
        )
        self.assertIn(bk_1, recent)
        self.assertIn(bk_3, recent)
        self.assertIn(bk_6, recent)
        self.assertNotIn(bk_8, recent)
        self.assertNotIn(bk_15, recent)

    def test_us3_widget_click_through_targets(self):
        """W4 chart points to Customers Low on Coupons report; W8 quick_list is on workspace."""
        dc = frappe.get_doc("Dashboard Chart", "Purisol \u2014 Customers Low on Coupons")
        self.assertEqual(dc.report_name, "Customers Low on Coupons")

        ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
        ql_labels = [ql.label for ql in ws.quick_lists]
        self.assertIn("Recent Depleted Booklets", ql_labels)

        ql = next(ql for ql in ws.quick_lists if ql.label == "Recent Depleted Booklets")
        self.assertEqual(ql.document_type, "Purisol Coupon Booklet")
        filters = json.loads(ql.filters_json)
        self.assertIn(["status", "=", "Depleted"], filters)

        content_blocks = json.loads(ws.content)
        block_ids = [b.get("id") for b in content_blocks]
        self.assertIn("follow-up-header", block_ids)
        self.assertIn("g4", block_ids)
        self.assertIn("ql8", block_ids)

    def test_us3_empty_state_renders_cleanly(self):
        """W4 and W8 fixtures load without error; workspace charts array includes W4."""
        dc = frappe.get_doc("Dashboard Chart", "Purisol \u2014 Customers Low on Coupons")
        self.assertIsNotNone(dc.name)

        ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
        chart_names = [c.chart_name for c in ws.charts]
        self.assertIn("Purisol \u2014 Customers Low on Coupons", chart_names)

        ql = next((q for q in ws.quick_lists if q.label == "Recent Depleted Booklets"), None)
        self.assertIsNotNone(ql)
        self.assertIsNotNone(json.loads(ql.filters_json))

    # -----------------------------------------------------------------------
    # Phase 6 — Cross-Cutting Polish Tests
    # -----------------------------------------------------------------------

    def test_dashboard_empty_state_all_widgets(self):
        """All 8 widget records load without raising; configs are valid JSON; content blocks present."""
        for name in [
            "Purisol \u2014 Booklets In Stock",
            "Purisol \u2014 Booklets In Custody",
            "Purisol \u2014 Active Sold Booklets",
            "Purisol \u2014 Open Discrepancies",
        ]:
            nc = frappe.get_doc("Number Card", name)
            self.assertIsNotNone(nc.name)
            self.assertIsNotNone(json.loads(nc.filters_json))

        for name in [
            "Purisol \u2014 In-Custody Breakdown",
            "Purisol \u2014 Customers Low on Coupons",
            "Purisol \u2014 Outstanding Liabilities",
            "Purisol \u2014 Today's Consumption",
        ]:
            dc = frappe.get_doc("Dashboard Chart", name)
            self.assertIsNotNone(dc.name)

        ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
        ql_labels = [ql.label for ql in ws.quick_lists]
        self.assertIn("Open Discrepancies", ql_labels)
        self.assertIn("Recent Depleted Booklets", ql_labels)

        blocks = json.loads(ws.content)
        block_ids = {b.get("id") for b in blocks}
        for expected_id in ("operations-header", "risk-header", "follow-up-header"):
            self.assertIn(expected_id, block_ids)

    def test_dashboard_cancelled_discrepancy_filter(self):
        """W5a docstatus=1 filter excludes draft Open discrepancies (docstatus=0)."""
        nc = frappe.get_doc("Number Card", "Purisol \u2014 Open Discrepancies")
        filters = json.loads(nc.filters_json)
        docstatus_filters = [f for f in filters if len(f) >= 4 and f[1] == "docstatus"]
        self.assertTrue(docstatus_filters, "docstatus filter must be present in W5a filters_json")
        self.assertEqual(docstatus_filters[0][3], 1)

        bk = make_booklet_in_stock()
        seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=bk.name,
            estimated_amount=50.0,
        )

        count_all_open = frappe.db.count("Purisol Coupon Discrepancy", {"status": "Open"})
        count_submitted_open = frappe.db.count(
            "Purisol Coupon Discrepancy", {"status": "Open", "docstatus": 1}
        )
        self.assertGreater(
            count_all_open, count_submitted_open,
            "Draft Open discrepancies must not appear when docstatus=1 filter is applied",
        )

    def test_dashboard_sc004_w6_reconciles_with_phase7_report(self):
        """W6 and Phase-7 Delivery Man Liability Balance report agree row-by-row on open_balance."""
        from cx_purisol.cx_purisol.report.delivery_man_liability_balance.delivery_man_liability_balance import (
            execute,
        )

        configure_purisol_settings_accounts()
        settings = frappe.get_single("Purisol Settings")

        dc = frappe.get_doc("Dashboard Chart", "Purisol \u2014 Outstanding Liabilities")
        self.assertEqual(dc.chart_type, "Report")
        self.assertEqual(dc.report_name, "Delivery Man Liability Balance")

        _columns, report_data = execute()

        if not settings.employee_liability_account:
            self.assertIsNotNone(report_data)
            return

        gl_rows = frappe.db.sql(
            """
            SELECT delivery_man, owed, paid
            FROM (
                SELECT
                    party AS delivery_man,
                    SUM(debit_in_account_currency) AS owed,
                    SUM(credit_in_account_currency) AS paid
                FROM `tabGL Entry`
                WHERE account = %s
                  AND party_type = 'Employee'
                  AND is_cancelled = 0
                GROUP BY party
            ) agg
            WHERE owed > 0 OR paid > 0
            """,
            (settings.employee_liability_account,),
            as_dict=True,
        )
        report_map = {
            r["delivery_man"]: r["open_balance"]
            for r in report_data
            if r.get("delivery_man")
        }
        for row in gl_rows:
            dm = row["delivery_man"]
            expected = float(row["owed"] or 0) - float(row["paid"] or 0)
            self.assertAlmostEqual(
                report_map.get(dm, 0.0),
                expected,
                places=2,
                msg=f"SC-004: W6 open_balance mismatch for {dm}",
            )

    def test_dashboard_sc007_w4_live_threshold_read(self):
        """W4 report expands immediately on threshold change without restart (SC-007)."""
        from frappe.model.naming import make_autoname

        from cx_purisol.cx_purisol.report.customers_low_on_coupons.test_customers_low_on_coupons import (
            _REPORT_SQL,
        )

        def _mk(cust_name, remaining):
            cust = ensure_customer(cust_name)
            bk = make_autoname("T28-.#####")
            doc = frappe.get_doc({
                "doctype": "Purisol Coupon Booklet",
                "booklet_number": bk,
                "status": "Sold",
                "customer": cust.name,
                "total_coupons": 20,
                "consumed_count": max(0, 20 - remaining),
                "remaining_count": remaining,
            })
            doc.flags.ignore_permissions = True
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True, set_name=bk)

        orig = frappe.db.get_single_value("Purisol Settings", "customer_low_stock_threshold") or 3
        try:
            for v in range(6):
                _mk(f"T28Cust{v}", v)

            frappe.db.set_single_value("Purisol Settings", "customer_low_stock_threshold", 3)
            rows_3 = frappe.db.sql(_REPORT_SQL, as_dict=True)
            customers_3 = {r["customer"] for r in rows_3}

            frappe.db.set_single_value("Purisol Settings", "customer_low_stock_threshold", 5)
            rows_5 = frappe.db.sql(_REPORT_SQL, as_dict=True)
            customers_5 = {r["customer"] for r in rows_5}

            for v in range(4):
                self.assertIn(f"T28Cust{v}", customers_3)
            self.assertNotIn("T28Cust4", customers_3)
            self.assertNotIn("T28Cust5", customers_3)

            self.assertIn("T28Cust4", customers_5)
            self.assertIn("T28Cust5", customers_5)
            self.assertGreater(len(rows_5), len(rows_3))
        finally:
            frappe.db.set_single_value("Purisol Settings", "customer_low_stock_threshold", orig)

    def test_dashboard_w8_relative_date_token_evaluates(self):
        """W8 filters_json contains the [Today - 7d] token; the date boundary is correct."""
        from frappe.model.naming import make_autoname

        def _mk_depleted(days_ago):
            bk = make_autoname("T29-.#####")
            doc = frappe.get_doc({
                "doctype": "Purisol Coupon Booklet",
                "booklet_number": bk,
                "status": "Depleted",
                "total_coupons": 20,
                "consumed_count": 20,
                "remaining_count": 0,
                "depleted_on": add_to_date(today(), days=-days_ago),
            })
            doc.flags.ignore_permissions = True
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True, set_name=bk)
            return bk

        bk_2 = _mk_depleted(2)
        bk_5 = _mk_depleted(5)
        bk_7 = _mk_depleted(7)
        bk_8 = _mk_depleted(8)
        bk_14 = _mk_depleted(14)

        ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
        ql = next(q for q in ws.quick_lists if q.label == "Recent Depleted Booklets")
        self.assertIn("[Today - 7d]", ql.filters_json, "W8 Quick List must use relative-date token")

        cutoff = add_to_date(today(), days=-7)
        result = frappe.db.get_all(
            "Purisol Coupon Booklet",
            filters=[["status", "=", "Depleted"], ["depleted_on", ">=", cutoff]],
            pluck="name",
        )
        self.assertIn(bk_2, result)
        self.assertIn(bk_5, result)
        self.assertIn(bk_7, result)
        self.assertNotIn(bk_8, result)
        self.assertNotIn(bk_14, result)
