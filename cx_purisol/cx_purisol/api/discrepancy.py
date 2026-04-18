"""Detection service for Purisol Coupon Discrepancies.

Not whitelisted — server-side only, called from PurisolCouponConsumptionEntry.on_submit.
"""
from __future__ import annotations

import frappe
from frappe.utils import add_days, now_datetime


def detect_for_entry(entry) -> list[str]:
    """
    Run both detection rules against the just-submitted Consumption Entry.
    Returns a list of newly-created Purisol Coupon Discrepancy names, possibly empty.

    Pre: Phase-4 side effects on coupons and booklets are already committed
    to the current transaction (this is called from the end of on_submit).
    """
    return _detect_missing_coupons(entry) + _detect_unassigned_booklets(entry)


def _detect_missing_coupons(entry) -> list[str]:
    """
    For each distinct booklet in the entry, detect interior gaps in consumed coupon
    page numbers and create one Purisol Coupon Discrepancy of type 'Missing Coupons'
    per affected booklet.  Returns list of created discrepancy names.
    """
    distinct_booklets = list({row.booklet for row in entry.coupons if row.booklet})
    created: list[str] = []

    for booklet_name in distinct_booklets:
        rows = frappe.get_all(
            "Purisol Coupon",
            filters={"booklet": booklet_name},
            fields=["name", "page_number", "status"],
        )

        consumed_pages = {r["page_number"] for r in rows if r["status"] == "Consumed"}

        if len(consumed_pages) < 2:
            continue

        lo, hi = min(consumed_pages), max(consumed_pages)
        gap_pages = set(range(lo + 1, hi)) - consumed_pages

        gap_rows = [
            r for r in rows if r["page_number"] in gap_pages and r["status"] == "Available"
        ]

        if not gap_rows:
            continue

        open_names = _list_open_missing_coupon_names(booklet_name)
        new_rows = [r for r in gap_rows if r["name"] not in open_names]

        if not new_rows:
            continue

        booklet_doc = frappe.get_doc("Purisol Coupon Booklet", booklet_name)
        disc_name = _build_and_insert_discrepancy(
            discrepancy_type="Missing Coupons",
            triggering_entry=entry,
            booklet_doc=booklet_doc,
            affected_coupon_names=[r["name"] for r in new_rows],
            customer=booklet_doc.customer,
        )
        created.append(disc_name)

    return created


def _detect_unassigned_booklets(entry) -> list[str]:
    """
    For each coupon in the entry whose parent booklet status is not 'Sold', create
    one Purisol Coupon Discrepancy of type 'Unassigned Booklet' per coupon.
    Returns list of created discrepancy names.

    Rule: per-coupon, not per-booklet (research.md §5, FR-004).
    No dedup needed — each coupon may only be Consumed once per the coupon state machine.
    """
    booklet_cache: dict[str, object] = {}
    created: list[str] = []

    for row in entry.coupons:
        booklet_name = frappe.db.get_value("Purisol Coupon", row.coupon, "booklet")
        if not booklet_name:
            continue

        if booklet_name not in booklet_cache:
            booklet_cache[booklet_name] = frappe.get_doc("Purisol Coupon Booklet", booklet_name)

        booklet_doc = booklet_cache[booklet_name]

        if booklet_doc.status != "Sold":
            disc_name = _build_and_insert_discrepancy(
                discrepancy_type="Unassigned Booklet",
                triggering_entry=entry,
                booklet_doc=booklet_doc,
                affected_coupon_names=[row.coupon],
                customer=None,
            )
            created.append(disc_name)

    return created


def _auto_populate_related_delivery_men(doc, entry, booklet) -> None:
    """
    Mutate doc.related_delivery_men in-place.  Appends:
    (a) one 'Custody Holder' row if booklet.status == 'In Custody', pointing at
        the most-recent submitted Assign custody entry for this booklet; and
    (b) one 'Submitted Adjacent Coupons' row per distinct delivery man who submitted
        any Consumption Entry referencing this booklet within 30 days of
        entry.posting_date (exclusive of the triggering entry itself).
    """
    custody_holder_set: set[str] = set()

    # (a) Custody Holder row
    if booklet.status == "In Custody":
        parent_names = frappe.get_all(
            "Purisol Custody Entry Booklet",
            filters={"booklet": booklet.name, "parenttype": "Purisol Custody Entry"},
            fields=["parent"],
            pluck="parent",
        )
        if parent_names:
            assign_entries = frappe.get_all(
                "Purisol Custody Entry",
                filters={
                    "name": ["in", parent_names],
                    "entry_type": "Assign",
                    "docstatus": 1,
                },
                fields=["name", "to_delivery_man"],
                order_by="creation desc",
                limit=1,
            )
            if assign_entries:
                ae = assign_entries[0]
                doc.append(
                    "related_delivery_men",
                    {
                        "delivery_man": ae["to_delivery_man"],
                        "role": "Custody Holder",
                        "custody_entry": ae["name"],
                    },
                )
                custody_holder_set.add(ae["to_delivery_man"])

    # (b) Submitted Adjacent Coupons — 30-day window anchored to entry.posting_date
    thirty_days_ago = add_days(entry.posting_date, -30)

    item_parents = frappe.get_all(
        "Purisol Coupon Consumption Item",
        filters={"booklet": booklet.name},
        fields=["parent"],
        pluck="parent",
    )

    seen: dict[str, str] = {}
    if item_parents:
        adjacent_entries = frappe.get_all(
            "Purisol Coupon Consumption Entry",
            filters={
                "name": ["in", list(set(item_parents))],
                "docstatus": 1,
                "posting_date": [">=", thirty_days_ago],
            },
            fields=["name", "delivery_man", "posting_date"],
            order_by="posting_date desc",
        )
        for ae in adjacent_entries:
            if ae["name"] == entry.name:
                continue
            dm = ae["delivery_man"]
            if dm not in custody_holder_set and dm not in seen:
                seen[dm] = ae["name"]

    for dm, ae_name in seen.items():
        doc.append(
            "related_delivery_men",
            {
                "delivery_man": dm,
                "role": "Submitted Adjacent Coupons",
                "consumption_entry": ae_name,
            },
        )

    # Edge case: triggering delivery_man has no other touchpoint → include as sole candidate
    existing_dms = {row.delivery_man for row in doc.related_delivery_men}
    if entry.delivery_man not in existing_dms:
        doc.append(
            "related_delivery_men",
            {
                "delivery_man": entry.delivery_man,
                "role": "Submitted Adjacent Coupons",
                "consumption_entry": entry.name,
            },
        )


def _compute_estimated_amount(booklet, count: int) -> float:
    """
    Return coupon_unit_price * count using the three-tier price resolution:
    1. booklet.sales_invoice -> Sales Invoice Item rate / 20
    2. Purisol Settings.default_price_list -> Item Price for coupon_item / 20
    3. 0.0 fallback
    """
    if not count:
        return 0.0

    # Tier 1: Sales Invoice line
    if booklet.sales_invoice:
        rows = frappe.get_all(
            "Sales Invoice Item",
            filters={"parent": booklet.sales_invoice, "purisol_booklet": booklet.name},
            fields=["rate"],
            limit=1,
        )
        if rows:
            return float(rows[0]["rate"] / 20 * count)

    # Tier 2: Price list fallback
    settings = frappe.get_cached_doc("Purisol Settings")
    if settings.coupon_item and settings.default_price_list:
        rows = frappe.get_all(
            "Item Price",
            filters={
                "item_code": settings.coupon_item,
                "price_list": settings.default_price_list,
            },
            fields=["price_list_rate"],
            limit=1,
        )
        if rows:
            return float(rows[0]["price_list_rate"] / 20 * count)

    return 0.0


def _list_open_missing_coupon_names(booklet: str) -> set[str]:
    """
    Return the set of coupon names already listed in affected_coupons rows of any
    Open (status='Open', docstatus=0) Missing Coupons discrepancy for this booklet.
    Used by _detect_missing_coupons for idempotent deduplication.
    """
    open_discs = frappe.get_all(
        "Purisol Coupon Discrepancy",
        filters={
            "booklet": booklet,
            "discrepancy_type": "Missing Coupons",
            "status": "Open",
            "docstatus": 0,
        },
        fields=["name"],
        pluck="name",
    )
    if not open_discs:
        return set()

    coupon_names = frappe.get_all(
        "Purisol Coupon Discrepancy Coupon",
        filters={
            "parent": ["in", open_discs],
            "parenttype": "Purisol Coupon Discrepancy",
        },
        fields=["coupon"],
        pluck="coupon",
    )
    return set(coupon_names)


def _build_and_insert_discrepancy(
    *,
    discrepancy_type: str,
    triggering_entry,
    booklet_doc,
    affected_coupon_names: list[str],
    customer: str | None,
) -> str:
    """
    Build and insert a new draft Purisol Coupon Discrepancy.
    Returns the new document's name.
    """
    doc = frappe.new_doc("Purisol Coupon Discrepancy")
    doc.discrepancy_type = discrepancy_type
    doc.status = "Open"
    doc.opened_on = now_datetime()
    doc.triggering_consumption_entry = triggering_entry.name
    doc.booklet = booklet_doc.name
    doc.customer = customer

    for coupon_name in affected_coupon_names:
        doc.append("affected_coupons", {"coupon": coupon_name})

    _auto_populate_related_delivery_men(doc, triggering_entry, booklet_doc)
    doc.estimated_amount = _compute_estimated_amount(booklet_doc, len(affected_coupon_names))

    doc.insert(ignore_permissions=True)
    return doc.name
