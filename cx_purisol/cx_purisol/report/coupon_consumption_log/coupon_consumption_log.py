import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "consumed_on", "fieldtype": "Datetime", "label": frappe._("Consumed On"), "width": 160},
        {"fieldname": "coupon", "fieldtype": "Link", "label": frappe._("Coupon"),
         "options": "Purisol Coupon", "width": 130},
        {"fieldname": "booklet", "fieldtype": "Link", "label": frappe._("Booklet"),
         "options": "Purisol Coupon Booklet", "width": 150},
        {"fieldname": "customer", "fieldtype": "Link", "label": frappe._("Customer"),
         "options": "Customer", "width": 150},
        {"fieldname": "delivery_man", "fieldtype": "Link", "label": frappe._("Delivery Man"),
         "options": "Employee", "width": 180},
        {"fieldname": "consumption_entry", "fieldtype": "Link", "label": frappe._("Entry"),
         "options": "Purisol Coupon Consumption Entry", "width": 160},
    ]

    params = {
        "from_date": filters.get("from_date") or None,
        "to_date": filters.get("to_date") or None,
        "delivery_man": filters.get("delivery_man") or None,
        "customer": filters.get("customer") or None,
        "booklet": filters.get("booklet") or None,
    }

    data = frappe.db.sql(
        """
        SELECT
            c.consumed_on,
            c.name AS coupon,
            c.booklet,
            b.customer,
            c.consumed_by_delivery_man AS delivery_man,
            c.consumption_entry
        FROM `tabPurisol Coupon` c
        JOIN `tabPurisol Coupon Booklet` b ON b.name = c.booklet
        JOIN `tabPurisol Coupon Consumption Entry` cce ON cce.name = c.consumption_entry
        WHERE c.status = 'Consumed'
          AND cce.docstatus = 1
          AND (%(from_date)s IS NULL OR DATE(c.consumed_on) >= %(from_date)s)
          AND (%(to_date)s IS NULL OR DATE(c.consumed_on) <= %(to_date)s)
          AND (%(delivery_man)s IS NULL OR c.consumed_by_delivery_man = %(delivery_man)s)
          AND (%(customer)s IS NULL OR b.customer = %(customer)s)
          AND (%(booklet)s IS NULL OR c.booklet = %(booklet)s)
        ORDER BY c.consumed_on DESC, c.name
        """,
        params,
        as_dict=True,
    )

    return columns, data
