import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "posting_date", "fieldtype": "Date", "label": frappe._("Sale Date"), "width": 120},
        {"fieldname": "booklet", "fieldtype": "Link", "label": frappe._("Booklet"),
         "options": "Purisol Coupon Booklet", "width": 150},
        {"fieldname": "customer", "fieldtype": "Link", "label": frappe._("Customer"),
         "options": "Customer", "width": 180},
        {"fieldname": "sales_invoice", "fieldtype": "Link", "label": frappe._("Invoice"),
         "options": "Sales Invoice", "width": 180},
        {"fieldname": "amount", "fieldtype": "Currency", "label": frappe._("Amount"), "width": 120},
        {"fieldname": "status", "fieldtype": "Data", "label": frappe._("Invoice Status"), "width": 130},
    ]

    params = {
        "from_date": filters.get("from_date") or None,
        "to_date": filters.get("to_date") or None,
        "customer": filters.get("customer") or None,
        "price_list": filters.get("price_list") or None,
    }

    data = frappe.db.sql(
        """
        SELECT
            si.posting_date,
            sii.purisol_booklet AS booklet,
            si.customer,
            si.name AS sales_invoice,
            sii.amount,
            si.status
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1
          AND sii.purisol_booklet IS NOT NULL
          AND (%(from_date)s IS NULL OR si.posting_date >= %(from_date)s)
          AND (%(to_date)s IS NULL OR si.posting_date <= %(to_date)s)
          AND (%(customer)s IS NULL OR si.customer = %(customer)s)
          AND (%(price_list)s IS NULL OR si.selling_price_list = %(price_list)s)
        ORDER BY si.posting_date DESC, si.name, sii.idx
        """,
        params,
        as_dict=True,
    )

    return columns, data
