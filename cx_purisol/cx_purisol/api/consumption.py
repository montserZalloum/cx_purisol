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
    if isinstance(coupon_numbers, str):
        coupon_numbers = frappe.parse_json(coupon_numbers)
    filtered = [n.strip() for n in (coupon_numbers or []) if isinstance(n, str) and n.strip()]
    if not filtered:
        frappe.throw(_("No coupon numbers to resolve."))

    coupon_rows = frappe.get_all(
        "Purisol Coupon",
        filters={"name": ["in", filtered]},
        fields=["name", "booklet", "status"],
    )
    coupon_map = {r["name"]: r for r in coupon_rows}

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
            row = coupon_map[n]
            b = row["booklet"]
            resolved.append({
                "coupon": n,
                "booklet": b,
                "customer": booklet_map.get(b, ""),
                "status": row["status"],
            })
        else:
            unresolved.append(n)

    return {"resolved": resolved, "unresolved": unresolved}
