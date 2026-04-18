import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, date_diff, now, nowdate

from cx_purisol.cx_purisol.tests.fixtures import (
    make_booklet_in_stock,
    make_employee,
    submit_assign,
    submit_transfer,
)

_REPORT_SQL = """
    SELECT
        b.current_delivery_man,
        b.name AS booklet,
        COALESCE(DATEDIFF(NOW(), MAX(e.entry_datetime)), 0) AS days_in_custody,
        b.customer,
        b.batch_id
    FROM `tabPurisol Coupon Booklet` b
    LEFT JOIN `tabPurisol Custody Entry Booklet` eb ON eb.booklet = b.name
    LEFT JOIN `tabPurisol Custody Entry` e ON e.name = eb.parent AND e.docstatus = 1
    WHERE b.status = 'In Custody'
    AND (%(delivery_man)s IS NULL OR b.current_delivery_man = %(delivery_man)s)
    AND (%(batch_id)s IS NULL OR b.batch_id = %(batch_id)s)
    GROUP BY b.name
    ORDER BY b.current_delivery_man, b.name
"""


def _run_report(delivery_man=None, batch_id=None):
    return frappe.db.sql(
        _REPORT_SQL, {"delivery_man": delivery_man, "batch_id": batch_id}, as_dict=True
    )


class TestCurrentCustodyReport(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_report_lists_only_in_custody(self):
        emp = make_employee(first_name="RptOnlyCust")
        in_stock = make_booklet_in_stock().name
        in_custody = make_booklet_in_stock().name
        submit_assign([in_custody], to_delivery_man=emp.name)

        data = _run_report()
        booklet_names = {row["booklet"] for row in data}

        self.assertIn(in_custody, booklet_names)
        self.assertNotIn(in_stock, booklet_names)

    def test_report_grouping_by_delivery_man(self):
        emp_a = make_employee(first_name="RptGroupA")
        emp_b = make_employee(first_name="RptGroupB")
        b1 = make_booklet_in_stock().name
        b2 = make_booklet_in_stock().name
        b3 = make_booklet_in_stock().name
        b4 = make_booklet_in_stock().name
        submit_assign([b1, b2], to_delivery_man=emp_a.name)
        submit_assign([b3, b4], to_delivery_man=emp_b.name)

        data = _run_report()

        emp_a_rows = [r for r in data if r["current_delivery_man"] == emp_a.name]
        emp_b_rows = [r for r in data if r["current_delivery_man"] == emp_b.name]

        self.assertEqual(len(emp_a_rows), 2)
        self.assertEqual(len(emp_b_rows), 2)

        emp_a_booklets = {r["booklet"] for r in emp_a_rows}
        self.assertEqual(emp_a_booklets, {b1, b2})

    def test_report_days_in_custody_matches_latest_entry(self):
        emp_a = make_employee(first_name="RptDaysA")
        emp_b = make_employee(first_name="RptDaysB")
        booklet_name = make_booklet_in_stock().name

        assign_dt = add_to_date(now(), days=-30)
        assign_entry = frappe.get_doc({
            "doctype": "Purisol Custody Entry",
            "entry_type": "Assign",
            "to_delivery_man": emp_a.name,
            "entry_datetime": assign_dt,
            "booklets": [{"booklet": booklet_name}],
        })
        assign_entry.insert(ignore_permissions=True)
        assign_entry.submit()

        transfer_dt = add_to_date(now(), days=-5)
        transfer_entry = frappe.get_doc({
            "doctype": "Purisol Custody Entry",
            "entry_type": "Transfer",
            "from_delivery_man": emp_a.name,
            "to_delivery_man": emp_b.name,
            "entry_datetime": transfer_dt,
            "booklets": [{"booklet": booklet_name}],
        })
        transfer_entry.insert(ignore_permissions=True)
        transfer_entry.submit()

        data = _run_report()
        row = next((r for r in data if r["booklet"] == booklet_name), None)
        self.assertIsNotNone(row)

        expected_days = date_diff(nowdate(), transfer_dt[:10])
        wrong_days = date_diff(nowdate(), assign_dt[:10])

        self.assertAlmostEqual(row["days_in_custody"], expected_days, delta=1)
        self.assertNotAlmostEqual(row["days_in_custody"], wrong_days, delta=1)
