import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.tests.fixtures import (
    make_booklet_in_stock,
    make_employee,
    submit_assign,
    submit_return,
    submit_transfer,
)


def _as_admin():
    frappe.set_user("Administrator")
    frappe.utils.get_roles = lambda user=None: [
        "Purisol Administrator",
        "Administrator",
        "System Manager",
        "All",
    ]


class TestAssignFlow(FrappeTestCase):
    def setUp(self):
        _as_admin()

    def test_assign_end_to_end(self):
        emp = make_employee(first_name="AssignTarget")
        booklets = [make_booklet_in_stock().name for _ in range(3)]
        entry = submit_assign(booklets, to_delivery_man=emp.name)
        self.assertEqual(entry.docstatus, 1)
        for name in booklets:
            b = frappe.get_doc("Purisol Coupon Booklet", name)
            self.assertEqual(b.status, "In Custody")
            self.assertEqual(b.current_delivery_man, emp.name)
        entry.reload()
        for row in entry.booklets:
            self.assertEqual(row.booklet_status_at_entry, "In Stock")
            self.assertIsNone(row.delivery_man_at_entry)

    def test_cancel_reverses_assign(self):
        emp = make_employee(first_name="CancelTarget")
        booklet_name = make_booklet_in_stock().name
        entry = submit_assign([booklet_name], to_delivery_man=emp.name)

        b = frappe.get_doc("Purisol Coupon Booklet", booklet_name)
        self.assertEqual(b.status, "In Custody")
        self.assertEqual(b.current_delivery_man, emp.name)

        entry.cancel()
        b.reload()
        self.assertEqual(b.status, "In Stock")
        self.assertIsNone(b.current_delivery_man)


class TestReturnFlow(FrappeTestCase):
    def setUp(self):
        _as_admin()

    def test_return_end_to_end(self):
        emp = make_employee(first_name="ReturnTarget")
        booklet_a = make_booklet_in_stock().name
        booklet_b = make_booklet_in_stock().name
        submit_assign([booklet_a, booklet_b], to_delivery_man=emp.name)

        entry = submit_return([booklet_a], from_delivery_man=emp.name)
        self.assertEqual(entry.docstatus, 1)

        b_a = frappe.get_doc("Purisol Coupon Booklet", booklet_a)
        self.assertEqual(b_a.status, "In Stock")
        self.assertIsNone(b_a.current_delivery_man)

        b_b = frappe.get_doc("Purisol Coupon Booklet", booklet_b)
        self.assertEqual(b_b.status, "In Custody")
        self.assertEqual(b_b.current_delivery_man, emp.name)

        entry.reload()
        row = entry.booklets[0]
        self.assertEqual(row.booklet_status_at_entry, "In Custody")
        self.assertEqual(row.delivery_man_at_entry, emp.name)

    def test_cancel_reverses_return(self):
        emp = make_employee(first_name="CancelReturn")
        booklet_name = make_booklet_in_stock().name
        submit_assign([booklet_name], to_delivery_man=emp.name)
        entry = submit_return([booklet_name], from_delivery_man=emp.name)

        b = frappe.get_doc("Purisol Coupon Booklet", booklet_name)
        self.assertEqual(b.status, "In Stock")
        self.assertIsNone(b.current_delivery_man)

        entry.cancel()
        b.reload()
        self.assertEqual(b.status, "In Custody")
        self.assertEqual(b.current_delivery_man, emp.name)


class TestTransferFlow(FrappeTestCase):
    def setUp(self):
        _as_admin()

    def test_partial_transfer(self):
        ali = make_employee(first_name="Ali")
        sami = make_employee(first_name="Sami")
        ali_b1 = make_booklet_in_stock().name
        ali_b2 = make_booklet_in_stock().name
        sami_b1 = make_booklet_in_stock().name
        sami_b2 = make_booklet_in_stock().name
        submit_assign([ali_b1, ali_b2], to_delivery_man=ali.name)
        submit_assign([sami_b1, sami_b2], to_delivery_man=sami.name)

        entry = submit_transfer([ali_b1], from_delivery_man=ali.name, to_delivery_man=sami.name)
        self.assertEqual(entry.docstatus, 1)

        b = frappe.get_doc("Purisol Coupon Booklet", ali_b1)
        self.assertEqual(b.status, "In Custody")
        self.assertEqual(b.current_delivery_man, sami.name)

        b2 = frappe.get_doc("Purisol Coupon Booklet", ali_b2)
        self.assertEqual(b2.status, "In Custody")
        self.assertEqual(b2.current_delivery_man, ali.name)

        for name in [sami_b1, sami_b2]:
            bk = frappe.get_doc("Purisol Coupon Booklet", name)
            self.assertEqual(bk.status, "In Custody")
            self.assertEqual(bk.current_delivery_man, sami.name)

        sami_custody = frappe.get_all(
            "Purisol Coupon Booklet",
            filters={"current_delivery_man": sami.name, "status": "In Custody"},
        )
        self.assertEqual(len(sami_custody), 3)

        transfer_entries = frappe.get_all(
            "Purisol Custody Entry",
            filters={"entry_type": "Transfer", "from_delivery_man": ali.name, "to_delivery_man": sami.name, "docstatus": 1},
        )
        self.assertEqual(len(transfer_entries), 1)

    def test_atomic_rollback_on_invalid_booklet(self):
        emp_a = make_employee(first_name="AtomicA")
        emp_b = make_employee(first_name="AtomicB")
        emp_c = make_employee(first_name="AtomicC")
        b1 = make_booklet_in_stock().name
        b2 = make_booklet_in_stock().name
        b3 = make_booklet_in_stock().name
        submit_assign([b1, b2], to_delivery_man=emp_a.name)
        submit_assign([b3], to_delivery_man=emp_c.name)

        with self.assertRaises(frappe.ValidationError):
            submit_transfer([b1, b2, b3], from_delivery_man=emp_a.name, to_delivery_man=emp_b.name)

        for name in [b1, b2]:
            bk = frappe.get_doc("Purisol Coupon Booklet", name)
            self.assertEqual(bk.status, "In Custody")
            self.assertEqual(bk.current_delivery_man, emp_a.name)

        bk3 = frappe.get_doc("Purisol Coupon Booklet", b3)
        self.assertEqual(bk3.current_delivery_man, emp_c.name)

    def test_cancel_reverses_transfer(self):
        emp_a = make_employee(first_name="TrCancelA")
        emp_b = make_employee(first_name="TrCancelB")
        booklet_name = make_booklet_in_stock().name
        submit_assign([booklet_name], to_delivery_man=emp_a.name)
        entry = submit_transfer([booklet_name], from_delivery_man=emp_a.name, to_delivery_man=emp_b.name)

        bk = frappe.get_doc("Purisol Coupon Booklet", booklet_name)
        self.assertEqual(bk.status, "In Custody")
        self.assertEqual(bk.current_delivery_man, emp_b.name)

        entry.cancel()
        bk.reload()
        self.assertEqual(bk.status, "In Custody")
        self.assertEqual(bk.current_delivery_man, emp_a.name)

    def test_cancel_rejected_if_booklet_subsequently_moved(self):
        emp_a = make_employee(first_name="SubMovedA")
        emp_b = make_employee(first_name="SubMovedB")
        booklet_name = make_booklet_in_stock().name
        assign_entry = submit_assign([booklet_name], to_delivery_man=emp_a.name)
        submit_transfer([booklet_name], from_delivery_man=emp_a.name, to_delivery_man=emp_b.name)

        with self.assertRaises(frappe.ValidationError):
            assign_entry.cancel()

    def test_custody_history_reconstructible(self):
        emp_a = make_employee(first_name="HistoryA")
        emp_b = make_employee(first_name="HistoryB")
        booklet_name = make_booklet_in_stock().name

        assign_entry = submit_assign([booklet_name], to_delivery_man=emp_a.name)
        transfer_entry = submit_transfer([booklet_name], from_delivery_man=emp_a.name, to_delivery_man=emp_b.name)
        return_entry = submit_return([booklet_name], from_delivery_man=emp_b.name)

        child_rows = frappe.get_all(
            "Purisol Custody Entry Booklet",
            filters={"booklet": booklet_name},
            fields=["parent", "parenttype"],
            order_by="creation asc",
        )
        parents = [row["parent"] for row in child_rows]
        self.assertEqual(len(parents), 3)
        self.assertIn(assign_entry.name, parents)
        self.assertIn(transfer_entry.name, parents)
        self.assertIn(return_entry.name, parents)
        self.assertEqual(parents[0], assign_entry.name)
        self.assertEqual(parents[1], transfer_entry.name)
        self.assertEqual(parents[2], return_entry.name)
