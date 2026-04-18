import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.tests.fixtures import make_sold_booklet_ready_for_consumption

test_ignore = ["Customer", "Employee", "Sales Invoice", "Purisol Coupon Booklet", "Purisol Coupon"]


def _make_entry(delivery_man, coupons):
    doc = frappe.get_doc({
        "doctype": "Purisol Coupon Consumption Entry",
        "posting_date": frappe.utils.today(),
        "posting_time": frappe.utils.nowtime(),
        "delivery_man": delivery_man,
        "coupons": [{"coupon": c} for c in coupons],
    })
    doc.insert(ignore_permissions=True)
    return doc


class TestConsumptionFlowsUS1(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_mode_a_three_coupons_happy_path(self):
        _, emp, booklet, coupons = make_sold_booklet_ready_for_consumption()
        picked = coupons[:3]
        entry = _make_entry(emp.name, picked)
        entry.submit()

        posting_dt = entry.posting_datetime

        # Verify consumed coupons
        for c in picked:
            doc = frappe.get_doc("Purisol Coupon", c)
            self.assertEqual(doc.status, "Consumed")
            self.assertEqual(str(doc.consumed_on), str(posting_dt))
            self.assertEqual(doc.consumed_by_delivery_man, emp.name)
            self.assertEqual(doc.consumption_entry, entry.name)

        # Verify untouched coupons
        for c in coupons[3:]:
            doc = frappe.get_doc("Purisol Coupon", c)
            self.assertEqual(doc.status, "Available")

        # Verify booklet aggregates
        b = frappe.get_doc("Purisol Coupon Booklet", booklet)
        self.assertEqual(b.consumed_count, 3)
        self.assertEqual(b.remaining_count, 17)
        self.assertEqual(b.status, "Sold")

    def test_mode_a_multi_booklet_single_entry(self):
        _, emp1, booklet1, coupons1 = make_sold_booklet_ready_for_consumption(
            customer_name="Acme Co.", employee_name="Ali"
        )
        _, emp2, booklet2, coupons2 = make_sold_booklet_ready_for_consumption(
            customer_name="Beta Ltd.", employee_name="Bassam"
        )
        picked = [coupons1[0], coupons1[1], coupons2[0], coupons2[1]]
        entry = _make_entry(emp1.name, picked)
        entry.submit()

        for c in [coupons1[0], coupons1[1]]:
            self.assertEqual(frappe.db.get_value("Purisol Coupon", c, "status"), "Consumed")
        for c in [coupons2[0], coupons2[1]]:
            self.assertEqual(frappe.db.get_value("Purisol Coupon", c, "status"), "Consumed")

        b1 = frappe.get_doc("Purisol Coupon Booklet", booklet1)
        self.assertEqual(b1.consumed_count, 2)
        self.assertEqual(b1.remaining_count, 18)

        b2 = frappe.get_doc("Purisol Coupon Booklet", booklet2)
        self.assertEqual(b2.consumed_count, 2)
        self.assertEqual(b2.remaining_count, 18)

    def test_cancel_round_trip_no_depletion(self):
        _, emp, booklet, coupons = make_sold_booklet_ready_for_consumption()
        picked = coupons[:3]
        entry = _make_entry(emp.name, picked)
        entry.submit()
        entry.cancel()

        # Coupons revert to Available with cleared metadata
        for c in picked:
            doc = frappe.get_doc("Purisol Coupon", c)
            self.assertEqual(doc.status, "Available")
            self.assertIsNone(doc.consumed_on)
            self.assertFalse(doc.consumed_by_delivery_man)
            self.assertFalse(doc.consumption_entry)

        # Booklet reverts
        b = frappe.get_doc("Purisol Coupon Booklet", booklet)
        self.assertEqual(b.consumed_count, 0)
        self.assertEqual(b.remaining_count, 20)
        self.assertEqual(b.status, "Sold")


# ---------------------------------------------------------------------------
# User Story 2 — Mode B: resolve coupons by number
# ---------------------------------------------------------------------------

class TestConsumptionFlowsUS2(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_mode_b_two_booklets_happy_path(self):
        _, emp1, booklet1, coupons1 = make_sold_booklet_ready_for_consumption(
            customer_name="Acme Co.", employee_name="Ali"
        )
        _, emp2, booklet2, coupons2 = make_sold_booklet_ready_for_consumption(
            customer_name="Beta Ltd.", employee_name="Bassam"
        )
        # Programmatically build an entry from coupons across two booklets (as Mode B would)
        picked = [coupons1[0], coupons2[0]]
        entry = _make_entry(emp1.name, picked)
        entry.submit()

        self.assertEqual(frappe.db.get_value("Purisol Coupon", coupons1[0], "status"), "Consumed")
        self.assertEqual(frappe.db.get_value("Purisol Coupon", coupons2[0], "status"), "Consumed")

        b1 = frappe.get_doc("Purisol Coupon Booklet", booklet1)
        self.assertEqual(b1.consumed_count, 1)
        b2 = frappe.get_doc("Purisol Coupon Booklet", booklet2)
        self.assertEqual(b2.consumed_count, 1)

    def test_mode_a_plus_mode_b_mixed(self):
        _, emp, booklet, coupons = make_sold_booklet_ready_for_consumption()
        # Mix: 3 rows from Mode A + 2 from Mode B (structurally identical rows)
        picked = coupons[:5]
        entry = _make_entry(emp.name, picked)
        entry.submit()

        for c in picked:
            self.assertEqual(frappe.db.get_value("Purisol Coupon", c, "status"), "Consumed")

        b = frappe.get_doc("Purisol Coupon Booklet", booklet)
        self.assertEqual(b.consumed_count, 5)
        self.assertEqual(b.remaining_count, 15)

    def test_resolve_coupons_partial(self):
        from cx_purisol.cx_purisol.api.consumption import resolve_coupons
        frappe.utils.get_roles = lambda user=None: [
            "Purisol Administrator", "Administrator", "System Manager", "All"
        ]
        _, _, _, coupons = make_sold_booklet_ready_for_consumption()
        names = [coupons[0], "CP-99999", coupons[1]]
        result = resolve_coupons(names)
        resolved_names = [r["coupon"] for r in result["resolved"]]
        self.assertIn(coupons[0], resolved_names)
        self.assertIn(coupons[1], resolved_names)
        self.assertEqual(result["unresolved"], ["CP-99999"])


# ---------------------------------------------------------------------------
# User Story 3 — Auto-deplete on 20th consumed coupon
# ---------------------------------------------------------------------------

class TestConsumptionFlowsUS3(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_auto_deplete_19_plus_1(self):
        _, emp, booklet, coupons = make_sold_booklet_ready_for_consumption()
        # Pre-consume 19 coupons via a first entry
        first_entry = _make_entry(emp.name, coupons[:19])
        first_entry.submit()

        # Submit the 20th coupon
        last_entry = _make_entry(emp.name, [coupons[19]])
        last_entry.submit()

        b = frappe.get_doc("Purisol Coupon Booklet", booklet)
        self.assertEqual(b.status, "Depleted")
        self.assertIsNotNone(b.depleted_on)
        self.assertEqual(b.consumed_count, 20)
        self.assertEqual(b.remaining_count, 0)

        # Verify Comment was added
        comments = frappe.get_all(
            "Comment",
            filters={"reference_doctype": "Purisol Coupon Booklet", "reference_name": booklet},
            fields=["content"],
        )
        comment_texts = [c["content"] for c in comments]
        self.assertTrue(any(last_entry.name in t for t in comment_texts))

    def test_auto_deplete_all_20_in_single_entry(self):
        _, emp, booklet, coupons = make_sold_booklet_ready_for_consumption()
        entry = _make_entry(emp.name, coupons)
        entry.submit()

        b = frappe.get_doc("Purisol Coupon Booklet", booklet)
        self.assertEqual(b.status, "Depleted")
        self.assertEqual(b.consumed_count, 20)

    def test_multi_booklet_one_depletes_one_partial(self):
        _, emp1, booklet1, coupons1 = make_sold_booklet_ready_for_consumption(
            customer_name="Acme Co.", employee_name="Ali"
        )
        _, emp2, booklet2, coupons2 = make_sold_booklet_ready_for_consumption(
            customer_name="Beta Ltd.", employee_name="Bassam"
        )
        # booklet1: all 20 → depleted; booklet2: only 5
        picked = coupons1 + coupons2[:5]
        entry = _make_entry(emp1.name, picked)
        entry.submit()

        b1 = frappe.get_doc("Purisol Coupon Booklet", booklet1)
        self.assertEqual(b1.status, "Depleted")
        b2 = frappe.get_doc("Purisol Coupon Booklet", booklet2)
        self.assertEqual(b2.status, "Sold")
        self.assertEqual(b2.consumed_count, 5)

    def test_cancel_reverts_depletion(self):
        _, emp, booklet, coupons = make_sold_booklet_ready_for_consumption()
        first_entry = _make_entry(emp.name, coupons[:19])
        first_entry.submit()
        last_entry = _make_entry(emp.name, [coupons[19]])
        last_entry.submit()

        b = frappe.get_doc("Purisol Coupon Booklet", booklet)
        self.assertEqual(b.status, "Depleted")

        last_entry.cancel()

        b.reload()
        self.assertEqual(b.status, "Sold")
        self.assertIsNone(b.depleted_on)
        self.assertEqual(b.consumed_count, 19)

        # Verify reversal Comment
        comments = frappe.get_all(
            "Comment",
            filters={"reference_doctype": "Purisol Coupon Booklet", "reference_name": booklet},
            fields=["content"],
        )
        comment_texts = [c["content"] for c in comments]
        self.assertTrue(any("cancelled" in t.lower() for t in comment_texts))

    def test_cancel_partial_entry_reverts_depletion_when_other_entry_has_partial(self):
        """When two entries split 20 coupons and the second depletes the booklet,
        cancelling the first drops consumed_count below 20 → booklet reverts to Sold."""
        _, emp, booklet, coupons = make_sold_booklet_ready_for_consumption()
        # Entry A: consume first 10 coupons
        entry_a = _make_entry(emp.name, coupons[:10])
        entry_a.submit()
        # Entry B: consume remaining 10 → depletes booklet
        entry_b = _make_entry(emp.name, coupons[10:])
        entry_b.submit()

        b = frappe.get_doc("Purisol Coupon Booklet", booklet)
        self.assertEqual(b.status, "Depleted")

        # Cancel entry A: entry B's 10 coupons remain Consumed; consumed_count = 10 < 20
        entry_a.cancel()
        b.reload()
        self.assertEqual(b.consumed_count, 10)
        # consumed_count < 20 → booklet reverts to Sold
        self.assertEqual(b.status, "Sold")


# ---------------------------------------------------------------------------
# User Story 4 — Reject invalid submissions all-or-nothing
# ---------------------------------------------------------------------------

class TestConsumptionFlowsUS4(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_reject_unknown_coupon_atomically(self):
        _, emp, booklet, coupons = make_sold_booklet_ready_for_consumption()
        # 2 valid + 1 unknown
        picked = [coupons[0], coupons[1], "CP-99999"]
        entry = _make_entry(emp.name, picked)
        with self.assertRaises(frappe.ValidationError) as ctx:
            entry.submit()
        self.assertIn("CP-99999", str(ctx.exception))

        # Valid coupons must still be Available
        for c in [coupons[0], coupons[1]]:
            self.assertEqual(frappe.db.get_value("Purisol Coupon", c, "status"), "Available")

    def test_reject_already_consumed_with_prior_entry_diagnostic(self):
        _, emp, booklet, coupons = make_sold_booklet_ready_for_consumption()
        c = coupons[0]
        # First entry consumes coupons[0]
        first = _make_entry(emp.name, [c])
        first.submit()

        # Second entry tries to consume the same coupon
        second = _make_entry(emp.name, [c, coupons[1]])
        with self.assertRaises(frappe.ValidationError) as ctx:
            second.submit()
        err = str(ctx.exception)
        self.assertIn(c, err)
        self.assertIn(first.name, err)

        # coupons[1] must remain Available (atomicity)
        self.assertEqual(frappe.db.get_value("Purisol Coupon", coupons[1], "status"), "Available")

    def test_reject_empty_entry_at_validate(self):
        _, emp, _, _ = make_sold_booklet_ready_for_consumption()
        doc = frappe.get_doc({
            "doctype": "Purisol Coupon Consumption Entry",
            "posting_date": frappe.utils.today(),
            "posting_time": frappe.utils.nowtime(),
            "delivery_man": emp.name,
            "coupons": [],
        })
        with self.assertRaises(frappe.ValidationError) as ctx:
            doc.insert(ignore_permissions=True)
        self.assertIn("at least one coupon", str(ctx.exception))

    def test_reject_duplicate_in_entry(self):
        _, emp, _, coupons = make_sold_booklet_ready_for_consumption()
        c = coupons[0]
        doc = frappe.get_doc({
            "doctype": "Purisol Coupon Consumption Entry",
            "posting_date": frappe.utils.today(),
            "posting_time": frappe.utils.nowtime(),
            "delivery_man": emp.name,
            "coupons": [{"coupon": c}, {"coupon": c}],
        })
        with self.assertRaises(frappe.ValidationError) as ctx:
            doc.insert(ignore_permissions=True)
        self.assertIn(c, str(ctx.exception))

    def test_coupon_from_non_sold_booklet_does_not_block(self):
        """FR-035: Phase 5 defers the warning; submit succeeds with no discrepancy row."""
        from cx_purisol.cx_purisol.tests.fixtures import make_booklet_in_stock
        _, emp, _, _ = make_sold_booklet_ready_for_consumption()
        in_stock_booklet = make_booklet_in_stock()
        # Create a coupon manually linked to the in-stock booklet
        k = int(in_stock_booklet.name.split("-")[1])
        coupon = frappe.get_doc({
            "doctype": "Purisol Coupon",
            "booklet": in_stock_booklet.name,
            "page_number": 1,
            "status": "Available",
            "coupon_number": f"CP-{(k - 1) * 20 + 1:05d}",
        })
        coupon.insert(ignore_permissions=True)

        entry = _make_entry(emp.name, [coupon.name])
        entry.submit()
        self.assertEqual(entry.docstatus, 1)
        self.assertEqual(len(entry.discrepancies_detected), 0)
