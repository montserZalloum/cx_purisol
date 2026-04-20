"""End-to-end Phase-6 notification flow tests (one per user story + edge cases).

US1 — New Discrepancy Opened (wired in Phase 3 of the Phase-6 rollout).
US2 — Customer Low Stock.
US3 — Warehouse Low Stock.
US4 — Booklet Depleted.
"""
from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.tests.fixtures import (
    configure_purisol_settings,
    count_notifications,
    ensure_coupon_item,
    ensure_customer,
    ensure_item_price,
    ensure_price_list,
    make_booklet_in_stock,
    make_booklet_with_consumed_coupons,
    make_employee,
    reset_warehouse_dedup,
    seed_administrator_user,
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


def _page_map(booklet_name):
    rows = frappe.get_all(
        "Purisol Coupon",
        filters={"booklet": booklet_name},
        fields=["name", "page_number"],
        order_by="page_number asc",
    )
    return {r["page_number"]: r["name"] for r in rows}


def _submit_entry(delivery_man, coupon_names):
    doc = frappe.get_doc({
        "doctype": "Purisol Coupon Consumption Entry",
        "posting_date": frappe.utils.today(),
        "posting_time": frappe.utils.nowtime(),
        "delivery_man": delivery_man,
        "coupons": [{"coupon": c} for c in coupon_names],
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc


class TestStory1DiscrepancyNotification(FrappeTestCase):
    """US1 end-to-end: Consumption Entry submit → Phase-5 detection → admin alert."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.admin = seed_administrator_user("p6-us1-flow-admin@example.com")
        self.customer_name = "P6-US1-Customer"
        ensure_customer(self.customer_name)
        self.emp = make_employee("P6US1", "Emp")

    def test_story1_discrepancy_notification(self):
        # Seed a Sold booklet with pages 1,2 already consumed.
        booklet_name, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1, 2)
        )
        pm = _page_map(booklet_name)

        before = count_notifications(
            for_user=self.admin, doctype="Purisol Coupon Discrepancy"
        )

        # Consume pages 7,8 → creates a Missing Coupons discrepancy for the gap 3-6.
        _submit_entry(self.emp.name, [pm[7], pm[8]])

        # One new discrepancy, one notification for the admin user referencing it.
        new_disc = frappe.get_all(
            "Purisol Coupon Discrepancy",
            filters={"booklet": booklet_name, "status": "Open"},
            fields=["name", "discrepancy_type"],
            order_by="creation desc",
            limit=1,
        )
        self.assertEqual(len(new_disc), 1)
        self.assertEqual(new_disc[0]["discrepancy_type"], "Missing Coupons")

        after = count_notifications(
            for_user=self.admin,
            doctype="Purisol Coupon Discrepancy",
            document_name=new_disc[0]["name"],
        )
        self.assertEqual(after, 1)

        total = count_notifications(
            for_user=self.admin, doctype="Purisol Coupon Discrepancy"
        )
        self.assertEqual(total, before + 1)

        # Body should reference booklet + delivery man.
        log = frappe.get_all(
            "Notification Log",
            filters={
                "for_user": self.admin,
                "document_type": "Purisol Coupon Discrepancy",
                "document_name": new_disc[0]["name"],
            },
            fields=["subject", "email_content"],
            limit=1,
        )[0]
        self.assertIn(new_disc[0]["name"], log["subject"])
        self.assertIn(booklet_name, log["email_content"])
        self.assertIn(self.emp.name, log["email_content"])


# ---------------------------------------------------------------------------
# US2 — Customer Low Stock
# ---------------------------------------------------------------------------


class TestStory2CustomerLowStock(FrappeTestCase):
    """US2 end-to-end: Consumption Entry drops customer's total-remaining ≤ threshold → admin alert."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.admin = seed_administrator_user("p6-us2-flow-admin@example.com")
        self.customer_name = "P6-US2-Customer"
        ensure_customer(self.customer_name)
        self.emp = make_employee("P6US2", "Emp")
        settings = frappe.get_single("Purisol Settings")
        self._orig_threshold = settings.customer_low_stock_threshold
        settings.customer_low_stock_threshold = 3
        settings.save(ignore_permissions=True)

    def tearDown(self):
        settings = frappe.get_single("Purisol Settings")
        settings.customer_low_stock_threshold = self._orig_threshold
        settings.save(ignore_permissions=True)

    def test_story2_customer_low_stock(self):
        # Threshold = 3.  Seed a Sold booklet with 16 consumed → remaining 4 > 3, no fire at setup.
        booklet, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=tuple(range(1, 17))
        )
        pm = _page_map(booklet)

        before = count_notifications(
            for_user=self.admin,
            doctype="Customer",
            document_name=self.customer_name,
        )

        # Consume page 17 → remaining 3 ≤ 3 → fires once per admin.
        _submit_entry(self.emp.name, [pm[17]])

        after = count_notifications(
            for_user=self.admin,
            doctype="Customer",
            document_name=self.customer_name,
        )
        self.assertEqual(after, before + 1)

        # Body should mention the customer name and count 3.
        log = frappe.get_all(
            "Notification Log",
            filters={
                "for_user": self.admin,
                "document_type": "Customer",
                "document_name": self.customer_name,
            },
            fields=["subject", "email_content"],
            order_by="creation desc",
            limit=1,
        )[0]
        self.assertIn(self.customer_name, log["subject"])
        self.assertIn(self.customer_name, log["email_content"])
        self.assertIn("3", log["email_content"])

    def test_story2_unassigned_booklet_skips_customer_check(self):
        # An In Stock booklet has customer = None — must not produce a Customer Low Stock notification.
        booklet = make_booklet_in_stock()
        pm = _page_map(booklet.name)

        before = count_notifications(for_user=self.admin, doctype="Customer")
        _submit_entry(self.emp.name, [pm[1]])
        after = count_notifications(for_user=self.admin, doctype="Customer")

        self.assertEqual(after, before)

    def test_story2_threshold_live_edit(self):
        # Start threshold = 2.  Setup remaining = 4 (no fire since 4 > 2).
        settings = frappe.get_single("Purisol Settings")
        settings.customer_low_stock_threshold = 2
        settings.save(ignore_permissions=True)

        booklet, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=tuple(range(1, 17))
        )
        pm = _page_map(booklet)

        # Admin raises threshold to 5 live.
        settings = frappe.get_single("Purisol Settings")
        settings.customer_low_stock_threshold = 5
        settings.save(ignore_permissions=True)

        before = count_notifications(
            for_user=self.admin,
            doctype="Customer",
            document_name=self.customer_name,
        )
        # Consume page 17 → remaining 3.  With old threshold (2) this would NOT fire;
        # with new threshold (5) it fires — proves live read.
        _submit_entry(self.emp.name, [pm[17]])
        after = count_notifications(
            for_user=self.admin,
            doctype="Customer",
            document_name=self.customer_name,
        )
        self.assertEqual(after, before + 1)


# ---------------------------------------------------------------------------
# US3 — Warehouse Low Stock
# ---------------------------------------------------------------------------


class TestStory3WarehouseLowStock(FrappeTestCase):
    """US3 end-to-end: Sales Invoice drops In Stock count < threshold → admin alert (daily dedup)."""

    def setUp(self):
        frappe.set_user("Administrator")
        frappe.local.role_permissions = {}
        frappe.local.user_roles = None
        frappe.utils.get_roles = lambda user=None: [
            "Purisol Administrator",
            "Administrator",
            "System Manager",
            "All",
        ]

        self.admin = seed_administrator_user("p6-us3-flow-admin@example.com")
        self.customer_name = "P6-US3-Customer"
        ensure_customer(self.customer_name)

        item = ensure_coupon_item()
        self.pl = ensure_price_list("Test-WH-PL")
        ensure_item_price(item.name, self.pl.name, 100)
        configure_purisol_settings(coupon_item=item.name, default_price_list=self.pl.name)

        self.booklets = [make_booklet_in_stock() for _ in range(6)]
        self.base_count = frappe.db.count(
            "Purisol Coupon Booklet", {"status": "In Stock"}
        )

        settings = frappe.get_single("Purisol Settings")
        self._orig_threshold = settings.warehouse_low_stock_threshold
        settings.warehouse_low_stock_threshold = self.base_count
        settings.save(ignore_permissions=True)
        reset_warehouse_dedup()

    def tearDown(self):
        settings = frappe.get_single("Purisol Settings")
        settings.warehouse_low_stock_threshold = self._orig_threshold
        settings.save(ignore_permissions=True)
        reset_warehouse_dedup()

    def _sell(self, booklet_name):
        from cx_purisol.cx_purisol.api.sell_booklets import (
            purisol_create_sales_invoice_for_booklets,
        )

        result = purisol_create_sales_invoice_for_booklets(
            self.customer_name, [booklet_name]
        )
        inv = frappe.get_doc("Sales Invoice", result["name"])
        inv.submit()
        return inv

    def test_story3_warehouse_low_stock_first_fire(self):
        before = count_notifications(
            for_user=self.admin, doctype="Purisol Coupon Booklet"
        )
        self._sell(self.booklets[0].name)
        # After: count = base_count - 1 < base_count = threshold → fires.
        after = count_notifications(
            for_user=self.admin, doctype="Purisol Coupon Booklet"
        )
        self.assertEqual(after, before + 1)
        marker = frappe.db.get_single_value(
            "Purisol Settings", "last_warehouse_low_stock_notified_on"
        )
        self.assertIsNotNone(marker)
        self.assertEqual(frappe.utils.getdate(marker), frappe.utils.getdate())

    def test_story3_warehouse_low_stock_dedup_same_day(self):
        self._sell(self.booklets[0].name)
        before = count_notifications(
            for_user=self.admin, doctype="Purisol Coupon Booklet"
        )
        # Three more same-day qualifying sales — all dedup'd.
        for i in range(1, 4):
            self._sell(self.booklets[i].name)
        after = count_notifications(
            for_user=self.admin, doctype="Purisol Coupon Booklet"
        )
        self.assertEqual(after, before)

    def test_story3_warehouse_low_stock_resets_next_day(self):
        self._sell(self.booklets[0].name)  # first fire
        # Simulate day boundary by backdating the dedup marker to yesterday.
        yesterday = frappe.utils.add_days(frappe.utils.today(), -1)
        frappe.db.set_single_value(
            "Purisol Settings", "last_warehouse_low_stock_notified_on", yesterday
        )
        before = count_notifications(
            for_user=self.admin, doctype="Purisol Coupon Booklet"
        )
        self._sell(self.booklets[1].name)
        after = count_notifications(
            for_user=self.admin, doctype="Purisol Coupon Booklet"
        )
        self.assertEqual(after, before + 1)

    def test_story3_warehouse_low_stock_strict_inequality(self):
        # Drop threshold by one so the post-sale count equals threshold — no fire.
        settings = frappe.get_single("Purisol Settings")
        settings.warehouse_low_stock_threshold = self.base_count - 1
        settings.save(ignore_permissions=True)

        before = count_notifications(
            for_user=self.admin, doctype="Purisol Coupon Booklet"
        )
        self._sell(self.booklets[0].name)
        after = count_notifications(
            for_user=self.admin, doctype="Purisol Coupon Booklet"
        )
        self.assertEqual(after, before)

    def test_story3_warehouse_unchanged_invoice_still_evaluates(self):
        # Threshold above current count so any submit qualifies on dedup-clear day.
        settings = frappe.get_single("Purisol Settings")
        settings.warehouse_low_stock_threshold = self.base_count + 1
        settings.save(ignore_permissions=True)

        item_code = ensure_coupon_item().name
        inv = frappe.new_doc("Sales Invoice")
        inv.customer = self.customer_name
        inv.selling_price_list = self.pl.name
        inv.append("items", {"item_code": item_code, "qty": 1, "rate": 100})
        inv.set_missing_values()
        inv.calculate_taxes_and_totals()
        inv.insert(ignore_permissions=True)

        before = count_notifications(
            for_user=self.admin, doctype="Purisol Coupon Booklet"
        )
        inv.submit()
        after = count_notifications(
            for_user=self.admin, doctype="Purisol Coupon Booklet"
        )
        self.assertEqual(after, before + 1)


# ---------------------------------------------------------------------------
# US4 — Booklet Depleted
# ---------------------------------------------------------------------------


class TestStory4BookletDepleted(FrappeTestCase):
    """US4 end-to-end: consuming a booklet's 20th coupon fires one Depleted alert per admin per booklet."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.admin = seed_administrator_user("p6-us4-flow-admin@example.com")
        self.customer_name = "P6-US4-Customer"
        ensure_customer(self.customer_name)
        self.emp = make_employee("P6US4", "Emp")

    def test_story4_booklet_depleted_notification(self):
        booklet, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=tuple(range(1, 20))
        )
        pm = _page_map(booklet)

        before = count_notifications(
            for_user=self.admin,
            doctype="Purisol Coupon Booklet",
            document_name=booklet,
        )
        _submit_entry(self.emp.name, [pm[20]])
        after = count_notifications(
            for_user=self.admin,
            doctype="Purisol Coupon Booklet",
            document_name=booklet,
        )
        self.assertEqual(after, before + 1)

        # Booklet actually depleted (Phase-4 behaviour preserved).
        self.assertEqual(
            frappe.db.get_value("Purisol Coupon Booklet", booklet, "status"),
            "Depleted",
        )

        log = frappe.get_all(
            "Notification Log",
            filters={
                "for_user": self.admin,
                "document_type": "Purisol Coupon Booklet",
                "document_name": booklet,
            },
            fields=["subject", "email_content"],
            order_by="creation desc",
            limit=1,
        )[0]
        self.assertIn(booklet, log["subject"])
        self.assertIn(booklet, log["email_content"])
        self.assertIn(self.customer_name, log["email_content"])

    def test_story4_multi_booklet_depletion_fires_per_booklet(self):
        booklet1, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=tuple(range(1, 20))
        )
        booklet2, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=tuple(range(1, 20))
        )
        pm1 = _page_map(booklet1)
        pm2 = _page_map(booklet2)

        before1 = count_notifications(
            for_user=self.admin,
            doctype="Purisol Coupon Booklet",
            document_name=booklet1,
        )
        before2 = count_notifications(
            for_user=self.admin,
            doctype="Purisol Coupon Booklet",
            document_name=booklet2,
        )
        _submit_entry(self.emp.name, [pm1[20], pm2[20]])
        after1 = count_notifications(
            for_user=self.admin,
            doctype="Purisol Coupon Booklet",
            document_name=booklet1,
        )
        after2 = count_notifications(
            for_user=self.admin,
            doctype="Purisol Coupon Booklet",
            document_name=booklet2,
        )
        self.assertEqual(after1, before1 + 1)
        self.assertEqual(after2, before2 + 1)

    def test_story4_non_depleting_consumption_no_notification(self):
        booklet, _ = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1,)
        )
        pm = _page_map(booklet)

        before = count_notifications(
            for_user=self.admin,
            doctype="Purisol Coupon Booklet",
            document_name=booklet,
        )
        _submit_entry(self.emp.name, [pm[2]])  # 2 of 20 consumed — not depleting
        after = count_notifications(
            for_user=self.admin,
            doctype="Purisol Coupon Booklet",
            document_name=booklet,
        )
        self.assertEqual(after, before)


# ---------------------------------------------------------------------------
# Polish — cross-cutting atomicity + empty-recipient coverage
# ---------------------------------------------------------------------------


class TestNotificationAtomicity(FrappeTestCase):
    """SC-008: a raise inside notify.send rolls back the whole triggering submit."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_atomicity_rolls_back_notifications_with_submit(self):
        seed_administrator_user("p6-atomic-admin@example.com")
        customer_name = "P6-Atomic-Customer"
        ensure_customer(customer_name)
        emp = make_employee("P6Atomic", "Emp")
        booklet, _ = make_booklet_with_consumed_coupons(
            customer_name, emp, consumed_pages=tuple(range(1, 20))
        )
        pm = _page_map(booklet)

        before = count_notifications(
            doctype="Purisol Coupon Booklet", document_name=booklet
        )
        status_before = frappe.db.get_value(
            "Purisol Coupon Booklet", booklet, "status"
        )

        frappe.db.savepoint("p6_flow_atomic_sp")

        raised = False
        try:
            with patch(
                "cx_purisol.cx_purisol.api.notify._emit_bell",
                side_effect=RuntimeError("simulated notification failure"),
            ):
                try:
                    _submit_entry(emp.name, [pm[20]])
                except RuntimeError:
                    raised = True
        finally:
            frappe.db.rollback(save_point="p6_flow_atomic_sp")

        self.assertTrue(raised)
        self.assertEqual(
            count_notifications(
                doctype="Purisol Coupon Booklet", document_name=booklet
            ),
            before,
        )
        self.assertEqual(
            frappe.db.get_value("Purisol Coupon Booklet", booklet, "status"),
            status_before,
        )


class TestNoAdminAllSilent(FrappeTestCase):
    """SC-007 / FR-014: with zero enabled admins, every trigger succeeds silently."""

    def setUp(self):
        frappe.set_user("Administrator")
        frappe.local.role_permissions = {}
        frappe.local.user_roles = None
        frappe.utils.get_roles = lambda user=None: [
            "Purisol Administrator",
            "Administrator",
            "System Manager",
            "All",
        ]

    def test_no_admin_triggers_all_silent_no_op(self):
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

        try:
            customer_name = "P6-NoAdmin-Customer"
            ensure_customer(customer_name)
            emp = make_employee("P6NoAdmin", "Emp")

            settings = frappe.get_single("Purisol Settings")
            orig_wh = settings.warehouse_low_stock_threshold
            orig_cust = settings.customer_low_stock_threshold

            in_stock = frappe.db.count(
                "Purisol Coupon Booklet", {"status": "In Stock"}
            )
            settings.warehouse_low_stock_threshold = in_stock + 10
            settings.customer_low_stock_threshold = 100
            settings.save(ignore_permissions=True)
            reset_warehouse_dedup()

            try:
                before_disc = frappe.db.count(
                    "Notification Log",
                    {"document_type": "Purisol Coupon Discrepancy"},
                )
                before_cust = frappe.db.count(
                    "Notification Log", {"document_type": "Customer"}
                )
                before_book = frappe.db.count(
                    "Notification Log", {"document_type": "Purisol Coupon Booklet"}
                )

                # Depletion + customer low stock (one consumption submit).
                booklet, _ = make_booklet_with_consumed_coupons(
                    customer_name, emp, consumed_pages=tuple(range(1, 20))
                )
                pm = _page_map(booklet)
                entry = _submit_entry(emp.name, [pm[20]])
                self.assertTrue(
                    frappe.db.exists(
                        "Purisol Coupon Consumption Entry", entry.name
                    )
                )

                # Warehouse low stock (one Sales Invoice submit).
                new_booklet = make_booklet_in_stock()
                item = ensure_coupon_item()
                pl = ensure_price_list("Test-NoAdmin-PL")
                ensure_item_price(item.name, pl.name, 100)
                configure_purisol_settings(
                    coupon_item=item.name, default_price_list=pl.name
                )
                from cx_purisol.cx_purisol.api.sell_booklets import (
                    purisol_create_sales_invoice_for_booklets,
                )

                result = purisol_create_sales_invoice_for_booklets(
                    customer_name, [new_booklet.name]
                )
                inv = frappe.get_doc("Sales Invoice", result["name"])
                inv.submit()
                self.assertEqual(inv.docstatus, 1)

                # Discrepancy (consumption with a gap).
                booklet2, _ = make_booklet_with_consumed_coupons(
                    customer_name, emp, consumed_pages=(1, 2)
                )
                pm2 = _page_map(booklet2)
                _submit_entry(emp.name, [pm2[7]])
                discs = frappe.get_all(
                    "Purisol Coupon Discrepancy",
                    filters={"booklet": booklet2, "status": "Open"},
                )
                self.assertGreater(len(discs), 0)

                self.assertEqual(
                    frappe.db.count(
                        "Notification Log",
                        {"document_type": "Purisol Coupon Discrepancy"},
                    ),
                    before_disc,
                )
                self.assertEqual(
                    frappe.db.count(
                        "Notification Log", {"document_type": "Customer"}
                    ),
                    before_cust,
                )
                self.assertEqual(
                    frappe.db.count(
                        "Notification Log",
                        {"document_type": "Purisol Coupon Booklet"},
                    ),
                    before_book,
                )
            finally:
                settings = frappe.get_single("Purisol Settings")
                settings.warehouse_low_stock_threshold = orig_wh
                settings.customer_low_stock_threshold = orig_cust
                settings.save(ignore_permissions=True)
        finally:
            for u in enabled_users:
                frappe.db.set_value("User", u, "enabled", 1)
