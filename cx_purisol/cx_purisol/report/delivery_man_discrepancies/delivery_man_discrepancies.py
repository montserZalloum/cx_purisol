import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "discrepancy", "fieldtype": "Link", "label": frappe._("Discrepancy ID"),
         "options": "Purisol Coupon Discrepancy", "width": 220},
        {"fieldname": "opened_on", "fieldtype": "Datetime", "label": frappe._("Opened On"), "width": 160},
        {"fieldname": "discrepancy_type", "fieldtype": "Data", "label": frappe._("Type"), "width": 160},
        {"fieldname": "booklet", "fieldtype": "Link", "label": frappe._("Booklet"),
         "options": "Purisol Coupon Booklet", "width": 150},
        {"fieldname": "coupons_count", "fieldtype": "Int", "label": frappe._("Coupons"), "width": 90},
        {"fieldname": "estimated_amount", "fieldtype": "Currency", "label": frappe._("Amount"), "width": 120},
        {"fieldname": "status", "fieldtype": "Data", "label": frappe._("Status"), "width": 200},
        {"fieldname": "resolution_action", "fieldtype": "Data", "label": frappe._("Resolution"), "width": 180},
        {"fieldname": "delivery_man", "fieldtype": "Link", "label": frappe._("Delivery Man"),
         "options": "Employee", "width": 180},
    ]

    params = {
        "from_date": filters.get("from_date") or None,
        "to_date": filters.get("to_date") or None,
        "delivery_man": filters.get("delivery_man") or None,
        "status": filters.get("status") or None,
    }

    data = frappe.db.sql(
        """
        SELECT
            d.name AS discrepancy,
            d.opened_on,
            d.discrepancy_type,
            d.booklet,
            (SELECT COUNT(*) FROM `tabPurisol Coupon Discrepancy Coupon` dc WHERE dc.parent = d.name) AS coupons_count,
            d.estimated_amount,
            d.status,
            d.resolution_action,
            cce.delivery_man
        FROM `tabPurisol Coupon Discrepancy` d
        LEFT JOIN `tabPurisol Coupon Consumption Entry` cce ON cce.name = d.triggering_consumption_entry
        WHERE d.docstatus = 1
          AND (cce.name IS NULL OR cce.docstatus = 1)
          AND (%(from_date)s IS NULL OR DATE(d.opened_on) >= %(from_date)s)
          AND (%(to_date)s IS NULL OR DATE(d.opened_on) <= %(to_date)s)
          AND (%(delivery_man)s IS NULL OR cce.delivery_man = %(delivery_man)s)
          AND (%(status)s IS NULL OR d.status = %(status)s)
        ORDER BY d.opened_on DESC
        """,
        params,
        as_dict=True,
    )

    return columns, data
