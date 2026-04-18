"""Unit tests for the discrepancy detection service — Phase 5 US1, US2 & US6.

T016: Gap algorithm edge cases (_detect_missing_coupons)
T017: Estimated-amount three-tier resolution (_compute_estimated_amount)
T018: Related delivery-men auto-population (_auto_populate_related_delivery_men)
T029: Unassigned-booklet per-coupon rule (_detect_unassigned_booklets)
T031: No-mutation guarantee (detect_for_entry)
T048: US6 related_delivery_men population invariants
"""
from __future__ import annotations

from types import SimpleNamespace

import frappe
from frappe.tests.utils import FrappeTestCase

from cx_purisol.cx_purisol.api.discrepancy import (
    _auto_populate_related_delivery_men,
    _compute_estimated_amount,
    _detect_missing_coupons,
    _detect_unassigned_booklets,
    detect_for_entry,
)
from cx_purisol.cx_purisol.tests.fixtures import (
    configure_purisol_settings,
    ensure_coupon_item,
    ensure_customer,
    ensure_item_price,
    ensure_price_list,
    make_booklet_in_stock,
    make_booklet_with_consumed_coupons,
    make_employee,
    make_sold_booklet_ready_for_consumption,
    seed_open_discrepancy,
    submit_assign,
)

test_ignore = [
    "Customer",
    "Employee",
    "Sales Invoice",
    "Purisol Coupon Booklet",
    "Purisol Coupon",
    "Purisol Coupon Discrepancy",
    "Purisol Custody Entry",
    "Purisol Coupon Consumption Entry",
]

_COUPON_COUNTER = [0]


def _next_coupon_number():
    _COUPON_COUNTER[0] += 1
    return f"CPN-UNIT-{_COUPON_COUNTER[0]:04d}"


def _make_booklet_with_pages_consumed(customer_name, consumed_page_numbers):
    """Create a Sold booklet; mark the given page numbers as Consumed via direct DB write.

    Returns (booklet_name, page_map) where page_map is {page_number: coupon_name}.
    Also returns a real, submitted Consumption Entry whose name can be used as a valid link.
    """
    from cx_purisol.cx_purisol.api.booklet_generation import _create_booklet_and_coupons
    from cx_purisol.cx_purisol.api.sell_booklets import purisol_create_sales_invoice_for_booklets

    item = ensure_coupon_item()
    pl = ensure_price_list("Test-UnitDetect-PL")
    ensure_item_price(item.name, pl.name, 200)
    ensure_customer(customer_name, default_price_list=pl.name)
    configure_purisol_settings(coupon_item=item.name, default_price_list=pl.name)

    booklet_name, _ = _create_booklet_and_coupons(batch_id=None)
    result = purisol_create_sales_invoice_for_booklets(customer_name, [booklet_name])
    si = frappe.get_doc("Sales Invoice", result["name"])
    si.submit()

    all_coupons = frappe.get_all(
        "Purisol Coupon",
        filters={"booklet": booklet_name},
        fields=["name", "page_number"],
        order_by="page_number asc",
    )
    page_map = {c["page_number"]: c["name"] for c in all_coupons}

    for page_num in consumed_page_numbers:
        if page_num in page_map:
            frappe.db.set_value("Purisol Coupon", page_map[page_num], "status", "Consumed")

    return booklet_name, page_map


# ---------------------------------------------------------------------------
# T016 — Gap algorithm edge cases
# ---------------------------------------------------------------------------


class TestGapAlgorithm(FrappeTestCase):
    """Unit tests for _detect_missing_coupons — gap algorithm edge cases."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.customer_name = "GapAlgo-Customer"
        self.emp = make_employee("GapAlgo", "Tester")

    def _real_entry_for(self, booklet_name, consumed_pages):
        """Create and submit a real consumption entry for the given pages of booklet_name.

        Returns the submitted entry document, which supplies a valid name for the link field.
        """
        all_coupons = frappe.get_all(
            "Purisol Coupon",
            filters={"booklet": booklet_name},
            fields=["name", "page_number"],
            order_by="page_number asc",
        )
        page_map = {c["page_number"]: c["name"] for c in all_coupons}
        coupon_names = [page_map[p] for p in consumed_pages if p in page_map]
        entry = frappe.get_doc({
            "doctype": "Purisol Coupon Consumption Entry",
            "posting_date": frappe.utils.today(),
            "posting_time": frappe.utils.nowtime(),
            "delivery_man": self.emp.name,
            "coupons": [{"coupon": c} for c in coupon_names],
        })
        entry.insert(ignore_permissions=True)
        entry.submit()
        return entry

    def test_gap_interior(self):
        """Pages {1,2} consumed then {7,8} consumed directly → gap {3,4,5,6}."""
        from cx_purisol.cx_purisol.api.booklet_generation import _create_booklet_and_coupons
        from cx_purisol.cx_purisol.api.sell_booklets import purisol_create_sales_invoice_for_booklets

        item = ensure_coupon_item()
        pl = ensure_price_list("Test-UnitDetect-PL")
        ensure_item_price(item.name, pl.name, 200)
        ensure_customer(self.customer_name, default_price_list=pl.name)
        configure_purisol_settings(coupon_item=item.name, default_price_list=pl.name)

        booklet_name, _ = _create_booklet_and_coupons(batch_id=None)
        result = purisol_create_sales_invoice_for_booklets(self.customer_name, [booklet_name])
        si = frappe.get_doc("Sales Invoice", result["name"])
        si.submit()

        all_coupons = frappe.get_all(
            "Purisol Coupon",
            filters={"booklet": booklet_name},
            fields=["name", "page_number"],
            order_by="page_number asc",
        )
        page_map = {c["page_number"]: c["name"] for c in all_coupons}

        # Consume pages 1,2 via a real entry (this runs on_submit detection, no gap yet)
        first_entry = self._real_entry_for(booklet_name, [1, 2])

        # Directly flip pages 7,8 to Consumed without a new entry (simulates second submission)
        for p in (7, 8):
            frappe.db.set_value("Purisol Coupon", page_map[p], "status", "Consumed")

        # Call detection with the first entry as the triggering entity
        result = _detect_missing_coupons(first_entry)
        self.assertEqual(len(result), 1)
        disc = frappe.get_doc("Purisol Coupon Discrepancy", result[0])
        affected = {r.coupon for r in disc.affected_coupons}
        self.assertEqual(affected, {page_map[p] for p in (3, 4, 5, 6)})
        self.assertEqual(disc.discrepancy_type, "Missing Coupons")
        self.assertEqual(disc.status, "Open")
        self.assertEqual(disc.booklet, booklet_name)

    def test_gap_none_when_contiguous(self):
        """Pages {1,2,3,4} Consumed → interior gap is empty, no discrepancy created."""
        booklet_name, first_entry_name = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1, 2)
        )
        all_coupons = frappe.get_all(
            "Purisol Coupon",
            filters={"booklet": booklet_name},
            fields=["name", "page_number"],
        )
        page_map = {c["page_number"]: c["name"] for c in all_coupons}
        # Flip pages 3,4 to Consumed
        for p in (3, 4):
            frappe.db.set_value("Purisol Coupon", page_map[p], "status", "Consumed")

        first_entry = frappe.get_doc("Purisol Coupon Consumption Entry", first_entry_name)
        result = _detect_missing_coupons(first_entry)
        self.assertEqual(result, [])

    def test_gap_none_below_min(self):
        """Only 1 consumed page -> len(consumed_pages) < 2, detection skips booklet."""
        _, first_entry_name = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(5,)
        )
        # Only page 5 is consumed; len = 1 → no gap possible
        first_entry = frappe.get_doc("Purisol Coupon Consumption Entry", first_entry_name)
        result = _detect_missing_coupons(first_entry)
        self.assertEqual(result, [])

    def test_gap_none_above_max(self):
        """Pages 1-10 all Consumed -> no Available gap page, no discrepancy."""
        booklet_name, first_entry_name = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1, 2)
        )
        all_coupons = frappe.get_all(
            "Purisol Coupon",
            filters={"booklet": booklet_name},
            fields=["name", "page_number"],
        )
        page_map = {c["page_number"]: c["name"] for c in all_coupons}
        for p in range(3, 11):
            frappe.db.set_value("Purisol Coupon", page_map[p], "status", "Consumed")

        first_entry = frappe.get_doc("Purisol Coupon Consumption Entry", first_entry_name)
        result = _detect_missing_coupons(first_entry)
        self.assertEqual(result, [])

    def test_gap_dedup_against_open_discrepancy(self):
        """Open discrepancy covers pages 3,4 → only pages 5,6 produce a new discrepancy."""
        booklet_name, first_entry_name = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1, 2)
        )
        all_coupons = frappe.get_all(
            "Purisol Coupon",
            filters={"booklet": booklet_name},
            fields=["name", "page_number"],
        )
        page_map = {c["page_number"]: c["name"] for c in all_coupons}

        # Flip 7,8 to Consumed so gap = {3,4,5,6}
        for p in (7, 8):
            frappe.db.set_value("Purisol Coupon", page_map[p], "status", "Consumed")

        # Seed open discrepancy covering pages 3,4
        seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=booklet_name,
            customer=self.customer_name,
            affected_coupons=[page_map[3], page_map[4]],
        )

        first_entry = frappe.get_doc("Purisol Coupon Consumption Entry", first_entry_name)
        result = _detect_missing_coupons(first_entry)
        self.assertEqual(len(result), 1)
        disc = frappe.get_doc("Purisol Coupon Discrepancy", result[0])
        affected = {r.coupon for r in disc.affected_coupons}
        self.assertEqual(affected, {page_map[5], page_map[6]})

    def test_gap_fully_covered_produces_no_discrepancy(self):
        """Open discrepancy covers entire gap {3,4,5,6} → no new discrepancy."""
        booklet_name, first_entry_name = make_booklet_with_consumed_coupons(
            self.customer_name, self.emp, consumed_pages=(1, 2)
        )
        all_coupons = frappe.get_all(
            "Purisol Coupon",
            filters={"booklet": booklet_name},
            fields=["name", "page_number"],
        )
        page_map = {c["page_number"]: c["name"] for c in all_coupons}
        for p in (7, 8):
            frappe.db.set_value("Purisol Coupon", page_map[p], "status", "Consumed")

        seed_open_discrepancy(
            discrepancy_type="Missing Coupons",
            booklet=booklet_name,
            customer=self.customer_name,
            affected_coupons=[page_map[p] for p in (3, 4, 5, 6)],
        )

        first_entry = frappe.get_doc("Purisol Coupon Consumption Entry", first_entry_name)
        result = _detect_missing_coupons(first_entry)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# T017 — _compute_estimated_amount three-tier resolution
# ---------------------------------------------------------------------------


class TestComputeEstimatedAmount(FrappeTestCase):
    """Unit tests for _compute_estimated_amount."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_estimated_amount_from_invoice_line(self):
        """Sold booklet with invoice: rate / 20 * count."""
        _, _, booklet_name, _ = make_sold_booklet_ready_for_consumption(
            customer_name="InvAmt-Customer", employee_name="InvAmt-Emp"
        )
        # make_sold_booklet_ready_for_consumption sets item price = 100; unit = 100/20 = 5
        booklet = frappe.get_doc("Purisol Coupon Booklet", booklet_name)
        amount = _compute_estimated_amount(booklet, 4)
        self.assertAlmostEqual(amount, 20.0, places=2)

    def test_estimated_amount_from_price_list_fallback(self):
        """In-Stock booklet with no invoice: uses Item Price / 20 fallback."""
        item = ensure_coupon_item()
        pl = ensure_price_list("FallbackAmt-PL")
        ensure_item_price(item.name, pl.name, 400)
        configure_purisol_settings(coupon_item=item.name, default_price_list=pl.name)

        booklet = make_booklet_in_stock()
        amount = _compute_estimated_amount(booklet, 3)
        self.assertAlmostEqual(amount, 60.0, places=2)

    def test_estimated_amount_zero_when_nothing_resolves(self):
        """No invoice + no coupon_item in settings → 0.0."""
        settings = frappe.get_single("Purisol Settings")
        orig_item = settings.coupon_item
        orig_pl = settings.default_price_list
        try:
            settings.coupon_item = None
            settings.default_price_list = None
            settings.save(ignore_permissions=True)
            frappe.clear_cache()

            booklet = make_booklet_in_stock()
            amount = _compute_estimated_amount(booklet, 2)
            self.assertEqual(amount, 0.0)
        finally:
            settings.coupon_item = orig_item
            settings.default_price_list = orig_pl
            settings.save(ignore_permissions=True)


# ---------------------------------------------------------------------------
# T018 — _auto_populate_related_delivery_men
# ---------------------------------------------------------------------------


class TestAutoPopulateRelatedDeliveryMen(FrappeTestCase):
    """Unit tests for _auto_populate_related_delivery_men."""

    def setUp(self):
        frappe.set_user("Administrator")

    def _new_disc(self, booklet_name):
        doc = frappe.new_doc("Purisol Coupon Discrepancy")
        doc.discrepancy_type = "Missing Coupons"
        doc.status = "Open"
        doc.booklet = booklet_name
        return doc

    def _coupon_for_booklet(self, booklet_name, page_number=1):
        coupon = frappe.get_doc({
            "doctype": "Purisol Coupon",
            "booklet": booklet_name,
            "page_number": page_number,
            "status": "Available",
            "coupon_number": _next_coupon_number(),
        })
        coupon.insert(ignore_permissions=True)
        return coupon

    def _submit_entry(self, delivery_man, coupons):
        entry = frappe.get_doc({
            "doctype": "Purisol Coupon Consumption Entry",
            "posting_date": frappe.utils.today(),
            "posting_time": frappe.utils.nowtime(),
            "delivery_man": delivery_man,
            "coupons": [{"coupon": c} for c in coupons],
        })
        entry.insert(ignore_permissions=True)
        entry.submit()
        return entry

    def test_related_persons_custody_holder_and_adjacent_30d(self):
        """In-Custody booklet + adjacent entry within 30d → Custody Holder + Adjacent row."""
        emp1 = make_employee("CustHold", "RelTest1")
        emp2 = make_employee("Adjac", "RelTest1")

        booklet = make_booklet_in_stock()
        submit_assign([booklet.name], to_delivery_man=emp1.name)
        coupon = self._coupon_for_booklet(booklet.name, page_number=1)

        prior = frappe.get_doc({
            "doctype": "Purisol Coupon Consumption Entry",
            "posting_date": frappe.utils.add_days(frappe.utils.today(), -10),
            "posting_time": frappe.utils.nowtime(),
            "delivery_man": emp2.name,
            "coupons": [{"coupon": coupon.name}],
        })
        prior.insert(ignore_permissions=True)
        prior.submit()

        booklet_doc = frappe.get_doc("Purisol Coupon Booklet", booklet.name)
        trigger = SimpleNamespace(
            name="FAKE-T-REL1",
            delivery_man=emp2.name,
            posting_date=frappe.utils.today(),
        )
        disc = self._new_disc(booklet.name)
        _auto_populate_related_delivery_men(disc, trigger, booklet_doc)

        role_map = {r.delivery_man: r.role for r in disc.related_delivery_men}
        self.assertEqual(role_map.get(emp1.name), "Custody Holder")
        self.assertEqual(role_map.get(emp2.name), "Submitted Adjacent Coupons")

    def test_related_persons_skip_custody_holder_when_not_in_custody(self):
        """Sold booklet → no Custody Holder row; triggering delivery_man appears as Adjacent."""
        _, emp, booklet_name, _ = make_sold_booklet_ready_for_consumption(
            customer_name="SkipCH-Customer", employee_name="SkipCH-Emp"
        )
        booklet_doc = frappe.get_doc("Purisol Coupon Booklet", booklet_name)
        trigger = SimpleNamespace(
            name="FAKE-T-REL2",
            delivery_man=emp.name,
            posting_date=frappe.utils.today(),
        )
        disc = self._new_disc(booklet_name)
        _auto_populate_related_delivery_men(disc, trigger, booklet_doc)

        for row in disc.related_delivery_men:
            self.assertNotEqual(row.role, "Custody Holder")
        dms = [r.delivery_man for r in disc.related_delivery_men]
        self.assertIn(emp.name, dms)

    def test_related_persons_30day_window_anchored_to_posting_date(self):
        """Entry older than 30 days is excluded from adjacency window."""
        emp_old = make_employee("OldAdj", "RelTest3")
        emp_trigger = make_employee("TriggerOnly", "RelTest3")
        booklet = make_booklet_in_stock()
        coupon = self._coupon_for_booklet(booklet.name, page_number=1)

        old_entry = frappe.get_doc({
            "doctype": "Purisol Coupon Consumption Entry",
            "posting_date": frappe.utils.add_days(frappe.utils.today(), -40),
            "posting_time": frappe.utils.nowtime(),
            "delivery_man": emp_old.name,
            "coupons": [{"coupon": coupon.name}],
        })
        old_entry.insert(ignore_permissions=True)
        old_entry.submit()

        booklet_doc = frappe.get_doc("Purisol Coupon Booklet", booklet.name)
        trigger = SimpleNamespace(
            name="FAKE-T-REL3",
            delivery_man=emp_trigger.name,
            posting_date=frappe.utils.today(),
        )
        disc = self._new_disc(booklet.name)
        _auto_populate_related_delivery_men(disc, trigger, booklet_doc)

        dms = [r.delivery_man for r in disc.related_delivery_men]
        self.assertNotIn(emp_old.name, dms)

    def test_related_persons_dedup_when_custody_holder_also_adjacent(self):
        """Custody holder who also has adjacent entries appears once as Custody Holder."""
        emp = make_employee("DedupCH", "RelTest4")
        booklet = make_booklet_in_stock()
        submit_assign([booklet.name], to_delivery_man=emp.name)
        coupon = self._coupon_for_booklet(booklet.name, page_number=2)

        adj = frappe.get_doc({
            "doctype": "Purisol Coupon Consumption Entry",
            "posting_date": frappe.utils.add_days(frappe.utils.today(), -5),
            "posting_time": frappe.utils.nowtime(),
            "delivery_man": emp.name,
            "coupons": [{"coupon": coupon.name}],
        })
        adj.insert(ignore_permissions=True)
        adj.submit()

        booklet_doc = frappe.get_doc("Purisol Coupon Booklet", booklet.name)
        trigger = SimpleNamespace(
            name="FAKE-T-REL4",
            delivery_man=emp.name,
            posting_date=frappe.utils.today(),
        )
        disc = self._new_disc(booklet.name)
        _auto_populate_related_delivery_men(disc, trigger, booklet_doc)

        emp_rows = [r for r in disc.related_delivery_men if r.delivery_man == emp.name]
        self.assertEqual(len(emp_rows), 1)
        self.assertEqual(emp_rows[0].role, "Custody Holder")


# ---------------------------------------------------------------------------
# T029 — _detect_unassigned_booklets per-coupon rule
# ---------------------------------------------------------------------------


class TestUnassignedBookletDetection(FrappeTestCase):
    """Unit tests for _detect_unassigned_booklets — per-coupon, non-Sold triggers discrepancy."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.emp = make_employee("UnassignedUnit", "Tester")
        # Create a valid submitted CE on a Sold booklet so we have a real CE name
        # to use as triggering_consumption_entry link target in _build_and_insert_discrepancy.
        _, _, _sold_booklet, sold_coupons = make_sold_booklet_ready_for_consumption(
            customer_name="UnassignedUnit-SoldCustomer",
            employee_name="UnassignedUnit-BaseEmp",
        )
        base_ce = frappe.get_doc({
            "doctype": "Purisol Coupon Consumption Entry",
            "posting_date": frappe.utils.today(),
            "posting_time": frappe.utils.nowtime(),
            "delivery_man": self.emp.name,
            "coupons": [{"coupon": sold_coupons[0]}],
        })
        base_ce.insert(ignore_permissions=True)
        base_ce.submit()
        self.base_ce_name = base_ce.name

    def _fake_entry(self, coupon_names):
        return SimpleNamespace(
            name=self.base_ce_name,
            delivery_man=self.emp.name,
            posting_date=frappe.utils.today(),
            coupons=[SimpleNamespace(coupon=c) for c in coupon_names],
        )

    def _insert_coupon(self, booklet_name, page_number=1):
        coupon = frappe.get_doc({
            "doctype": "Purisol Coupon",
            "booklet": booklet_name,
            "page_number": page_number,
            "status": "Available",
            "coupon_number": _next_coupon_number(),
        })
        coupon.insert(ignore_permissions=True)
        return coupon

    def test_unassigned_detection_in_stock_booklet(self):
        """Coupon from an In Stock booklet → one Unassigned Booklet discrepancy, customer null."""
        booklet = make_booklet_in_stock()
        coupon = self._insert_coupon(booklet.name, page_number=1)
        entry = self._fake_entry([coupon.name])

        result = _detect_unassigned_booklets(entry)

        self.assertEqual(len(result), 1)
        disc = frappe.get_doc("Purisol Coupon Discrepancy", result[0])
        self.assertEqual(disc.discrepancy_type, "Unassigned Booklet")
        self.assertEqual(disc.status, "Open")
        self.assertEqual(disc.booklet, booklet.name)
        self.assertIsNone(disc.customer)
        self.assertEqual(len(disc.affected_coupons), 1)
        self.assertEqual(disc.affected_coupons[0].coupon, coupon.name)

    def test_unassigned_detection_in_custody_booklet(self):
        """Coupon from an In Custody booklet → discrepancy created (rule is 'not Sold')."""
        booklet = make_booklet_in_stock()
        submit_assign([booklet.name], to_delivery_man=self.emp.name)
        coupon = self._insert_coupon(booklet.name, page_number=1)
        entry = self._fake_entry([coupon.name])

        result = _detect_unassigned_booklets(entry)

        self.assertEqual(len(result), 1)
        disc = frappe.get_doc("Purisol Coupon Discrepancy", result[0])
        self.assertEqual(disc.discrepancy_type, "Unassigned Booklet")
        self.assertIsNone(disc.customer)

    def test_unassigned_detection_no_discrepancy_when_sold(self):
        """Coupon from a Sold booklet → no discrepancy."""
        _, _, _booklet_name, sold_coupons = make_sold_booklet_ready_for_consumption(
            customer_name="UnassignedUnit-SoldOnly",
            employee_name="UnassignedUnit-SoldEmp",
        )
        # Pick a coupon that wasn't consumed in setUp (index 1+)
        entry = self._fake_entry([sold_coupons[1]])

        result = _detect_unassigned_booklets(entry)

        self.assertEqual(result, [])

    def test_unassigned_detection_three_coupons_three_discrepancies(self):
        """Three coupons from the same In Stock booklet → three distinct discrepancies."""
        booklet = make_booklet_in_stock()
        coupons = [self._insert_coupon(booklet.name, page_number=p) for p in (1, 2, 3)]
        entry = self._fake_entry([c.name for c in coupons])

        result = _detect_unassigned_booklets(entry)

        self.assertEqual(len(result), 3)
        for disc_name in result:
            disc = frappe.get_doc("Purisol Coupon Discrepancy", disc_name)
            self.assertEqual(disc.discrepancy_type, "Unassigned Booklet")
            self.assertEqual(len(disc.affected_coupons), 1)
        coupon_names_in_discs = {
            frappe.get_doc("Purisol Coupon Discrepancy", n).affected_coupons[0].coupon
            for n in result
        }
        self.assertEqual(coupon_names_in_discs, {c.name for c in coupons})


# ---------------------------------------------------------------------------
# T031 — detect_for_entry no-mutation guarantee (contracts §2.2, FR-021)
# ---------------------------------------------------------------------------


class TestDetectionNoMutation(FrappeTestCase):
    """detect_for_entry must only insert new Discrepancy records; it must not
    modify any existing Coupon, Booklet, or Consumption Entry record."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_no_mutation_of_source_records(self):
        emp = make_employee("NoMutate", "Tester")
        # In Stock booklet + one coupon — detection will fire for this coupon.
        booklet = make_booklet_in_stock()
        coupon = frappe.get_doc({
            "doctype": "Purisol Coupon",
            "booklet": booklet.name,
            "page_number": 1,
            "status": "Available",
            "coupon_number": _next_coupon_number(),
        })
        coupon.insert(ignore_permissions=True)

        # Base CE on a Sold booklet supplies a valid triggering_consumption_entry link.
        _, _, _sold_booklet, sold_coupons = make_sold_booklet_ready_for_consumption(
            customer_name="NoMutate-Customer",
            employee_name="NoMutate-Emp",
        )
        base_ce = frappe.get_doc({
            "doctype": "Purisol Coupon Consumption Entry",
            "posting_date": frappe.utils.today(),
            "posting_time": frappe.utils.nowtime(),
            "delivery_man": emp.name,
            "coupons": [{"coupon": sold_coupons[0]}],
        })
        base_ce.insert(ignore_permissions=True)
        base_ce.submit()

        # Snapshot modified timestamps BEFORE calling detect_for_entry.
        ce_modified = frappe.db.get_value(
            "Purisol Coupon Consumption Entry", base_ce.name, "modified"
        )
        coupon_modified = frappe.db.get_value("Purisol Coupon", coupon.name, "modified")
        booklet_modified = frappe.db.get_value("Purisol Coupon Booklet", booklet.name, "modified")

        fake_entry = SimpleNamespace(
            name=base_ce.name,
            delivery_man=emp.name,
            posting_date=frappe.utils.today(),
            coupons=[SimpleNamespace(coupon=coupon.name)],
        )
        detect_for_entry(fake_entry)

        self.assertEqual(
            frappe.db.get_value("Purisol Coupon Consumption Entry", base_ce.name, "modified"),
            ce_modified,
            "detect_for_entry must not modify the triggering Consumption Entry",
        )
        self.assertEqual(
            frappe.db.get_value("Purisol Coupon", coupon.name, "modified"),
            coupon_modified,
            "detect_for_entry must not modify any Coupon record",
        )
        self.assertEqual(
            frappe.db.get_value("Purisol Coupon Booklet", booklet.name, "modified"),
            booklet_modified,
            "detect_for_entry must not modify any Booklet record",
        )


# ---------------------------------------------------------------------------
# T048 — US6 related_delivery_men population invariants
# ---------------------------------------------------------------------------


class TestUS6RelatedDeliveryMenInvariants(FrappeTestCase):
    """US6: verify related_delivery_men auto-population rules (FR-007, SC-011)."""

    def setUp(self):
        frappe.set_user("Administrator")

    def _new_disc(self, booklet_name):
        doc = frappe.new_doc("Purisol Coupon Discrepancy")
        doc.discrepancy_type = "Missing Coupons"
        doc.status = "Open"
        doc.booklet = booklet_name
        return doc

    def test_related_men_custody_only_when_in_custody(self):
        """In-Custody booklet → Custody Holder row present; Sold booklet → absent."""
        emp = make_employee("US6Cust", "Inv1")
        booklet = make_booklet_in_stock()
        submit_assign([booklet.name], to_delivery_man=emp.name)
        booklet_doc = frappe.get_doc("Purisol Coupon Booklet", booklet.name)
        trigger = SimpleNamespace(
            name="FAKE-US6-A",
            delivery_man=emp.name,
            posting_date=frappe.utils.today(),
        )
        disc = self._new_disc(booklet.name)
        _auto_populate_related_delivery_men(disc, trigger, booklet_doc)
        roles = {r.role for r in disc.related_delivery_men}
        self.assertIn("Custody Holder", roles)

    def test_related_men_30day_window_excludes_older_entries(self):
        """Entries older than 30 days are excluded from adjacency window (FR-007)."""
        emp_old = make_employee("US6Old", "Inv2")
        emp_trigger = make_employee("US6Trig", "Inv2")
        booklet = make_booklet_in_stock()
        coupon = frappe.get_doc({
            "doctype": "Purisol Coupon",
            "booklet": booklet.name,
            "page_number": 3,
            "status": "Available",
            "coupon_number": _next_coupon_number(),
        })
        coupon.insert(ignore_permissions=True)
        old_entry = frappe.get_doc({
            "doctype": "Purisol Coupon Consumption Entry",
            "posting_date": frappe.utils.add_days(frappe.utils.today(), -45),
            "posting_time": frappe.utils.nowtime(),
            "delivery_man": emp_old.name,
            "coupons": [{"coupon": coupon.name}],
        })
        old_entry.insert(ignore_permissions=True)
        old_entry.submit()

        booklet_doc = frappe.get_doc("Purisol Coupon Booklet", booklet.name)
        trigger = SimpleNamespace(
            name="FAKE-US6-B",
            delivery_man=emp_trigger.name,
            posting_date=frappe.utils.today(),
        )
        disc = self._new_disc(booklet.name)
        _auto_populate_related_delivery_men(disc, trigger, booklet_doc)
        dms = [r.delivery_man for r in disc.related_delivery_men]
        self.assertNotIn(emp_old.name, dms)

    def test_related_men_includes_triggering_delivery_man_when_sole_touchpoint(self):
        """When triggering delivery_man is the only touchpoint, they still appear (research §4)."""
        emp = make_employee("US6Sole", "Inv3")
        booklet = make_booklet_in_stock()
        booklet_doc = frappe.get_doc("Purisol Coupon Booklet", booklet.name)
        trigger = SimpleNamespace(
            name="FAKE-US6-C",
            delivery_man=emp.name,
            posting_date=frappe.utils.today(),
        )
        disc = self._new_disc(booklet.name)
        _auto_populate_related_delivery_men(disc, trigger, booklet_doc)
        dms = [r.delivery_man for r in disc.related_delivery_men]
        self.assertIn(emp.name, dms)
