import json

import frappe
from frappe import _


def _resolve_price_list(customer: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    customer_default = frappe.db.get_value("Customer", customer, "default_price_list")
    if customer_default:
        return customer_default
    settings_default = frappe.db.get_single_value("Purisol Settings", "default_price_list")
    if settings_default:
        return settings_default
    frappe.throw(
        _(
            "No Price List could be resolved for this sale. "
            "Configure a default_price_list in Purisol Settings or pick one on the workflow."
        )
    )


@frappe.whitelist()
def purisol_create_sales_invoice_for_booklets(
    customer: str,
    booklets,
    price_list=None,
) -> dict:
    frappe.only_for("Purisol Administrator")

    coupon_item = frappe.db.get_single_value("Purisol Settings", "coupon_item")
    if not coupon_item:
        frappe.throw(_("Configure coupon_item in Purisol Settings before selling."))

    if isinstance(booklets, str):
        booklets = json.loads(booklets)

    if not booklets:
        frappe.throw(_("Select at least one booklet to sell."))

    seen: set[str] = set()
    for name in booklets:
        if name in seen:
            frappe.throw(_("Booklet {0} selected more than once.").format(name))
        seen.add(name)

    for name in booklets:
        status = frappe.db.get_value("Purisol Coupon Booklet", name, "status")
        if not status:
            frappe.throw(_("Booklet {0} cannot be sold — status is {1}.").format(name, "unknown"))
        if status not in ("In Stock", "In Custody"):
            frappe.throw(_("Booklet {0} cannot be sold — status is {1}.").format(name, status))

    resolved_pl = _resolve_price_list(customer, price_list)

    inv = frappe.new_doc("Sales Invoice")
    inv.customer = customer
    inv.selling_price_list = resolved_pl

    for name in booklets:
        inv.append("items", {
            "item_code": coupon_item,
            "qty": 1,
            "purisol_booklet": name,
        })

    inv.set_missing_values()
    inv.calculate_taxes_and_totals()
    inv.insert(ignore_permissions=False)

    return {"name": inv.name}


@frappe.whitelist()
def get_coupon_item_code():
    return frappe.db.get_single_value("Purisol Settings", "coupon_item")
