import frappe

_PHASE4_DOCTYPES = [
    ("cx_purisol", "purisol_coupon_consumption_item"),
    ("cx_purisol", "purisol_coupon_discrepancy_item"),
    ("cx_purisol", "purisol_coupon_consumption_entry"),
]

_EMPLOYEE_LINK_TITLE_SETTERS = [
    {
        "property": "title_field",
        "value": "employee_name",
        "property_type": "Data",
    },
    {
        "property": "show_title_field_in_link",
        "value": "1",
        "property_type": "Check",
    },
]
_APP_MODULE = "Cx Purisol"


def after_install():
    ensure_employee_link_title_setters()


def before_uninstall():
    remove_employee_link_title_setters()


def ensure_employee_link_title_setters():
    """Make Employee link fields display `employee_name` alongside the ID.

    Idempotent: re-running updates the value in place. Ties the Property Setters
    to this app's module so `bench uninstall-app` (and the paired
    `before_uninstall` hook) can revert the customization cleanly.
    """
    for spec in _EMPLOYEE_LINK_TITLE_SETTERS:
        name = f"Employee-main-{spec['property']}"
        if frappe.db.exists("Property Setter", name):
            ps = frappe.get_doc("Property Setter", name)
            ps.value = spec["value"]
            ps.module = _APP_MODULE
            ps.is_system_generated = 0
            ps.save(ignore_permissions=True)
        else:
            frappe.get_doc(
                {
                    "doctype": "Property Setter",
                    "doctype_or_field": "DocType",
                    "doc_type": "Employee",
                    "field_name": None,
                    "property": spec["property"],
                    "value": spec["value"],
                    "property_type": spec["property_type"],
                    "module": _APP_MODULE,
                    "is_system_generated": 0,
                }
            ).insert(ignore_permissions=True)

    frappe.clear_cache(doctype="Employee")


def remove_employee_link_title_setters():
    """Reverse of `ensure_employee_link_title_setters`. Safe to re-run."""
    for spec in _EMPLOYEE_LINK_TITLE_SETTERS:
        name = f"Employee-main-{spec['property']}"
        if frappe.db.exists("Property Setter", name):
            frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)

    frappe.clear_cache(doctype="Employee")


def before_tests():
    for module, dt in _PHASE4_DOCTYPES:
        frappe.reload_doc(module, "doctype", dt, force=True)

    # Ensure the child-table columns exist (reload_doc may skip ALTER on cached schemas)
    _ensure_column("Purisol Coupon Consumption Item", "customer", "varchar(140)")
    _ensure_column("Purisol Coupon Consumption Item", "booklet", "varchar(140)")

    ensure_employee_link_title_setters()

    frappe.db.commit()


def _ensure_column(doctype, fieldname, col_type):
    table = f"tab{doctype}"
    existing = [r[0] for r in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")]
    if fieldname not in existing:
        frappe.db.sql(f"ALTER TABLE `{table}` ADD COLUMN `{fieldname}` {col_type}")
