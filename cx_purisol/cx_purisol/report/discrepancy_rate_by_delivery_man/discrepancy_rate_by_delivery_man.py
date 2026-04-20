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
            "fieldname": "coupons_submitted",
            "label": frappe._("Coupons Submitted"),
            "fieldtype": "Int",
            "width": 140,
        },
        {
            "fieldname": "discrepancies_count",
            "label": frappe._("Discrepancies"),
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "fieldname": "discrepancy_rate",
            "label": frappe._("Rate (%)"),
            "fieldtype": "Percent",
            "width": 110,
        },
        {
            "fieldname": "discrepancy_total",
            "label": frappe._("Discrepancy Total"),
            "fieldtype": "Currency",
            "width": 150,
        },
    ]

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    date_filter = ""
    if from_date:
        date_filter += " AND cce.posting_date >= %(from_date)s"
    if to_date:
        date_filter += " AND cce.posting_date <= %(to_date)s"

    sql_params = {"from_date": from_date, "to_date": to_date}

    coupons_rows = frappe.db.sql(
        f"""
        SELECT cce.delivery_man, COUNT(*) AS n
        FROM `tabPurisol Coupon Consumption Item` ci
        JOIN `tabPurisol Coupon Consumption Entry` cce ON cce.name = ci.parent
        WHERE cce.docstatus = 1{date_filter}
        GROUP BY cce.delivery_man
        """,
        sql_params,
        as_dict=True,
    )

    disc_rows = frappe.db.sql(
        f"""
        SELECT cce.delivery_man, COUNT(*) AS n,
               COALESCE(SUM(d.estimated_amount), 0) AS total
        FROM `tabPurisol Coupon Discrepancy` d
        JOIN `tabPurisol Coupon Consumption Entry` cce
            ON cce.name = d.triggering_consumption_entry
        WHERE d.docstatus = 1 AND cce.docstatus = 1{date_filter}
        GROUP BY cce.delivery_man
        """,
        sql_params,
        as_dict=True,
    )

    merged: dict[str, dict] = {}
    for row in coupons_rows:
        merged[row.delivery_man] = {
            "delivery_man": row.delivery_man,
            "coupons_submitted": int(row.n),
            "discrepancies_count": 0,
            "discrepancy_rate": 0,
            "discrepancy_total": 0,
        }

    for row in disc_rows:
        dm = row.delivery_man
        if dm in merged:
            merged[dm]["discrepancies_count"] = int(row.n)
            merged[dm]["discrepancy_total"] = float(row.total or 0)

    data = []
    for row in merged.values():
        c = row["coupons_submitted"]
        d = row["discrepancies_count"]
        row["discrepancy_rate"] = round(100 * d / c, 2) if c else 0
        data.append(row)

    data.sort(key=lambda r: (-r["discrepancy_rate"], -r["coupons_submitted"]))
    return columns, data
