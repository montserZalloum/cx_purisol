import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.api.consumption import list_available_coupons, resolve_coupons
from cx_purisol.cx_purisol.tests.fixtures import make_sold_booklet_ready_for_consumption

test_ignore = ["Customer", "Employee", "Sales Invoice", "Purisol Coupon Booklet", "Purisol Coupon"]


class TestListAvailableCoupons(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        _, _, self._booklet, self._coupons = make_sold_booklet_ready_for_consumption()

    def _as_non_admin(self, fn):
        frappe.set_user("Guest")
        try:
            fn()
        finally:
            frappe.set_user("Administrator")

    def test_non_admin_raises_permission_error(self):
        with self.assertRaises(frappe.PermissionError):
            self._as_non_admin(lambda: list_available_coupons(self._booklet))

    def test_happy_path_returns_20_sorted_rows(self):
        frappe.utils.get_roles = lambda user=None: ["Purisol Administrator", "Administrator", "System Manager", "All"]
        result = list_available_coupons(self._booklet)
        self.assertEqual(len(result), 20)
        pages = [r["page_number"] for r in result]
        self.assertEqual(pages, sorted(pages))

    def test_after_consuming_3_returns_17(self):
        frappe.utils.get_roles = lambda user=None: ["Purisol Administrator", "Administrator", "System Manager", "All"]
        for c in self._coupons[:3]:
            frappe.db.set_value(
                "Purisol Coupon", c, {"status": "Consumed"}, update_modified=False
            )
        result = list_available_coupons(self._booklet)
        self.assertEqual(len(result), 17)

    def test_unknown_booklet_returns_empty(self):
        frappe.utils.get_roles = lambda user=None: ["Purisol Administrator", "Administrator", "System Manager", "All"]
        result = list_available_coupons("WP-99999")
        self.assertEqual(result, [])

    def test_empty_booklet_param_raises(self):
        frappe.utils.get_roles = lambda user=None: ["Purisol Administrator", "Administrator", "System Manager", "All"]
        with self.assertRaises(frappe.ValidationError):
            list_available_coupons("")


class TestResolveCoupons(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        frappe.utils.get_roles = lambda user=None: ["Purisol Administrator", "Administrator", "System Manager", "All"]
        _, _, booklet1, self._coupons1 = make_sold_booklet_ready_for_consumption(
            customer_name="Acme Co.", employee_name="Ali"
        )
        _, _, booklet2, self._coupons2 = make_sold_booklet_ready_for_consumption(
            customer_name="Beta Ltd.", employee_name="Bassam"
        )
        self._booklet1 = booklet1
        self._booklet2 = booklet2

    def _as_non_admin(self, fn):
        frappe.set_user("Guest")
        try:
            fn()
        finally:
            frappe.set_user("Administrator")

    def test_non_admin_raises_permission_error(self):
        with self.assertRaises(frappe.PermissionError):
            self._as_non_admin(lambda: resolve_coupons([self._coupons1[0]]))

    def test_happy_path_three_valid_resolved_with_order_preserved(self):
        names = [self._coupons1[0], self._coupons1[2], self._coupons1[1]]
        result = resolve_coupons(names)
        resolved_names = [r["coupon"] for r in result["resolved"]]
        self.assertEqual(resolved_names, names)
        self.assertEqual(result["unresolved"], [])
        for r in result["resolved"]:
            self.assertEqual(r["booklet"], self._booklet1)

    def test_mixed_list_two_valid_one_unknown(self):
        names = [self._coupons1[0], "CP-99999", self._coupons2[0]]
        result = resolve_coupons(names)
        resolved_names = [r["coupon"] for r in result["resolved"]]
        self.assertIn(self._coupons1[0], resolved_names)
        self.assertIn(self._coupons2[0], resolved_names)
        self.assertEqual(result["unresolved"], ["CP-99999"])

    def test_blank_lines_filtered_silently(self):
        names = [self._coupons1[0], "", "   ", self._coupons1[1]]
        result = resolve_coupons(names)
        self.assertEqual(len(result["resolved"]), 2)
        self.assertEqual(result["unresolved"], [])

    def test_all_blank_raises_no_coupon_numbers_error(self):
        with self.assertRaises(frappe.ValidationError) as ctx:
            resolve_coupons(["", "   "])
        self.assertIn("No coupon numbers", str(ctx.exception))

    def test_already_consumed_coupon_still_in_resolved(self):
        c = self._coupons1[0]
        frappe.db.set_value("Purisol Coupon", c, {"status": "Consumed"}, update_modified=False)
        result = resolve_coupons([c])
        consumed_row = next((r for r in result["resolved"] if r["coupon"] == c), None)
        self.assertIsNotNone(consumed_row)
        self.assertEqual(consumed_row["status"], "Consumed")
        self.assertEqual(result["unresolved"], [])

    def test_resolved_row_includes_available_status(self):
        c = self._coupons1[0]
        result = resolve_coupons([c])
        row = next((r for r in result["resolved"] if r["coupon"] == c), None)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "Available")
