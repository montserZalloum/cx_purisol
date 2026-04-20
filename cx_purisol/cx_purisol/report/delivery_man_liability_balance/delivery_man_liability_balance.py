import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {
            "fieldname": "delivery_man",
            "label": frappe._("Delivery Man"),
            "fieldtype": "Link",
            "options": "Employee",
            "width": 200,
        },
        {
            "fieldname": "delivery_man_name",
            "label": frappe._("Name"),
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "fieldname": "total_owed",
            "label": frappe._("Total Owed"),
            "fieldtype": "Currency",
            "width": 140,
        },
        {
            "fieldname": "total_paid",
            "label": frappe._("Total Paid"),
            "fieldtype": "Currency",
            "width": 140,
        },
        {
            "fieldname": "open_balance",
            "label": frappe._("Open Balance"),
            "fieldtype": "Currency",
            "width": 140,
        },
    ]

    settings = frappe.get_single("Purisol Settings")
    if not settings.employee_liability_account:
        return columns, [
            {
                "delivery_man": None,
                "delivery_man_name": frappe._(
                    "Configure employee_liability_account in Purisol Settings to enable this report"
                ),
                "total_owed": None,
                "total_paid": None,
                "open_balance": None,
            }
        ]

    delivery_man = filters.get("delivery_man")

    rows = frappe.db.sql(
        """
        SELECT delivery_man, owed, paid
        FROM (
            SELECT
                party AS delivery_man,
                SUM(debit_in_account_currency) AS owed,
                SUM(credit_in_account_currency) AS paid
            FROM `tabGL Entry`
            WHERE account = %(account)s
              AND party_type = 'Employee'
              AND is_cancelled = 0
              AND (%(delivery_man)s IS NULL OR party = %(delivery_man)s)
            GROUP BY party
        ) agg
        WHERE owed > 0 OR paid > 0
        ORDER BY (owed - paid) DESC
        """,
        {"account": settings.employee_liability_account, "delivery_man": delivery_man},
        as_dict=True,
    )

    data = []
    for row in rows:
        emp_name = (
            frappe.db.get_value("Employee", row.delivery_man, "employee_name")
            or row.delivery_man
        )
        owed = float(row.owed or 0)
        paid = float(row.paid or 0)
        data.append(
            {
                "delivery_man": row.delivery_man,
                "delivery_man_name": emp_name,
                "total_owed": owed,
                "total_paid": paid,
                "open_balance": owed - paid,
            }
        )

    return columns, data
