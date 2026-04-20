import frappe


def execute(filters=None):
    filters = filters or {}

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    delivery_man = filters.get("delivery_man")

    columns = [
        {"fieldname": "posting_date", "label": frappe._("Date"), "fieldtype": "Date", "width": 120},
        {"fieldname": "delivery_man", "label": frappe._("Delivery Man"), "fieldtype": "Link",
         "options": "Employee", "width": 200},
        {"fieldname": "coupons_submitted", "label": frappe._("Coupons Submitted"), "fieldtype": "Int", "width": 140},
        {"fieldname": "booklets_touched", "label": frappe._("Booklets Touched"), "fieldtype": "Int", "width": 140},
        {"fieldname": "discrepancies_count", "label": frappe._("Discrepancies"), "fieldtype": "Int", "width": 120},
        {"fieldname": "discrepancy_total", "label": frappe._("Discrepancy Total"), "fieldtype": "Currency", "width": 150},
    ]

    date_filter = ""
    if from_date:
        date_filter += " AND cce.posting_date >= %(from_date)s"
    if to_date:
        date_filter += " AND cce.posting_date <= %(to_date)s"
    dm_filter = " AND cce.delivery_man = %(delivery_man)s" if delivery_man else ""

    sql_params = {"from_date": from_date, "to_date": to_date, "delivery_man": delivery_man}

    coupons_rows = frappe.db.sql(
        f"""
        SELECT cce.posting_date, cce.delivery_man, COUNT(*) AS n
        FROM `tabPurisol Coupon Consumption Item` ci
        JOIN `tabPurisol Coupon Consumption Entry` cce ON cce.name = ci.parent
        WHERE cce.docstatus = 1{date_filter}{dm_filter}
        GROUP BY cce.posting_date, cce.delivery_man
        """,
        sql_params,
        as_dict=True,
    )

    booklets_rows = frappe.db.sql(
        f"""
        SELECT cce.posting_date, cce.delivery_man, COUNT(DISTINCT ci.booklet) AS n
        FROM `tabPurisol Coupon Consumption Item` ci
        JOIN `tabPurisol Coupon Consumption Entry` cce ON cce.name = ci.parent
        WHERE cce.docstatus = 1{date_filter}{dm_filter}
        GROUP BY cce.posting_date, cce.delivery_man
        """,
        sql_params,
        as_dict=True,
    )

    # Count all non-cancelled discrepancies (docstatus 0=Open, 1=Resolved) per FR-010
    # "discrepancies opened" includes unresolved ones so the admin sees today's activity
    disc_rows = frappe.db.sql(
        f"""
        SELECT cce.posting_date, cce.delivery_man, COUNT(*) AS n,
               COALESCE(SUM(d.estimated_amount), 0) AS total
        FROM `tabPurisol Coupon Discrepancy` d
        JOIN `tabPurisol Coupon Consumption Entry` cce
            ON cce.name = d.triggering_consumption_entry
        WHERE d.docstatus IN (0, 1) AND cce.docstatus = 1{date_filter}{dm_filter}
        GROUP BY cce.posting_date, cce.delivery_man
        """,
        sql_params,
        as_dict=True,
    )

    merged: dict[tuple, dict] = {}

    def _key(row):
        return (str(row["posting_date"]), row["delivery_man"])

    def _ensure(key, posting_date, delivery_man):
        if key not in merged:
            merged[key] = {
                "posting_date": posting_date,
                "delivery_man": delivery_man,
                "coupons_submitted": 0,
                "booklets_touched": 0,
                "discrepancies_count": 0,
                "discrepancy_total": 0,
            }

    for row in coupons_rows:
        k = _key(row)
        _ensure(k, row["posting_date"], row["delivery_man"])
        merged[k]["coupons_submitted"] = row["n"]

    for row in booklets_rows:
        k = _key(row)
        _ensure(k, row["posting_date"], row["delivery_man"])
        merged[k]["booklets_touched"] = row["n"]

    for row in disc_rows:
        k = _key(row)
        _ensure(k, row["posting_date"], row["delivery_man"])
        merged[k]["discrepancies_count"] = row["n"]
        merged[k]["discrepancy_total"] = row["total"]

    data = sorted(merged.values(), key=lambda r: (str(r["posting_date"]), r["delivery_man"]))
    return columns, data
