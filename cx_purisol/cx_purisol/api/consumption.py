import frappe
from frappe import _


@frappe.whitelist()
def list_available_coupons(booklet):
    frappe.only_for("Purisol Administrator")
    if not booklet:
        frappe.throw(_("Booklet name is required."))
    return frappe.get_all(
        "Purisol Coupon",
        filters={"booklet": booklet, "status": "Available"},
        fields=["name as coupon", "page_number"],
        order_by="page_number asc",
    )


@frappe.whitelist()
def resolve_coupons(coupon_numbers):
    frappe.only_for("Purisol Administrator")
    filtered = [n.strip() for n in (coupon_numbers or []) if n.strip()]
    if not filtered:
        frappe.throw(_("No coupon numbers to resolve."))

    coupon_rows = frappe.get_all(
        "Purisol Coupon",
        filters={"name": ["in", filtered]},
        fields=["name", "booklet"],
    )
    coupon_map = {r["name"]: r["booklet"] for r in coupon_rows}

    booklet_names = list({r["booklet"] for r in coupon_rows if r["booklet"]})
    booklet_rows = frappe.get_all(
        "Purisol Coupon Booklet",
        filters={"name": ["in", booklet_names]},
        fields=["name", "customer"],
    ) if booklet_names else []
    booklet_map = {r["name"]: r["customer"] for r in booklet_rows}

    resolved = []
    unresolved = []
    for n in filtered:
        if n in coupon_map:
            b = coupon_map[n]
            resolved.append({"coupon": n, "booklet": b, "customer": booklet_map.get(b, "")})
        else:
            unresolved.append(n)

    return {"resolved": resolved, "unresolved": unresolved}
