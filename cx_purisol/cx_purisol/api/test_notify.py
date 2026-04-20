"""Unit tests for the Purisol Notify utility — Phase 6 (contracts/notify.md §1)."""
from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.api import notify
from cx_purisol.cx_purisol.tests.fixtures import (
    count_notifications,
    seed_administrator_user,
)


class TestNotifyUtility(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_send_role_expands_to_all_enabled_users(self):
        u1 = seed_administrator_user("p6-notify-a@example.com")
        u2 = seed_administrator_user("p6-notify-b@example.com")

        before_a = count_notifications(for_user=u1, subject_contains="NOTIFY-ROLE-OK")
        before_b = count_notifications(for_user=u2, subject_contains="NOTIFY-ROLE-OK")

        created = notify.send(
            recipient="Purisol Administrator",
            subject="NOTIFY-ROLE-OK subject",
            message="body",
            reference_doctype="Purisol Settings",
            reference_name="Purisol Settings",
        )

        self.assertGreaterEqual(len(created), 2)
        self.assertEqual(
            count_notifications(for_user=u1, subject_contains="NOTIFY-ROLE-OK"),
            before_a + 1,
        )
        self.assertEqual(
            count_notifications(for_user=u2, subject_contains="NOTIFY-ROLE-OK"),
            before_b + 1,
        )

    def test_send_role_excludes_disabled_users(self):
        enabled = seed_administrator_user("p6-notify-enabled@example.com")
        disabled = seed_administrator_user("p6-notify-disabled@example.com")
        frappe.db.set_value("User", disabled, "enabled", 0)

        try:
            before = count_notifications(
                for_user=disabled, subject_contains="NOTIFY-DISABLED"
            )
            before_enabled = count_notifications(
                for_user=enabled, subject_contains="NOTIFY-DISABLED"
            )

            notify.send(
                recipient="Purisol Administrator",
                subject="NOTIFY-DISABLED subject",
                message="body",
            )

            self.assertEqual(
                count_notifications(
                    for_user=disabled, subject_contains="NOTIFY-DISABLED"
                ),
                before,
            )
            self.assertEqual(
                count_notifications(
                    for_user=enabled, subject_contains="NOTIFY-DISABLED"
                ),
                before_enabled + 1,
            )
        finally:
            frappe.db.set_value("User", disabled, "enabled", 1)

    def test_send_unknown_role_is_silent_no_op(self):
        before = count_notifications(subject_contains="NOTIFY-UNKNOWN-ROLE")

        created = notify.send(
            recipient="Nonexistent Role XYZ",
            subject="NOTIFY-UNKNOWN-ROLE subject",
            message="body",
        )

        self.assertEqual(created, [])
        self.assertEqual(
            count_notifications(subject_contains="NOTIFY-UNKNOWN-ROLE"),
            before,
        )

    def test_send_user_recipient_direct(self):
        target = seed_administrator_user("p6-notify-user-direct@example.com")

        before = count_notifications(
            for_user=target, subject_contains="NOTIFY-USER-DIRECT"
        )

        created = notify.send(
            recipient=target,
            subject="NOTIFY-USER-DIRECT subject",
            message="body",
        )

        self.assertEqual(len(created), 1)
        self.assertEqual(
            count_notifications(
                for_user=target, subject_contains="NOTIFY-USER-DIRECT"
            ),
            before + 1,
        )

    def test_send_rolls_back_on_insert_failure(self):
        seed_administrator_user("p6-notify-atomic@example.com")

        before = count_notifications(subject_contains="NOTIFY-ATOMIC")

        frappe.db.savepoint("p6_notify_atomic_sp")

        original_insert = frappe.model.document.Document.insert

        def _raising_insert(self, *args, **kwargs):
            if self.doctype == "Notification Log":
                raise RuntimeError("simulated failure during Notification Log insert")
            return original_insert(self, *args, **kwargs)

        raised = False
        try:
            with patch.object(
                frappe.model.document.Document, "insert", _raising_insert
            ):
                try:
                    notify.send(
                        recipient="Purisol Administrator",
                        subject="NOTIFY-ATOMIC subject",
                        message="body",
                    )
                except RuntimeError:
                    raised = True
        finally:
            frappe.db.rollback(save_point="p6_notify_atomic_sp")

        self.assertTrue(raised)
        self.assertEqual(
            count_notifications(subject_contains="NOTIFY-ATOMIC"),
            before,
        )
