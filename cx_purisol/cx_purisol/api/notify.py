"""Purisol Notify — channel-agnostic notification utility (Phase 6).

Single public entry point for every Phase-6 alert.  Internally dispatches to the
ERPNext ``Notification Log`` bell-icon channel; a future phase adds email / SMS
/ WhatsApp by editing this module only — trigger sites never change.

Runs inside the caller's transaction.  Empty recipient sets (unknown role,
all-disabled users, unknown user, blank input) are a silent no-op (FR-014).
"""
from __future__ import annotations

import frappe


def send(
    recipient: str,
    subject: str,
    message: str,
    reference_doctype: str | None = None,
    reference_name: str | None = None,
) -> list[str]:
    """Create one Notification Log entry per enabled user matching ``recipient``.

    ``recipient`` may be either an exact Role name (preferred) or an exact User
    name.  Role input expands to the set of enabled users holding that role;
    unknown roles, unknown users, and disabled users all collapse to an empty
    recipient set and a silent no-op.

    Returns the list of Notification Log names created, possibly empty.
    Runs inside the caller's transaction.  Any raise propagates and rolls back.
    """
    if not recipient or not str(recipient).strip():
        return []

    users = _resolve_recipients(recipient)
    created: list[str] = []
    for user in users:
        created.append(
            _emit_bell(
                for_user=user,
                subject=subject,
                message=message,
                reference_doctype=reference_doctype,
                reference_name=reference_name,
            )
        )
    return created


def _resolve_recipients(recipient: str) -> list[str]:
    """Resolve a role-or-user input to the list of enabled User names.

    Role-first resolution; falls back to direct User lookup.  Empty result on
    unknown input or all-disabled role (FR-014).
    """
    if frappe.db.exists("Role", recipient):
        rows = frappe.db.sql(
            """
            SELECT DISTINCT hr.parent AS user
            FROM `tabHas Role` hr
            INNER JOIN `tabUser` u ON u.name = hr.parent
            WHERE hr.role = %s
              AND hr.parenttype = 'User'
              AND u.enabled = 1
            """,
            (recipient,),
            as_dict=True,
        )
        return [r["user"] for r in rows]

    if frappe.db.exists("User", recipient):
        enabled = frappe.db.get_value("User", recipient, "enabled")
        return [recipient] if enabled else []

    return []


def _emit_bell(
    for_user: str,
    subject: str,
    message: str,
    reference_doctype: str | None,
    reference_name: str | None,
) -> str:
    """Create one Notification Log entry with type='Alert' targeting ``for_user``.

    Returns the created Notification Log name.  Runs inside the caller's
    transaction; a raise propagates.
    """
    log = frappe.new_doc("Notification Log")
    log.type = "Alert"
    log.subject = subject
    log.email_content = message
    log.for_user = for_user
    if reference_doctype:
        log.document_type = reference_doctype
    if reference_name:
        log.document_name = reference_name
    log.from_user = None
    log.insert(ignore_permissions=True)
    return log.name
