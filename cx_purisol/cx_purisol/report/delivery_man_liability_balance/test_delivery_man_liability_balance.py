import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from cx_purisol.cx_purisol.report.delivery_man_liability_balance.delivery_man_liability_balance import (
    execute,
)
from cx_purisol.cx_purisol.tests.fixtures import (
    configure_purisol_settings_accounts,
    make_employee,
)

test_ignore = [
    "Employee",
    "Journal Entry",
    "Payment Entry",
    "GL Entry",
]


def _make_liability_je(dm_name: str, account: str, amount: float, company: str) -> str:
    settings = frappe.get_single("Purisol Settings")
    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.posting_date = today()
    je.company = company
    je.user_remark = f"Seed liability JE {amount}"
    je.append("accounts", {
        "account": account,
        "party_type": "Employee",
        "party": dm_name,
        "debit_in_account_currency": amount,
        "credit_in_account_currency": 0,
    })
    je.append("accounts", {
        "account": settings.discrepancy_offset_account,
        "debit_in_account_currency": 0,
        "credit_in_account_currency": amount,
    })
    je.insert(ignore_permissions=True)
    je.submit()
    return je.name


def _make_payment_entry(dm_name: str, amount: float, company: str) -> str:
    settings = frappe.get_single("Purisol Settings")
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.posting_date = today()
    pe.company = company
    pe.paid_from = settings.discrepancy_offset_account
    pe.paid_to = settings.default_cash_account
    pe.paid_amount = amount
    pe.received_amount = amount
    pe.party_type = "Employee"
    pe.party = dm_name
    pe.insert(ignore_permissions=True)
    pe.submit()
    return pe.name


class TestDeliveryManLiabilityBalance(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        import erpnext
        self._company = frappe.defaults.get_global_default("company") or erpnext.get_default_company()

    def test_acceptance_scenario_2_liability_balance(self):
        """DM A: 2 JEs (200+150=350 owed) + 1 PE (100 paid) → open_balance=250 (US2 AS2)."""
        configure_purisol_settings_accounts()
        settings = frappe.get_single("Purisol Settings")
        account = settings.employee_liability_account

        dm_a = make_employee("LiabDmA")

        _make_liability_je(dm_a.name, account, 200.0, self._company)
        _make_liability_je(dm_a.name, account, 150.0, self._company)
        _make_payment_entry(dm_a.name, 100.0, self._company)

        _, data = execute({"delivery_man": dm_a.name})
        self.assertEqual(len(data), 1)

        row = data[0]
        self.assertAlmostEqual(row["total_owed"], 350.0, places=2)
        self.assertAlmostEqual(row["total_paid"], 100.0, places=2)
        self.assertAlmostEqual(row["open_balance"], 250.0, places=2)
        self.assertEqual(row["delivery_man"], dm_a.name)

    def test_unconfigured_account_returns_info_row(self):
        """When employee_liability_account is unset → single info row with null numerics."""
        settings = frappe.get_single("Purisol Settings")
        original = settings.employee_liability_account
        settings.employee_liability_account = ""
        settings.save(ignore_permissions=True)

        try:
            _, data = execute({})
            self.assertEqual(len(data), 1)
            row = data[0]
            self.assertIsNone(row["total_owed"])
            self.assertIsNone(row["total_paid"])
            self.assertIsNone(row["open_balance"])
            self.assertIn("Configure", row["delivery_man_name"])
        finally:
            settings.employee_liability_account = original
            settings.save(ignore_permissions=True)

    def test_no_rows_when_no_gl_entries(self):
        """A delivery man with no GL entries does not appear."""
        configure_purisol_settings_accounts()
        dm_ghost = make_employee("LiabGhostDm")

        _, data = execute({"delivery_man": dm_ghost.name})
        dm_names = [r["delivery_man"] for r in data]
        self.assertNotIn(dm_ghost.name, dm_names)
