import frappe
from frappe import _


def validate_booklet_lines(doc, method=None):
    if not any(getattr(it, "purisol_booklet", None) for it in doc.items):
        return

    coupon_item = frappe.db.get_single_value("Purisol Settings", "coupon_item")
    seen_booklets: set[str] = set()

    for line in doc.items:
        booklet_name = getattr(line, "purisol_booklet", None)
        if not booklet_name:
            continue

        # V1: booklet must exist
        if not frappe.db.exists("Purisol Coupon Booklet", booklet_name):
            frappe.throw(_("Booklet {0} does not exist — broken reference.").format(booklet_name))

        # V2: item_code must equal coupon_item
        if line.item_code != coupon_item:
            frappe.throw(
                _("Booklet {0} cannot be sold under item_code {1}.").format(booklet_name, line.item_code)
            )

        # V3: booklet status must be In Stock or In Custody
        status = frappe.db.get_value("Purisol Coupon Booklet", booklet_name, "status")
        if status not in ("In Stock", "In Custody"):
            frappe.throw(
                _("Booklet {0} cannot be sold — current status: {1}.").format(booklet_name, status)
            )

        # V4: no duplicate booklets across lines
        if booklet_name in seen_booklets:
            frappe.throw(
                _("Booklet {0} appears on more than one line of this invoice.").format(booklet_name)
            )
        seen_booklets.add(booklet_name)

        # V5: qty must be 1
        if line.qty != 1:
            frappe.throw(_("Booklet lines must have quantity 1."))


def mark_booklets_sold(doc, method=None):
    if not any(getattr(it, "purisol_booklet", None) for it in doc.items):
        return

    sold_datetime = frappe.utils.get_datetime(
        f"{doc.posting_date} {doc.posting_time or '00:00:00'}"
    )

    for line in doc.items:
        booklet_name = getattr(line, "purisol_booklet", None)
        if not booklet_name:
            continue

        booklet = frappe.get_doc("Purisol Coupon Booklet", booklet_name)
        booklet.db_set(
            {
                "status": "Sold",
                "customer": doc.customer,
                "sold_on": sold_datetime,
                "sales_invoice": doc.name,
                "current_delivery_man": None,
            },
            update_modified=True,
            notify=True,
        )
        booklet.add_comment("Info", _("Sold via {0}").format(doc.name))


def reverse_booklets_sale(doc, method=None):
    if not any(getattr(it, "purisol_booklet", None) for it in doc.items):
        return

    booklet_names = [
        getattr(line, "purisol_booklet", None)
        for line in doc.items
        if getattr(line, "purisol_booklet", None)
    ]

    blocked = []
    for booklet_name in booklet_names:
        consumed_count = frappe.db.count(
            "Purisol Coupon",
            filters={"booklet": booklet_name, "status": "Consumed"},
        )
        if consumed_count > 0:
            blocked.append(booklet_name)

    if blocked:
        frappe.throw(
            _(
                "Cannot cancel — coupons have been consumed on: {0}. "
                "The only correction path is a financial adjustment (outside Phase 3 scope)."
            ).format(", ".join(blocked))
        )

    for booklet_name in booklet_names:
        booklet = frappe.get_doc("Purisol Coupon Booklet", booklet_name)
        booklet.db_set(
            {
                "status": "In Stock",
                "customer": None,
                "sold_on": None,
                "sales_invoice": None,
            },
            update_modified=True,
            notify=True,
        )
        booklet.add_comment("Info", _("Sale reversed — invoice {0} cancelled.").format(doc.name))


def guard_trash(doc, method=None):
    referencing = frappe.get_all(
        "Purisol Coupon Booklet",
        filters={"sales_invoice": doc.name},
        pluck="name",
    )
    if referencing:
        frappe.throw(
            _("Cannot delete — booklets still reference this invoice. Cancel the invoice first.")
        )
