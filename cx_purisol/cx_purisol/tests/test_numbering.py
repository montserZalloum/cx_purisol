import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.api.booklet_generation import _coupon_range_for_booklet


class TestCouponRangeForBooklet(FrappeTestCase):
    def test_booklet_1(self):
        first, last = _coupon_range_for_booklet(1)
        self.assertEqual(first, "CP-00001")
        self.assertEqual(last, "CP-00020")

    def test_booklet_2(self):
        first, last = _coupon_range_for_booklet(2)
        self.assertEqual(first, "CP-00021")
        self.assertEqual(last, "CP-00040")

    def test_booklet_50(self):
        first, last = _coupon_range_for_booklet(50)
        self.assertEqual(first, "CP-00981")
        self.assertEqual(last, "CP-01000")

    def test_range_length_always_20(self):
        for n in range(1, 101):
            first, last = _coupon_range_for_booklet(n)
            first_num = int(first.split("-")[1])
            last_num = int(last.split("-")[1])
            self.assertEqual(last_num - first_num + 1, 20, f"booklet {n} range length != 20")

    def test_consecutive_booklets_are_contiguous(self):
        for n in range(1, 100):
            _, last_n = _coupon_range_for_booklet(n)
            first_next, _ = _coupon_range_for_booklet(n + 1)
            self.assertEqual(
                int(first_next.split("-")[1]),
                int(last_n.split("-")[1]) + 1,
                f"gap between booklet {n} and {n+1}",
            )
