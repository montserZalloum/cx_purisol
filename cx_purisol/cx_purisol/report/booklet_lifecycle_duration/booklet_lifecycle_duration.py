import frappe


def execute(filters=None):
    columns = [
        {
            "fieldname": "avg_generation_to_first_sale",
            "label": frappe._("Avg Days: Generation \u2192 Sale"),
            "fieldtype": "Float",
            "width": 220,
        },
        {
            "fieldname": "avg_sale_to_depletion",
            "label": frappe._("Avg Days: Sale \u2192 Depletion"),
            "fieldtype": "Float",
            "width": 220,
        },
        {
            "fieldname": "avg_full_lifetime",
            "label": frappe._("Avg Days: Generation \u2192 Depletion"),
            "fieldtype": "Float",
            "width": 240,
        },
    ]

    row = frappe.db.sql(
        """
        SELECT
            ROUND(AVG(CASE WHEN b.status IN ('Sold', 'Depleted') AND b.sold_on IS NOT NULL
                          THEN DATEDIFF(b.sold_on, b.creation) END), 1) AS avg_generation_to_first_sale,
            ROUND(AVG(CASE WHEN b.status = 'Depleted'
                          THEN DATEDIFF(b.depleted_on, b.sold_on) END), 1) AS avg_sale_to_depletion,
            ROUND(AVG(CASE WHEN b.status = 'Depleted'
                          THEN DATEDIFF(b.depleted_on, b.creation) END), 1) AS avg_full_lifetime
        FROM `tabPurisol Coupon Booklet` b
        """,
        as_dict=True,
    )

    data = [dict(row[0])] if row else [
        {"avg_generation_to_first_sale": None, "avg_sale_to_depletion": None, "avg_full_lifetime": None}
    ]
    return columns, data
