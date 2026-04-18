# Phase 1 Data Model — Discrepancy Detection & Resolution

**Feature**: 005-discrepancy-detection | **Date**: 2026-04-18

Phase 5 introduces **three** new custom DocTypes (one submittable parent + two child tables), **widens one** existing Phase-4 stub DocType's JSON (one additive Link field), and **widens one** existing controller (`Purisol Coupon Consumption Entry` — Python only, no JSON change). It introduces **zero** new custom fields, **zero** new roles, and **zero** changes to any Phase 1/2/3 DocType.

---

## 1. New DocType — `Purisol Coupon Discrepancy`

**Purpose**: A submittable investigation record opened automatically by the system when the Consumption Entry submit detects an anomaly, and resolved manually by the Administrator. One record per distinct anomaly (one per booklet for Missing Coupons, one per coupon for Unassigned Booklet).

### 1.1. DocType-level properties

| Property | Value |
|----------|-------|
| `name` | `Purisol Coupon Discrepancy` |
| `module` | `Cx Purisol` |
| `autoname` | `PCD-.YYYY.-.#####` |
| `naming_rule` | `Expression (old style)` |
| `is_submittable` | `1` |
| `track_changes` | `1` |
| `engine` | `InnoDB` |
| `sort_field` | `opened_on` |
| `sort_order` | `DESC` |
| `search_fields` | `booklet,customer,discrepancy_type` |
| `title_field` | `name` |

### 1.2. Fields

| # | fieldname | fieldtype | options / default | reqd | read_only | in_list_view | Notes |
|---|-----------|-----------|-------------------|------|-----------|--------------|-------|
| 1 | `discrepancy_type` | `Select` | `Missing Coupons\nUnassigned Booklet` | 1 | 1 | 1 | Set by detection service; locked thereafter (immutable across validate). |
| 2 | `status` | `Select` | `Open\nUnder Review\nResolved - Admin Error\nResolved - Delivery Man Liable\nResolved - Paid`, default `Open` | 1 | 1 | 1 | Controller owns all transitions. Form field is read-only — status moves via submit. `Under Review` is the one save-time transition (see §1.5). |
| 3 | `opened_on` | `Datetime` | default: `now` | 1 | 1 | 1 | Set by detection service at insert time. |
| 4 | `resolved_on` | `Datetime` | — | 0 | 1 | 0 | Stamped by `before_submit` when a resolution path runs. |
| 5 | `section_break_detection` | `Section Break` | label: `Detection Context` | — | — | — | |
| 6 | `triggering_consumption_entry` | `Link` | `Purisol Coupon Consumption Entry` | 1 | 1 | 1 | The submitted entry that caused this discrepancy to open. Locked post-insert. |
| 7 | `booklet` | `Link` | `Purisol Coupon Booklet` | 1 | 1 | 1 | The affected booklet. Locked post-insert. |
| 8 | `customer` | `Link` | `Customer` | 0 | 1 | 1 | Fetched from `booklet.customer` at insert time (null for Unassigned Booklet). |
| 9 | `section_break_coupons` | `Section Break` | label: `Affected Coupons` | — | — | — | |
| 10 | `affected_coupons` | `Table` | `Purisol Coupon Discrepancy Coupon` | 1 | 1 | 0 | One row per missing/offending coupon. Locked post-insert. |
| 11 | `section_break_related` | `Section Break` | label: `Related Delivery Men` | — | — | — | |
| 12 | `related_delivery_men` | `Table` | `Purisol Coupon Discrepancy Related Person` | 0 | 1 | 0 | Auto-populated shortlist. Locked post-insert. |
| 13 | `section_break_resolution` | `Section Break` | label: `Resolution` | — | — | — | |
| 14 | `liable_delivery_man` | `Link` | `Employee` | 0 | 0 | 0 | Set by admin at resolution time. Conditional required via JS + server guard on the two financial paths. |
| 15 | `estimated_amount` | `Currency` | default: `0` | 0 | 0 | 1 | Auto-computed at insert; admin-editable while draft; locked at submit. |
| 16 | `resolution_action` | `Select` | `\nNone\nAdd to Liability Ledger\nImmediate Cash Payment` | 0 | 0 | 0 | Empty on draft = "not yet chosen". Blank selection leaves the discrepancy savable as Open. |
| 17 | `resolution_notes` | `Small Text` | — | 0 | 0 | 0 | Free-text. Preserved verbatim on submit (FR-016). |
| 18 | `section_break_links` | `Section Break` | label: `Linked Documents` | — | — | — | |
| 19 | `journal_entry` | `Link` | `Journal Entry` | 0 | 1 | 0 | Populated by `before_submit` when `resolution_action = "Add to Liability Ledger"`. |
| 20 | `payment_entry` | `Link` | `Payment Entry` | 0 | 1 | 0 | Populated by `before_submit` when `resolution_action = "Immediate Cash Payment"`. |
| 21 | `amended_from` | `Link` | `Purisol Coupon Discrepancy` | 0 | 1 | 0 | Standard Frappe field for submittables. Will never be populated because amend is disabled. |

### 1.3. Permissions

| role | read | write | create | submit | cancel | amend | delete | print | email | export | share | report |
|------|------|-------|--------|--------|--------|-------|--------|-------|-------|--------|-------|--------|
| `Purisol Administrator` | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 1 | 1 | 1 | 1 |
| `System Manager` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 1 | 1 |

No other role has any access. `amend = 0` enforces FR-017 (amendment not permitted).

### 1.4. State machine

```text
                       ┌──────────────────────────────┐
                       │ Open (created by detection)  │
                       └─┬────────────────────────────┘
                         │
                         │  save with status = "Under Review"
                         ▼
                   ┌────────────────┐
                   │ Under Review   │  (optional; no business logic hinges on it)
                   └─┬──────────────┘
                     │
 ┌───────────────────┼─────────────────────────────────────┐
 │                   │                                     │
 │ submit with       │  submit with                        │  submit with
 │ resolution_action │  resolution_action =                │  resolution_action =
 │ = "None"          │  "Add to Liability Ledger"          │  "Immediate Cash Payment"
 ▼                   ▼                                     ▼
"Resolved -      "Resolved - Delivery Man Liable"     "Resolved - Paid"
 Admin Error"    (JE created, linked via journal_entry)(PE created, linked via payment_entry)
 ▲
 └── all three terminal states are locked (docstatus = 1, amend disabled)
```

### 1.5. Controller lifecycle (`purisol_coupon_discrepancy.py`)

| Hook | Responsibility |
|------|----------------|
| `before_insert` | Defensive defaults: if `status` is empty, set to `"Open"`; if `opened_on` is empty, set to `frappe.utils.now_datetime()`. (The detection service explicitly sets both; this is belt-and-braces.) |
| `validate` | Enforce **field immutability** for detection-time fields while draft: compare against `get_doc_before_save()` and reject changes to `discrepancy_type`, `triggering_consumption_entry`, `booklet`, `customer`, `affected_coupons` (any row add/remove/edit), `related_delivery_men` (any row add/remove/edit), `opened_on`. Enforce **status-transition rules** for draft state: `Open → Under Review` or `Open → Open` (no-op) or `Under Review → Open` or `Under Review → Under Review` are save-time allowed; any other direct status write raises (only submit moves into the `Resolved - *` states). Recompute `estimated_amount` iff untouched since insert (implementation: set a hidden sentinel at insert time; skip recompute if the admin edited the value). |
| `before_submit` | Branch on `resolution_action`: **`""` (empty)** — throw `_("Please choose a resolution action before submitting.")`. **`"None"`** — no additional requirements; set `status = "Resolved - Admin Error"`, `resolved_on = now_datetime()`. **`"Add to Liability Ledger"`** — require `liable_delivery_man` (throw else); require `Purisol Settings.employee_liability_account` and `.discrepancy_offset_account` to both be set (aggregate errors; throw else); call `_create_liability_journal_entry(self)`; assign `self.journal_entry = <je.name>`; set `status = "Resolved - Delivery Man Liable"`, `resolved_on = now_datetime()`. **`"Immediate Cash Payment"`** — require `liable_delivery_man` (throw else); require `Purisol Settings.discrepancy_offset_account` and `.default_cash_account` (aggregate errors; throw else); call `_create_cash_payment_entry(self)`; assign `self.payment_entry = <pe.name>`; set `status = "Resolved - Paid"`, `resolved_on = now_datetime()`. |
| `on_submit` | No-op. All side effects were performed in `before_submit`. |
| `on_cancel` | Throw `_("Cancelling a resolved discrepancy is not permitted. Corrections must go through a reversing Journal Entry or Payment Entry.")` — enforces FR-017 belt-and-braces for an even more paranoid variant than "amend = 0" alone provides. |

### 1.6. Helpers (module-private)

- `_create_liability_journal_entry(doc: PurisolCouponDiscrepancy) -> frappe.model.document.Document`:
  - Reads `settings = frappe.get_cached_doc("Purisol Settings")`.
  - Builds a `Journal Entry` with `voucher_type = "Journal Entry"`, `posting_date = today`, `company = settings.get("company") or erpnext.get_default_company()`, `user_remark = _("Discrepancy {0} — liable {1}").format(doc.name, doc.liable_delivery_man)`.
  - Appends two account rows as documented in research.md §7 (debit to `employee_liability_account` with party, credit to `discrepancy_offset_account`).
  - `.insert()` + `.submit()` inside the current transaction. Returns the JE document.
- `_create_cash_payment_entry(doc: PurisolCouponDiscrepancy) -> frappe.model.document.Document`:
  - Reads the same settings.
  - Builds a `Payment Entry` with `payment_type = "Receive"`, `posting_date = today`, `company = ...`, `paid_from = settings.discrepancy_offset_account`, `paid_to = settings.default_cash_account`, `paid_amount = doc.estimated_amount`, `received_amount = doc.estimated_amount`, `party_type = "Employee"`, `party = doc.liable_delivery_man`.
  - Appends a references row: `reference_doctype = "Purisol Coupon Discrepancy"`, `reference_name = doc.name`, `allocated_amount = doc.estimated_amount`.
  - `.insert()` + `.submit()`. Returns the PE document.

Both helpers run inside the current submit transaction; a raise from inside ERPNext's own validation propagates out and rolls the whole discrepancy submit back.

---

## 2. New DocType (child table) — `Purisol Coupon Discrepancy Coupon`

**Purpose**: One row per affected coupon on a `Purisol Coupon Discrepancy`.

### 2.1. DocType-level properties

| Property | Value |
|----------|-------|
| `name` | `Purisol Coupon Discrepancy Coupon` |
| `module` | `Cx Purisol` |
| `istable` | `1` |
| `track_changes` | `1` |
| `engine` | `InnoDB` |

### 2.2. Fields

| # | fieldname | fieldtype | options | reqd | read_only | in_list_view | Notes |
|---|-----------|-----------|---------|------|-----------|--------------|-------|
| 1 | `coupon` | `Link` | `Purisol Coupon` | 1 | 0 | 1 | Search-indexed. Primary key of the row. |
| 2 | `coupon_number` | `Data` | — | 0 | 1 | 1 | `fetch_from = coupon.coupon_number`. |
| 3 | `booklet` | `Link` | `Purisol Coupon Booklet` | 0 | 1 | 0 | `fetch_from = coupon.booklet`. Same-as-parent in all Phase-5 use cases; stored for report convenience. |
| 4 | `notes` | `Small Text` | — | 0 | 0 | 0 | Free-text per-coupon notes (optional; unused by detection). |

### 2.3. Controller (`purisol_coupon_discrepancy_coupon.py`)

Empty Document subclass — no row-level validation; parent-level invariants live on `Purisol Coupon Discrepancy`.

---

## 3. New DocType (child table) — `Purisol Coupon Discrepancy Related Person`

**Purpose**: One row per delivery-man touchpoint on a `Purisol Coupon Discrepancy`. Surfaces the investigation shortlist.

### 3.1. DocType-level properties

| Property | Value |
|----------|-------|
| `name` | `Purisol Coupon Discrepancy Related Person` |
| `module` | `Cx Purisol` |
| `istable` | `1` |
| `track_changes` | `1` |
| `engine` | `InnoDB` |

### 3.2. Fields

| # | fieldname | fieldtype | options | reqd | read_only | in_list_view | Notes |
|---|-----------|-----------|---------|------|-----------|--------------|-------|
| 1 | `delivery_man` | `Link` | `Employee` | 1 | 0 | 1 | The employee with a touchpoint to the booklet. |
| 2 | `role` | `Select` | `Custody Holder\nSubmitted Adjacent Coupons` | 1 | 0 | 1 | How the person is related to the booklet. |
| 3 | `custody_entry` | `Link` | `Purisol Custody Entry` | 0 | 0 | 0 | Populated when `role = "Custody Holder"`. |
| 4 | `consumption_entry` | `Link` | `Purisol Coupon Consumption Entry` | 0 | 0 | 0 | Populated when `role = "Submitted Adjacent Coupons"`. |
| 5 | `notes` | `Small Text` | — | 0 | 0 | 0 | Free-text. |

### 3.3. Controller (`purisol_coupon_discrepancy_related_person.py`)

Empty Document subclass. The "exactly one of custody_entry / consumption_entry is populated" invariant is enforced at the auto-populate site in the detection service (research.md §4) — not at the row level, because the parent admin may legitimately leave both blank on a manually-added row.

---

## 4. Widening the Phase-4 stub `Purisol Coupon Discrepancy Item`

### 4.1. JSON changes

**Before** (Phase 4):

```json
{
  "fields": [
    { "fieldname": "notes", "fieldtype": "Small Text", "label": "Notes" }
  ],
  ...
}
```

**After** (Phase 5):

```json
{
  "field_order": [
    "discrepancy",
    "discrepancy_type",
    "notes"
  ],
  "fields": [
    {
      "fieldname": "discrepancy",
      "fieldtype": "Link",
      "label": "Discrepancy",
      "options": "Purisol Coupon Discrepancy",
      "reqd": 1,
      "in_list_view": 1
    },
    {
      "fieldname": "discrepancy_type",
      "fieldtype": "Select",
      "options": "Missing Coupons\nUnassigned Booklet",
      "fetch_from": "discrepancy.discrepancy_type",
      "read_only": 1,
      "in_list_view": 1
    },
    { "fieldname": "notes", "fieldtype": "Small Text", "label": "Notes" }
  ]
}
```

No other JSON property changes. `istable = 1`, `track_changes = 1`, module `Cx Purisol` all preserved.

### 4.2. Controller (`purisol_coupon_discrepancy_item.py`)

Unchanged — remains an empty `Document` subclass.

---

## 5. Widening the `Purisol Coupon Consumption Entry` controller

**No JSON change.** The Phase-4 controller is widened in Python only:

### 5.1. `validate` — drop the two defensive throws

**Before** (Phase 4):

```python
def validate(self):
    self.total_coupons = len(self.coupons or [])

    if not self.coupons:
        frappe.throw(_("Consumption Entry must list at least one coupon."))

    seen = set()
    for row in self.coupons:
        if row.coupon in seen:
            frappe.throw(_("Coupon {0} appears more than once in this entry.").format(row.coupon))
        seen.add(row.coupon)

    if self.has_warnings:
        frappe.throw(_("has_warnings is reserved for Phase 5 and cannot be set."))

    if self.discrepancies_detected:
        frappe.throw(_("discrepancies_detected is reserved for Phase 5."))
```

**After** (Phase 5):

```python
def validate(self):
    self.total_coupons = len(self.coupons or [])

    if not self.coupons:
        frappe.throw(_("Consumption Entry must list at least one coupon."))

    seen = set()
    for row in self.coupons:
        if row.coupon in seen:
            frappe.throw(_("Coupon {0} appears more than once in this entry.").format(row.coupon))
        seen.add(row.coupon)

    # has_warnings and discrepancies_detected are controller-owned (not admin-editable).
    # The form fields remain read_only = 1 in the JSON; only server-side code writes them.
    # No validation needed here — the detection service in on_submit populates them.
```

### 5.2. `on_submit` — add detection pass after Phase-4 side effects

```python
def on_submit(self):
    posting_dt = self.posting_datetime
    for row in self.coupons:
        frappe.db.set_value(
            "Purisol Coupon",
            row.coupon,
            {
                "status": "Consumed",
                "consumed_on": posting_dt,
                "consumed_by_delivery_man": self.delivery_man,
                "consumption_entry": self.name,
            },
            update_modified=True,
        )

    booklets = {row.booklet for row in self.coupons if row.booklet}
    for b in booklets:
        consumed_count = frappe.db.count("Purisol Coupon", {"booklet": b, "status": "Consumed"})
        remaining_count = 20 - consumed_count
        booklet = frappe.get_doc("Purisol Coupon Booklet", b)
        booklet.consumed_count = consumed_count
        booklet.remaining_count = remaining_count
        triggered_depletion = consumed_count == 20 and booklet.status == "Sold"
        if triggered_depletion:
            booklet.status = "Depleted"
            booklet.depleted_on = posting_dt
        booklet.save(ignore_permissions=True)
        if triggered_depletion:
            booklet.add_comment("Info", _("Depleted via {0}").format(self.name))

    # Phase 5: detect discrepancies and append to discrepancies_detected.
    from cx_purisol.cx_purisol.api.discrepancy import detect_for_entry

    created_names = detect_for_entry(self)
    if created_names:
        self.has_warnings = 1
        for name in created_names:
            self.append(
                "discrepancies_detected",
                {"discrepancy": name},
            )
        # Persist the widened parent doc. `db_update` keeps us in the submit transaction
        # and writes parent + child rows atomically.
        self.db_update()
        for row in self.discrepancies_detected:
            row.db_insert()
```

`db_update()` + `db_insert()` are the low-level writes that stay inside the current transaction without triggering a recursive `validate`/`on_submit` pass.

### 5.3. `on_cancel` — unchanged from Phase 4

Phase 5 does **not** widen cancel. Spec edge case: "Cancellation of a consumption entry that created discrepancies — Out of scope for MVP." Discrepancies opened by a later-cancelled entry remain in their current state; the admin handles them manually through the resolution flow.

---

## 6. Detection service — `cx_purisol/cx_purisol/api/discrepancy.py`

Server-side module; not whitelisted.

### 6.1. Public entrypoint

```python
def detect_for_entry(entry) -> list[str]:
    """
    Run both detection rules against the just-submitted Consumption Entry.
    Returns a list of newly-created Purisol Coupon Discrepancy names,
    possibly empty.

    Pre: Phase-4 side effects on coupons and booklets are already committed
    to the current transaction (this is called from the end of on_submit).
    """
```

### 6.2. Private helpers

- `_detect_missing_coupons(entry) -> list[str]` — for each distinct booklet in `entry.coupons`, run the algorithm in research.md §2. For each non-empty gap, build a `Purisol Coupon Discrepancy` doc with the fields per §6.3 below, `.insert()` + `.submit()` inside the current transaction, and collect its `name`.
- `_detect_unassigned_booklets(entry) -> list[str]` — for each row in `entry.coupons`, read `booklet.status`; if not `"Sold"`, build a per-coupon discrepancy (single-row `affected_coupons`) and submit.
- `_auto_populate_related_delivery_men(doc, entry, booklet)` — mutates `doc.related_delivery_men` in place, per research.md §4.
- `_compute_estimated_amount(booklet, affected_coupons_count) -> float` — per research.md §3.
- `_list_open_missing_coupon_names(booklet) -> set[str]` — `frappe.get_all` against `Purisol Coupon Discrepancy Coupon` joined to the parent where `parenttype = "Purisol Coupon Discrepancy"`, `docstatus = 1` is **wrong** (we want draft-or-submitted? No — Open means `docstatus` could be 0 (draft never submitted, impossible in practice) or 1 (submitted as Open). Since `Open` is only a pre-submit status, a discrepancy in `status = "Open"` always has `docstatus = 0`; but detection creates it, populates it, then `.submit()` → `docstatus = 1` with `status = "Resolved - *"`. Wait — re-read the model: detection creates discrepancies in Open state and `.submit()`s them? Let me reconsider. Spec: "Detection creates a Purisol Coupon Discrepancy submittable record (status Open)". That means at detection time, the discrepancy is **created as a submitted record** whose business-state is `Open` (the submittable's `docstatus = 1` but our own `status` field says `Open`). Submitted is about the structural lifecycle; `status` is about the business lifecycle. Admin later *cancels-then-resubmits*? No — per spec "once submitted, locked". The right reading: submit-with-status-Open is how a new discrepancy is persisted, and resolution happens by the admin cancelling, editing, re-submitting? That contradicts FR-017 ("amendment is not permitted"). Instead: detection `.insert()`s a draft (`docstatus = 0`, `status = "Open"`); resolution is the submit (flips to `docstatus = 1` + `status = "Resolved - *"`). "Submittable" in spec language = "of type submittable", not "is already submitted". See §7 below for the final reading.

### 6.3. Detection-time field writes (common to both rules)

```python
doc = frappe.new_doc("Purisol Coupon Discrepancy")
doc.discrepancy_type = ...                        # "Missing Coupons" or "Unassigned Booklet"
doc.status = "Open"
doc.opened_on = frappe.utils.now_datetime()
doc.triggering_consumption_entry = entry.name
doc.booklet = booklet_name
doc.customer = booklet_doc.customer               # None for Unassigned Booklet
for row in affected_rows:
    doc.append("affected_coupons", {"coupon": row.name})
_auto_populate_related_delivery_men(doc, entry, booklet_doc)
doc.estimated_amount = _compute_estimated_amount(booklet_doc, len(affected_rows))
doc.insert(ignore_permissions=True)
```

**Key point** — `doc.insert()` only, **not** `doc.submit()`. The discrepancy is persisted as a draft (`docstatus = 0`) with business-state `status = "Open"`. The admin's resolution action is the submit. See §7.

---

## 7. Lifecycle reconciliation — "submittable" ≠ "already submitted"

The spec uses "submittable" throughout to describe `Purisol Coupon Discrepancy`. In Frappe vocabulary:

- **`is_submittable = 1`** on the DocType = "this DocType supports submit/cancel lifecycle".
- **`docstatus = 0`** = draft; `docstatus = 1` = submitted; `docstatus = 2` = cancelled.
- A *detected* discrepancy lives at `docstatus = 0, status = "Open"` (or `"Under Review"` if the admin saves that mid-investigation). Save-time edits are allowed (admin can set `liable_delivery_man`, `estimated_amount`, `resolution_action`, `resolution_notes`, `status = "Under Review"`) while draft.
- A *resolved* discrepancy lives at `docstatus = 1, status ∈ {"Resolved - Admin Error", "Resolved - Delivery Man Liable", "Resolved - Paid"}`. Frappe's built-in submitted-document semantics lock every field (FR-017). `amend = 0` disallows the cancel-then-amend-then-resubmit cycle.

This reconciles:
- Detection creates and `.insert()`s (not `.submit()`s).
- The "Open Discrepancies" list view filter is `status = "Open"` — covers both `docstatus = 0, status = "Open"` and the hypothetical `docstatus = 0, status = "Under Review"` only if we also filter `docstatus = 0`. (The saved list view filter is therefore `status IN ("Open", "Under Review")` OR equivalently `docstatus = 0` — decision in research.md §12 is to use `status = "Open"` as-is, matching spec FR-018 verbatim; `Under Review` discrepancies fall off the "Open" list, which is the intended UX given that `Under Review` is an admin's private investigation marker).
- Resolution is the `.submit()`; the controller's `before_submit` does the work.
- Cancellation on a resolved discrepancy would revert it to `docstatus = 2, status = "Resolved - *"` — we explicitly disable this via the `on_cancel` throw (§1.5 last row), preserving audit trail.

---

## 8. Relationships diagram

```
            Purisol Coupon Consumption Entry  (Phase 4; controller widened in Phase 5)
             ├── (Phase 4 fields ...)
             ├── has_warnings               : Check   (Phase 5 — set by on_submit when discrepancies created)
             │
             └── discrepancies_detected (1:N)
                     → Purisol Coupon Discrepancy Item  (Phase 4 stub, widened in Phase 5)
                          ├── discrepancy                  → Purisol Coupon Discrepancy  (*** Phase 5 ***)
                          ├── discrepancy_type             : Select (fetched, read-only)
                          └── notes                        : Small Text

            Purisol Coupon Discrepancy  (*** NEW, submittable ***)
             ├── discrepancy_type           : Select
             ├── status                     : Select (5 values)
             ├── opened_on / resolved_on    : Datetime
             ├── triggering_consumption_entry  → Purisol Coupon Consumption Entry
             ├── booklet                       → Purisol Coupon Booklet
             ├── customer                      → Customer (nullable)
             ├── liable_delivery_man           → Employee
             ├── estimated_amount           : Currency
             ├── resolution_action          : Select (None | Add to Liability Ledger | Immediate Cash Payment)
             ├── resolution_notes           : Small Text
             │
             ├── affected_coupons (1:N)
             │        → Purisol Coupon Discrepancy Coupon  (*** NEW ***)
             │             ├── coupon            → Purisol Coupon
             │             ├── coupon_number     : Data (fetched)
             │             └── booklet           → Purisol Coupon Booklet (fetched)
             │
             ├── related_delivery_men (1:N)
             │        → Purisol Coupon Discrepancy Related Person  (*** NEW ***)
             │             ├── delivery_man      → Employee
             │             ├── role              : Select (Custody Holder | Submitted Adjacent Coupons)
             │             ├── custody_entry     → Purisol Custody Entry (optional)
             │             └── consumption_entry → Purisol Coupon Consumption Entry (optional)
             │
             ├── journal_entry             → Journal Entry  (populated on Liability resolution)
             └── payment_entry             → Payment Entry  (populated on Cash Payment resolution)


            Purisol Settings  (Phase 1; fields already reserved)
             ├── coupon_item                   → Item               (used for price-list fallback)
             ├── default_price_list            → Price List         (used for price-list fallback)
             ├── employee_liability_account    → Account            (required for Add to Liability Ledger)
             ├── discrepancy_offset_account    → Account            (required for both financial paths)
             └── default_cash_account          → Account            (required for Immediate Cash Payment)
```

---

## 9. Validations in one place

### 9.1. Parent-level `validate` on `Purisol Coupon Discrepancy` (runs on every save, including drafts)

| # | Rule | On violation |
|---|------|--------------|
| V1 | `discrepancy_type` immutable vs `get_doc_before_save()` | `frappe.throw(_("discrepancy_type cannot be changed after creation."))` |
| V2 | `triggering_consumption_entry` immutable | `_("triggering_consumption_entry cannot be changed after creation.")` |
| V3 | `booklet` immutable | `_("booklet cannot be changed after creation.")` |
| V4 | `customer` immutable | `_("customer cannot be changed after creation.")` |
| V5 | `opened_on` immutable | `_("opened_on cannot be changed after creation.")` |
| V6 | `affected_coupons` rows immutable (same length, same coupon per row, same order) | `_("affected_coupons cannot be edited after creation.")` |
| V7 | `related_delivery_men` rows immutable | `_("related_delivery_men cannot be edited after creation.")` |
| V8 | `status` can only transition `Open ↔ Under Review` via save | `_("Status transition from {0} to {1} is not allowed on save.").format(prior, new)` |
| V9 | Recompute `estimated_amount` if admin hasn't edited it since insert | — (pure compute) |

### 9.2. Submit-time `before_submit` on `Purisol Coupon Discrepancy`

Errors are **aggregated** across preconditions so the admin sees every missing input in one rejection.

| # | Rule (applies per `resolution_action`) | On violation |
|---|----------------------------------------|--------------|
| S1 | `resolution_action` is set | `_("Please choose a resolution action before submitting.")` |
| S2a | `Add to Liability Ledger`: `liable_delivery_man` set | `_("Liable Delivery Man is required for 'Add to Liability Ledger'.")` |
| S2b | `Add to Liability Ledger`: `Purisol Settings.employee_liability_account` set | `_("Employee liability account is not configured in Purisol Settings.")` |
| S2c | `Add to Liability Ledger`: `Purisol Settings.discrepancy_offset_account` set | `_("Discrepancy offset account is not configured in Purisol Settings.")` |
| S3a | `Immediate Cash Payment`: `liable_delivery_man` set | `_("Liable Delivery Man is required for 'Immediate Cash Payment'.")` |
| S3b | `Immediate Cash Payment`: `Purisol Settings.discrepancy_offset_account` set | `_("Discrepancy offset account is not configured in Purisol Settings.")` |
| S3c | `Immediate Cash Payment`: `Purisol Settings.default_cash_account` set | `_("Default cash account is not configured in Purisol Settings.")` |
| S4 | `None`: no additional preconditions | — |

### 9.3. `on_cancel` on `Purisol Coupon Discrepancy`

| # | Rule | On violation |
|---|------|--------------|
| C1 | Always reject cancellation (FR-017) | `_("Cancelling a resolved discrepancy is not permitted. Corrections must go through a reversing Journal Entry or Payment Entry.")` |

### 9.4. Detection-service invariants (not blocking — raises only on infrastructure failure)

The detection service is pure read + fresh-insert. It raises only if `frappe.get_all` or `doc.insert` raises (infrastructure failure). Any raise propagates out of `on_submit` and rolls the Consumption Entry back.

---

## 10. Fixtures / migrations

### 10.1. Fixtures

No new role fixture (the existing `Purisol Administrator` role is referenced directly in the new DocType JSONs' permissions).

**New fixture: saved list view** — a `Workspace` or `List View Settings` fixture entry (final choice: **a `List View Settings` fixture** — simpler than a Workspace entry and scoped to this single DocType). The fixture creates a default filter bundled with the new DocType JSON's `actions` / `states` properties, or via a dedicated `View` DocType record:

```json
{
  "doctype": "List View Settings",
  "name": "Purisol Coupon Discrepancy",
  "total_fields": 5,
  "fields": [
    { "fieldname": "discrepancy_type" },
    { "fieldname": "booklet" },
    { "fieldname": "customer" },
    { "fieldname": "estimated_amount" },
    { "fieldname": "opened_on" }
  ]
}
```

The default filter `status = "Open"` is shipped as the DocType's list-view script default instead (research.md §12 revision): the `doctype_list_js` entry in `hooks.py` points at `doctype/purisol_coupon_discrepancy/purisol_coupon_discrepancy_list.js`, which sets the default filter if none is already applied.

Final decision: **go with the list script** — `List View Settings` DocType is a newer ERPNext feature whose fixture export is inconsistent across versions; the list script is known to work on Frappe 15. The script is documented in §1 of the plan.

### 10.2. `patches.txt`

Add one post-model-sync entry:

```
cx_purisol.patches.v0_5_0.relax_consumption_entry_reserved_guards
```

No-op anchor, matches the Phase 2/3/4 pattern.

### 10.3. `hooks.py` changes

- Extend `doctype_js` (it's currently `doctype_list_js = {"Purisol Coupon Booklet": ...}`; we add both):

```python
doctype_js = {
    "Purisol Coupon Discrepancy": "public/js/purisol_coupon_discrepancy.js",
}

doctype_list_js = {
    "Purisol Coupon Booklet": "public/js/purisol_coupon_booklet_list.js",
    "Purisol Coupon Discrepancy": "public/js/purisol_coupon_discrepancy_list.js",
}
```

(The per-doctype JS files colocate with the DocType folder but are referenced via the `public/js/` path; Frappe's convention is to symlink or copy those into `public/js` at build time. We follow Phase 3's precedent.)

- **No** new `doc_events`. All detection is called from the Consumption Entry controller's own `on_submit`.

---

## 11. What is deliberately NOT changed

- **No change** to `purisol_coupon.json`, `purisol_coupon_booklet.json`, `purisol_settings.json`, `purisol_custody_entry*.json`, `purisol_coupon_consumption_entry.json`, `purisol_coupon_consumption_item.json`. The reserved fields on `Purisol Settings` (the three account links) already exist; we start using them. The reserved fields on the Consumption Entry (`has_warnings`, `discrepancies_detected`) already exist; we start using them.
- **No new role.** `Purisol Administrator` covers every Phase-5 interaction.
- **No new custom field fixture.** Phase 3's `Sales Invoice Item.purisol_booklet` already exists.
- **No new whitelisted API.** Detection is internal; resolution goes through the submittable form.
- **No notification code.** The post-submit modal is a client-script concern, not a Notification DocType. Phase-6 owns channel-agnostic notifications.
- **No report code** beyond the default list view and its saved filter.
- **No background jobs.** Every operation is well under the synchronous threshold.
- **No changes to `Purisol Coupon Consumption Entry.on_cancel`.** Linked discrepancies remain in their current state if the entry is cancelled; the admin handles them manually.
- **No amend path for resolved discrepancies** (`amend = 0`). Corrections go through reversing JEs/PEs.
