import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.api.booklet_generation import purisol_generate_booklets


def _as_admin():
    frappe.set_user("Administrator")
    frappe.utils.get_roles = lambda user=None: [
        "Purisol Administrator",
        "Administrator",
        "System Manager",
        "All",
    ]


class TestSyncGeneration(FrappeTestCase):
    def setUp(self):
        _as_admin()

    def test_sync_generation_5_booklets(self):
        result = purisol_generate_booklets(5)
        self.assertEqual(result["mode"], "sync")
        self.assertIn("first_booklet", result)
        self.assertIn("last_booklet", result)
        self.assertEqual(result["total_coupons"], 100)

        first_k = int(result["first_booklet"].split("-")[1])
        last_k = int(result["last_booklet"].split("-")[1])
        self.assertEqual(last_k - first_k + 1, 5)

        expected_names = [f"WP-{k:05d}" for k in range(first_k, last_k + 1)]
        booklets = frappe.get_all(
            "Purisol Coupon Booklet",
            filters={"name": ["in", expected_names]},
            fields=["name", "status"],
        )
        self.assertEqual(len(booklets), 5)
        for b in booklets:
            self.assertEqual(b["status"], "In Stock")

        coupons = frappe.get_all(
            "Purisol Coupon",
            filters={"booklet": ["in", [b["name"] for b in booklets]]},
            fields=["name", "status"],
        )
        self.assertEqual(len(coupons), 100)
        for c in coupons:
            self.assertEqual(c["status"], "Available")

    def test_sync_generation_then_another_batch(self):
        result1 = purisol_generate_booklets(3)
        result2 = purisol_generate_booklets(2)

        k1_last = int(result1["last_booklet"].split("-")[1])
        k2_first = int(result2["first_booklet"].split("-")[1])
        self.assertEqual(k2_first, k1_last + 1)

        b2_name = result2["first_booklet"]
        k2 = int(b2_name.split("-")[1])
        coupons = frappe.get_all(
            "Purisol Coupon",
            filters={"booklet": b2_name},
            fields=["name"],
            order_by="name asc",
        )
        coupon_nums = [int(c["name"].split("-")[1]) for c in coupons]
        expected_first = (k2 - 1) * 20 + 1
        self.assertEqual(coupon_nums[0], expected_first)
        self.assertEqual(coupon_nums[-1], k2 * 20)

    def test_generation_rejects_zero_quantity(self):
        self.assertRaises(frappe.ValidationError, purisol_generate_booklets, 0)

    def test_generation_rejects_negative_quantity(self):
        self.assertRaises(frappe.ValidationError, purisol_generate_booklets, -1)

    def test_generation_with_batch_id(self):
        result = purisol_generate_booklets(2, batch_id="BATCH-TEST-001")
        booklets = frappe.get_all(
            "Purisol Coupon Booklet",
            filters={"name": ["in", [result["first_booklet"], result["last_booklet"]]]},
            fields=["batch_id"],
        )
        for b in booklets:
            self.assertEqual(b["batch_id"], "BATCH-TEST-001")

    def test_generation_summary_shape(self):
        result = purisol_generate_booklets(1)
        for key in ("mode", "first_booklet", "last_booklet", "total_coupons"):
            self.assertIn(key, result)


class TestAsyncGeneration(FrappeTestCase):
    def setUp(self):
        _as_admin()

    def test_async_generation_50_booklets(self):
        import unittest.mock as mock

        captured = {}

        def fake_enqueue(method, **kwargs):
            captured["method"] = method
            captured["kwargs"] = kwargs
            from cx_purisol.cx_purisol.api.booklet_generation import (
                _run_generate_booklets_job,
            )

            _run_generate_booklets_job(
                quantity=kwargs["quantity"],
                batch_id=kwargs.get("batch_id"),
                user=kwargs["user"],
                job_name=kwargs.get("job_name", "test_job"),
            )
            return mock.MagicMock(id="test_job")

        with mock.patch("frappe.enqueue", side_effect=fake_enqueue):
            result = purisol_generate_booklets(50)

        self.assertEqual(result["mode"], "async")
        self.assertIn("job_name", result)
        self.assertIn("channel", result)
        self.assertEqual(result["quantity"], 50)

        total = frappe.db.count("Purisol Coupon Booklet")
        self.assertGreaterEqual(total, 50)


class TestBatchIdFilter(FrappeTestCase):
    """T026 - booklets filterable by batch_id."""

    def setUp(self):
        _as_admin()
        import uuid
        self._run_id = uuid.uuid4().hex[:8]

    def test_booklets_filterable_by_batch_id(self):
        id_a = f"FILTER-BATCH-A-{self._run_id}"
        id_b = f"FILTER-BATCH-B-{self._run_id}"
        purisol_generate_booklets(2, batch_id=id_a)
        purisol_generate_booklets(3, batch_id=id_b)

        batch_a = frappe.get_all(
            "Purisol Coupon Booklet",
            filters={"batch_id": id_a},
            fields=["name"],
        )
        batch_b = frappe.get_all(
            "Purisol Coupon Booklet",
            filters={"batch_id": id_b},
            fields=["name"],
        )
        self.assertEqual(len(batch_a), 2)
        self.assertEqual(len(batch_b), 3)
        names_a = {r["name"] for r in batch_a}
        names_b = {r["name"] for r in batch_b}
        self.assertTrue(names_a.isdisjoint(names_b))
