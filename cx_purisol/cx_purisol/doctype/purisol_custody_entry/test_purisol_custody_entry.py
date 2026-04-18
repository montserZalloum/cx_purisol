import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.tests.fixtures import (
    make_booklet_in_stock,
    make_custody_entry,
    make_employee,
    submit_assign,
    submit_return,
    submit_transfer,
)

test_ignore = ["Customer", "Employee", "Sales Invoice", "Subscription", "Subscription Plan", "User"]


def _as_admin():
    frappe.set_user("Administrator")
    frappe.utils.get_roles = lambda user=None: [
        "Purisol Administrator",
        "Administrator",
        "System Manager",
        "All",
    ]


class TestAssignValidation(FrappeTestCase):
    def setUp(self):
        _as_admin()

    def test_assign_requires_to_delivery_man(self):
        booklet = make_booklet_in_stock()
        with self.assertRaises(frappe.ValidationError):
            make_custody_entry("Assign", [booklet.name])

    def test_assign_forbids_from_delivery_man(self):
        emp_from = make_employee(first_name="From")
        emp_to = make_employee(first_name="To")
        booklet = make_booklet_in_stock()
        with self.assertRaises(frappe.ValidationError):
            make_custody_entry(
                "Assign",
                [booklet.name],
                from_delivery_man=emp_from.name,
                to_delivery_man=emp_to.name,
            )

    def test_rejects_empty_child_table(self):
        emp = make_employee(first_name="Empty")
        doc = frappe.get_doc({
            "doctype": "Purisol Custody Entry",
            "entry_type": "Assign",
            "to_delivery_man": emp.name,
            "booklets": [],
        })
        self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

    def test_rejects_duplicate_booklet_in_entry(self):
        emp = make_employee(first_name="Dup")
        booklet = make_booklet_in_stock()
        doc = frappe.get_doc({
            "doctype": "Purisol Custody Entry",
            "entry_type": "Assign",
            "to_delivery_man": emp.name,
            "booklets": [
                {"booklet": booklet.name},
                {"booklet": booklet.name},
            ],
        })
        self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

    def test_assign_rejects_booklet_not_in_stock(self):
        emp_a = make_employee(first_name="Alpha")
        emp_b = make_employee(first_name="Beta")
        booklet = make_booklet_in_stock()
        submit_assign([booklet.name], to_delivery_man=emp_a.name)
        with self.assertRaises(frappe.ValidationError):
            make_custody_entry(
                "Assign", [booklet.name], to_delivery_man=emp_b.name
            )

    def test_snapshot_filled_before_submit(self):
        emp = make_employee(first_name="Snap")
        booklet = make_booklet_in_stock()
        entry = submit_assign([booklet.name], to_delivery_man=emp.name)
        entry.reload()
        row = entry.booklets[0]
        self.assertEqual(row.booklet_status_at_entry, "In Stock")
        self.assertIsNone(row.delivery_man_at_entry)


class TestReturnValidation(FrappeTestCase):
    def setUp(self):
        _as_admin()

    def test_return_requires_from_delivery_man(self):
        emp = make_employee(first_name="RetReq")
        booklet = make_booklet_in_stock()
        submit_assign([booklet.name], to_delivery_man=emp.name)
        with self.assertRaises(frappe.ValidationError):
            make_custody_entry("Return", [booklet.name])

    def test_return_forbids_to_delivery_man(self):
        emp_a = make_employee(first_name="RetForbA")
        emp_b = make_employee(first_name="RetForbB")
        booklet = make_booklet_in_stock()
        submit_assign([booklet.name], to_delivery_man=emp_a.name)
        with self.assertRaises(frappe.ValidationError):
            make_custody_entry(
                "Return",
                [booklet.name],
                from_delivery_man=emp_a.name,
                to_delivery_man=emp_b.name,
            )

    def test_return_rejects_booklet_not_in_custody(self):
        emp = make_employee(first_name="RetNotCust")
        booklet = make_booklet_in_stock()
        with self.assertRaises(frappe.ValidationError):
            make_custody_entry("Return", [booklet.name], from_delivery_man=emp.name)

    def test_return_rejects_booklet_held_by_other(self):
        emp_a = make_employee(first_name="RetHeldA")
        emp_b = make_employee(first_name="RetHeldB")
        booklet = make_booklet_in_stock()
        submit_assign([booklet.name], to_delivery_man=emp_a.name)
        with self.assertRaises(frappe.ValidationError):
            make_custody_entry("Return", [booklet.name], from_delivery_man=emp_b.name)


class TestTransferValidation(FrappeTestCase):
    def setUp(self):
        _as_admin()

    def test_transfer_requires_both(self):
        emp = make_employee(first_name="TrReqBoth")
        _emp_b = make_employee(first_name="TrReqBothB")
        booklet = make_booklet_in_stock()
        submit_assign([booklet.name], to_delivery_man=emp.name)
        with self.assertRaises(frappe.ValidationError):
            make_custody_entry("Transfer", [booklet.name], from_delivery_man=emp.name)

    def test_transfer_rejects_self(self):
        emp = make_employee(first_name="TrSelf")
        booklet = make_booklet_in_stock()
        submit_assign([booklet.name], to_delivery_man=emp.name)
        with self.assertRaises(frappe.ValidationError):
            make_custody_entry(
                "Transfer",
                [booklet.name],
                from_delivery_man=emp.name,
                to_delivery_man=emp.name,
            )

    def test_transfer_rejects_booklet_held_by_other(self):
        emp_a = make_employee(first_name="TrHeldA")
        emp_b = make_employee(first_name="TrHeldB")
        emp_c = make_employee(first_name="TrHeldC")
        booklet = make_booklet_in_stock()
        submit_assign([booklet.name], to_delivery_man=emp_a.name)
        with self.assertRaises(frappe.ValidationError):
            make_custody_entry(
                "Transfer",
                [booklet.name],
                from_delivery_man=emp_b.name,
                to_delivery_man=emp_c.name,
            )

    def test_transfer_rejects_booklet_not_in_custody(self):
        emp_a = make_employee(first_name="TrNotCustA")
        emp_b = make_employee(first_name="TrNotCustB")
        booklet = make_booklet_in_stock()
        with self.assertRaises(frappe.ValidationError):
            make_custody_entry(
                "Transfer",
                [booklet.name],
                from_delivery_man=emp_a.name,
                to_delivery_man=emp_b.name,
            )
