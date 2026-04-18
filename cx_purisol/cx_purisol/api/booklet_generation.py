import time
import uuid

import frappe
from frappe import _
from frappe.model.naming import make_autoname


def _coupon_range_for_booklet(k: int) -> tuple:
    """Return (first_coupon_name, last_coupon_name) for booklet number k."""
    return (f"CP-{(k - 1) * 20 + 1:05d}", f"CP-{k * 20:05d}")


@frappe.whitelist()
def purisol_generate_booklets(quantity, batch_id=None):
    frappe.only_for("Purisol Administrator")

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        frappe.throw(_("Quantity must be a positive integer."))

    if quantity <= 0:
        frappe.throw(_("Quantity must be a positive integer."))

    batch_id = (batch_id or "").strip() or None

    if quantity <= 20:
        return _run_sync(quantity, batch_id)

    job_name = f"purisol_generate_booklets_{uuid.uuid4().hex}"
    frappe.enqueue(
        "cx_purisol.cx_purisol.api.booklet_generation._run_generate_booklets_job",
        queue="long",
        timeout=1800,
        quantity=quantity,
        batch_id=batch_id,
        user=frappe.session.user,
        job_name=job_name,
        now=False,
    )
    return {
        "mode": "async",
        "job_name": job_name,
        "channel": "purisol_generate_booklets_progress",
        "quantity": quantity,
    }


def _run_sync(quantity: int, batch_id):
    first_booklet = None
    last_booklet = None

    for _i in range(quantity):
        booklet_name, _k = _create_booklet_and_coupons(batch_id)
        if first_booklet is None:
            first_booklet = booklet_name
        last_booklet = booklet_name

    frappe.db.commit()
    return {
        "mode": "sync",
        "first_booklet": first_booklet,
        "last_booklet": last_booklet,
        "total_coupons": quantity * 20,
        "batch_id": batch_id,
    }


def _run_generate_booklets_job(quantity, batch_id, user, job_name=""):
    frappe.publish_realtime(
        event="purisol_generate_booklets_progress",
        message={"status": "started", "job_name": job_name, "total": quantity, "done": 0, "batch_id": batch_id},
        user=user,
    )

    first_booklet = None
    last_booklet = None
    last_progress_time = time.monotonic()
    last_progress_pct = 0

    try:
        for i in range(quantity):
            booklet_name, _ = _create_booklet_and_coupons(batch_id)
            if first_booklet is None:
                first_booklet = booklet_name
            last_booklet = booklet_name
            frappe.db.commit()

            done = i + 1
            now = time.monotonic()
            pct = int(done / quantity * 100)
            elapsed = now - last_progress_time
            if pct > last_progress_pct and elapsed >= 0.5:
                frappe.publish_realtime(
                    event="purisol_generate_booklets_progress",
                    message={
                        "status": "progress",
                        "job_name": job_name,
                        "total": quantity,
                        "done": done,
                        "last_booklet": last_booklet,
                    },
                    user=user,
                )
                last_progress_time = now
                last_progress_pct = pct

        frappe.publish_realtime(
            event="purisol_generate_booklets_progress",
            message={
                "status": "complete",
                "job_name": job_name,
                "total": quantity,
                "first_booklet": first_booklet,
                "last_booklet": last_booklet,
                "total_coupons": quantity * 20,
                "batch_id": batch_id,
            },
            user=user,
        )
    except Exception as exc:
        frappe.log_error(frappe.get_traceback(), "purisol_generate_booklets_job")
        frappe.publish_realtime(
            event="purisol_generate_booklets_progress",
            message={
                "status": "failed",
                "job_name": job_name,
                "done": (first_booklet and int(last_booklet.split("-")[1]) - int(first_booklet.split("-")[1]) + 1) or 0,
                "error": str(exc),
            },
            user=user,
        )


def _create_booklet_and_coupons(batch_id):
    """Create one booklet + its 20 coupons inside a savepoint. Returns (booklet_name, k)."""
    sp = "purisol_booklet_sp"
    frappe.db.savepoint(sp)
    try:
        booklet_name = make_autoname("WP-.#####")
        k = int(booklet_name.split("-")[1])
        first_cp, last_cp = _coupon_range_for_booklet(k)

        booklet = frappe.get_doc(
            {
                "doctype": "Purisol Coupon Booklet",
                "name": booklet_name,
                "booklet_number": booklet_name,
                "status": "In Stock",
                "first_coupon": first_cp,
                "last_coupon": last_cp,
                "total_coupons": 20,
                "consumed_count": 0,
                "remaining_count": 20,
                "batch_id": batch_id,
            }
        )
        booklet.flags.ignore_permissions = True
        booklet.flags.ignore_mandatory = True
        booklet.insert(ignore_permissions=True, set_name=booklet_name)

        for page in range(1, 21):
            cp_num = (k - 1) * 20 + page
            cp_name = f"CP-{cp_num:05d}"
            coupon = frappe.get_doc(
                {
                    "doctype": "Purisol Coupon",
                    "name": cp_name,
                    "coupon_number": cp_name,
                    "booklet": booklet_name,
                    "page_number": page,
                    "status": "Available",
                }
            )
            coupon.flags.ignore_permissions = True
            coupon.flags.ignore_mandatory = True
            coupon.insert(ignore_permissions=True, set_name=cp_name)

        frappe.db.sql("UPDATE `tabSeries` SET `current` = %s WHERE `name` = 'CP'", (k * 20,))
        return booklet_name, k

    except Exception:
        frappe.db.rollback(save_point=sp)
        raise
