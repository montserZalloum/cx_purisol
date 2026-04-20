from cx_purisol.install import ensure_employee_link_title_setters


def execute():
    """Show `employee_name` alongside the Employee ID in link fields.

    Creates two Property Setters (`title_field`, `show_title_field_in_link`)
    on the Employee DocType, tied to this app's module so uninstall reverts
    them via `before_uninstall`.
    """
    ensure_employee_link_title_setters()
