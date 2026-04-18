import frappe


def execute():
    frappe.clear_cache(doctype="Purisol Coupon Booklet")
    frappe.clear_cache(doctype="Purisol Custody Entry")
    frappe.clear_cache(doctype="Purisol Custody Entry Booklet")
