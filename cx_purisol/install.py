import frappe

_PHASE4_DOCTYPES = [
    ("cx_purisol", "purisol_coupon_consumption_item"),
    ("cx_purisol", "purisol_coupon_discrepancy_item"),
    ("cx_purisol", "purisol_coupon_consumption_entry"),
]


def before_tests():
    for module, dt in _PHASE4_DOCTYPES:
        frappe.reload_doc(module, "doctype", dt, force=True)

    # Ensure the child-table columns exist (reload_doc may skip ALTER on cached schemas)
    _ensure_column("Purisol Coupon Consumption Item", "customer", "varchar(140)")
    _ensure_column("Purisol Coupon Consumption Item", "booklet", "varchar(140)")

    frappe.db.commit()


def _ensure_column(doctype, fieldname, col_type):
    table = f"tab{doctype}"
    existing = [r[0] for r in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")]
    if fieldname not in existing:
        frappe.db.sql(f"ALTER TABLE `{table}` ADD COLUMN `{fieldname}` {col_type}")
