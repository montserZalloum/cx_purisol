import frappe
from frappe.model.naming import make_autoname

COUPON_ITEM_CODE = "Purisol-Test-Coupon-Item"


def ensure_coupon_item():
    if frappe.db.exists("Item", COUPON_ITEM_CODE):
        return frappe.get_doc("Item", COUPON_ITEM_CODE)
    company = frappe.defaults.get_global_default("company") or "_Test Company"
    income_account = (
        frappe.db.get_value("Account", {"company": company, "account_type": "Income Account", "is_group": 0}, "name")
        or frappe.db.get_value("Account", {"company": company, "root_type": "Income", "is_group": 0}, "name")
    )
    item = frappe.get_doc({
        "doctype": "Item",
        "item_code": COUPON_ITEM_CODE,
        "item_name": "Purisol Test Coupon Booklet",
        "item_group": "All Item Groups",
        "stock_uom": "Nos",
        "is_stock_item": 0,
        "is_sales_item": 1,
        "item_defaults": [{"company": company, "income_account": income_account}] if income_account else [],
    })
    item.insert(ignore_permissions=True)
    return item


def ensure_price_list(name, currency="INR", is_selling=1):
    if frappe.db.exists("Price List", name):
        return frappe.get_doc("Price List", name)
    pl = frappe.get_doc({
        "doctype": "Price List",
        "price_list_name": name,
        "currency": currency,
        "selling": is_selling,
        "buying": 0,
        "enabled": 1,
    })
    pl.insert(ignore_permissions=True)
    return pl


def ensure_item_price(item_code, price_list, rate):
    existing = frappe.db.get_value(
        "Item Price",
        {"item_code": item_code, "price_list": price_list, "selling": 1},
        "name",
    )
    if existing:
        frappe.db.set_value("Item Price", existing, "price_list_rate", rate)
        return frappe.get_doc("Item Price", existing)
    ip = frappe.get_doc({
        "doctype": "Item Price",
        "item_code": item_code,
        "price_list": price_list,
        "price_list_rate": rate,
        "selling": 1,
        "currency": frappe.db.get_value("Price List", price_list, "currency") or "INR",
    })
    ip.insert(ignore_permissions=True)
    return ip


def ensure_customer(name, default_price_list=None):
    if frappe.db.exists("Customer", name):
        doc = frappe.get_doc("Customer", name)
        if default_price_list is not None and doc.default_price_list != default_price_list:
            doc.default_price_list = default_price_list
            doc.save(ignore_permissions=True)
        return doc
    customer = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": name,
        "customer_type": "Individual",
        "customer_group": "All Customer Groups",
        "territory": "All Territories",
        "default_price_list": default_price_list,
    })
    customer.insert(ignore_permissions=True)
    return customer


def configure_purisol_settings(coupon_item=None, default_price_list=None):
    settings = frappe.get_single("Purisol Settings")
    changed = False
    if coupon_item is not None and settings.coupon_item != coupon_item:
        settings.coupon_item = coupon_item
        changed = True
    if default_price_list is not None and settings.default_price_list != default_price_list:
        settings.default_price_list = default_price_list
        changed = True
    if changed:
        settings.save(ignore_permissions=True)


def make_employee(first_name="Test", last_name="Employee", company=None):
    company = company or frappe.defaults.get_global_default("company") or "_Test Company"
    emp = frappe.get_doc({
        "doctype": "Employee",
        "first_name": first_name,
        "last_name": last_name,
        "company": company,
        "gender": "Male",
        "date_of_birth": "1990-01-01",
        "date_of_joining": "2020-01-01",
        "status": "Active",
    })
    emp.insert(ignore_permissions=True)
    return emp


def make_booklet_in_stock(batch_id=None):
    booklet_name = make_autoname("WP-.#####")
    k = int(booklet_name.split("-")[1])
    booklet = frappe.get_doc({
        "doctype": "Purisol Coupon Booklet",
        "name": booklet_name,
        "booklet_number": booklet_name,
        "status": "In Stock",
        "first_coupon": f"CP-{(k - 1) * 20 + 1:05d}",
        "last_coupon": f"CP-{k * 20:05d}",
        "total_coupons": 20,
        "consumed_count": 0,
        "remaining_count": 20,
        "batch_id": batch_id,
    })
    booklet.flags.ignore_permissions = True
    booklet.flags.ignore_mandatory = True
    booklet.insert(ignore_permissions=True, set_name=booklet_name)
    return booklet


def make_custody_entry(entry_type, booklets, from_delivery_man=None, to_delivery_man=None):
    doc = frappe.get_doc({
        "doctype": "Purisol Custody Entry",
        "entry_type": entry_type,
        "from_delivery_man": from_delivery_man,
        "to_delivery_man": to_delivery_man,
        "booklets": [{"booklet": b} for b in booklets],
    })
    doc.insert(ignore_permissions=True)
    return doc


def submit_assign(booklets, to_delivery_man):
    entry = make_custody_entry("Assign", booklets, to_delivery_man=to_delivery_man)
    entry.submit()
    return entry


def submit_return(booklets, from_delivery_man):
    entry = make_custody_entry("Return", booklets, from_delivery_man=from_delivery_man)
    entry.submit()
    return entry


def submit_transfer(booklets, from_delivery_man, to_delivery_man):
    entry = make_custody_entry(
        "Transfer",
        booklets,
        from_delivery_man=from_delivery_man,
        to_delivery_man=to_delivery_man,
    )
    entry.submit()
    return entry


def make_sold_booklet_ready_for_consumption(
    customer_name="Acme Co.", employee_name="Ali", booklet_name=None
):
    from cx_purisol.cx_purisol.api.booklet_generation import _create_booklet_and_coupons
    from cx_purisol.cx_purisol.api.sell_booklets import purisol_create_sales_invoice_for_booklets

    item = ensure_coupon_item()
    pl = ensure_price_list("Test-Consumption-PL")
    ensure_item_price(item.name, pl.name, 100)
    customer = ensure_customer(customer_name, default_price_list=pl.name)
    configure_purisol_settings(coupon_item=item.name, default_price_list=pl.name)

    emp_doc = make_employee(employee_name)

    if booklet_name is None:
        booklet_name, _ = _create_booklet_and_coupons(batch_id=None)

    result = purisol_create_sales_invoice_for_booklets(customer.name, [booklet_name])
    si = frappe.get_doc("Sales Invoice", result["name"])
    si.submit()

    coupon_names = frappe.get_all(
        "Purisol Coupon",
        filters={"booklet": booklet_name},
        fields=["name"],
        order_by="page_number asc",
        pluck="name",
    )

    return (customer_name, emp_doc, booklet_name, coupon_names)


# ---------------------------------------------------------------------------
# Phase 5 helpers
# ---------------------------------------------------------------------------


def configure_purisol_settings_accounts(
    employee_liability=None, discrepancy_offset=None, default_cash=None
):
    """Configure the three Phase-5 account fields on Purisol Settings.

    If an argument is None, a suitable existing GL account is located automatically
    from the test company's chart of accounts.
    """
    company = frappe.defaults.get_global_default("company") or "_Test Company"

    if employee_liability is None:
        employee_liability = frappe.db.get_value(
            "Account",
            {"company": company, "account_type": "Payable", "is_group": 0},
            "name",
        ) or frappe.db.get_value(
            "Account",
            {"company": company, "root_type": "Liability", "is_group": 0},
            "name",
        )

    if discrepancy_offset is None:
        discrepancy_offset = frappe.db.get_value(
            "Account",
            {"company": company, "account_type": "Income Account", "is_group": 0},
            "name",
        ) or frappe.db.get_value(
            "Account",
            {"company": company, "root_type": "Income", "is_group": 0},
            "name",
        )

    if default_cash is None:
        default_cash = frappe.db.get_value(
            "Account",
            {"company": company, "account_type": "Cash", "is_group": 0},
            "name",
        ) or frappe.db.get_value(
            "Account",
            {"company": company, "account_name": "Cash", "is_group": 0},
            "name",
        )

    settings = frappe.get_single("Purisol Settings")
    changed = False

    for attr, val in [
        ("employee_liability_account", employee_liability),
        ("discrepancy_offset_account", discrepancy_offset),
        ("default_cash_account", default_cash),
    ]:
        if val is not None and getattr(settings, attr) != val:
            setattr(settings, attr, val)
            changed = True

    if changed:
        settings.save(ignore_permissions=True)


def seed_open_discrepancy(
    *,
    discrepancy_type,
    booklet,
    customer=None,
    triggering_entry=None,
    affected_coupons=(),
    estimated_amount=0.0,
):
    """Insert a draft Purisol Coupon Discrepancy directly (bypasses detection path).

    Returns the new document's name.  Used by resolution-only tests that need
    a ready-made Open discrepancy without driving a full Consumption Entry submit.
    """
    doc = frappe.new_doc("Purisol Coupon Discrepancy")
    doc.discrepancy_type = discrepancy_type
    doc.status = "Open"
    doc.opened_on = frappe.utils.now_datetime()
    doc.booklet = booklet
    doc.customer = customer
    doc.triggering_consumption_entry = triggering_entry
    doc.estimated_amount = estimated_amount

    for coupon_name in affected_coupons:
        doc.append("affected_coupons", {"coupon": coupon_name})

    doc.insert(ignore_permissions=True, ignore_mandatory=True)
    return doc.name


def make_booklet_with_consumed_coupons(customer, employee, consumed_pages=(1, 2)):
    """Create a Sold booklet and submit a Consumption Entry consuming the given pages.

    Returns (booklet_name, consumption_entry_name).
    ``customer`` and ``employee`` may be names (strings) or doc objects.
    ``consumed_pages`` is a 1-based tuple of page numbers to consume.
    """
    from cx_purisol.cx_purisol.api.booklet_generation import _create_booklet_and_coupons
    from cx_purisol.cx_purisol.api.sell_booklets import purisol_create_sales_invoice_for_booklets

    customer_name = customer if isinstance(customer, str) else customer.name
    emp_name = employee if isinstance(employee, str) else employee.name

    item = ensure_coupon_item()
    pl = ensure_price_list("Test-Consumption-PL")
    ensure_item_price(item.name, pl.name, 100)
    ensure_customer(customer_name, default_price_list=pl.name)
    configure_purisol_settings(coupon_item=item.name, default_price_list=pl.name)

    booklet_name, _ = _create_booklet_and_coupons(batch_id=None)
    result = purisol_create_sales_invoice_for_booklets(customer_name, [booklet_name])
    si = frappe.get_doc("Sales Invoice", result["name"])
    si.submit()

    all_coupons = frappe.get_all(
        "Purisol Coupon",
        filters={"booklet": booklet_name},
        fields=["name", "page_number"],
        order_by="page_number asc",
    )
    page_map = {c["page_number"]: c["name"] for c in all_coupons}
    coupon_names = [page_map[p] for p in consumed_pages if p in page_map]

    entry = frappe.get_doc({
        "doctype": "Purisol Coupon Consumption Entry",
        "posting_date": frappe.utils.today(),
        "posting_time": frappe.utils.nowtime(),
        "delivery_man": emp_name,
        "coupons": [{"coupon": c} for c in coupon_names],
    })
    entry.insert(ignore_permissions=True)
    entry.submit()

    return booklet_name, entry.name


def make_in_stock_booklet():
    """Create and return an In Stock (unsold) Purisol Coupon Booklet for US2 scenarios."""
    return make_booklet_in_stock()


# ---------------------------------------------------------------------------
# Phase 6 helpers
# ---------------------------------------------------------------------------


def seed_administrator_user(email, name=None):
    """Idempotently create a User + Has Role row for the Purisol Administrator role.

    Returns the User name (email).  Safe to call repeatedly within a single test.
    """
    if not frappe.db.exists("User", email):
        user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": name or email.split("@")[0],
            "send_welcome_email": 0,
            "enabled": 1,
            "user_type": "System User",
        })
        user.insert(ignore_permissions=True)
    else:
        user = frappe.get_doc("User", email)
        if not user.enabled:
            user.enabled = 1
            user.save(ignore_permissions=True)

    has_role = frappe.db.exists(
        "Has Role",
        {"parent": email, "parenttype": "User", "role": "Purisol Administrator"},
    )
    if not has_role:
        user = frappe.get_doc("User", email)
        user.append("roles", {"role": "Purisol Administrator"})
        user.save(ignore_permissions=True)

    return email


def count_notifications(
    for_user=None, doctype=None, document_name=None, subject_contains=None
):
    """Count Notification Log rows matching the given filters.

    All arguments are optional; omit for a sitewide count.  Used for delta-based
    assertions (count_before → count_after) in Phase-6 tests.
    """
    filters: dict = {}
    if for_user is not None:
        filters["for_user"] = for_user
    if doctype is not None:
        filters["document_type"] = doctype
    if document_name is not None:
        filters["document_name"] = document_name
    if subject_contains is not None:
        filters["subject"] = ["like", f"%{subject_contains}%"]
    return frappe.db.count("Notification Log", filters)


def reset_warehouse_dedup():
    """Clear Purisol Settings.last_warehouse_low_stock_notified_on between tests."""
    frappe.db.set_single_value(
        "Purisol Settings", "last_warehouse_low_stock_notified_on", None
    )
