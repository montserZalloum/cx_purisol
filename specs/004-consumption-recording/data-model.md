# Phase 1 Data Model — Consumption Recording

**Feature**: 004-consumption-recording | **Date**: 2026-04-18

Phase 4 introduces **three** new custom DocTypes (one submittable parent, one primary child table, one reserved-empty child-table stub), **widens two** existing controllers' state-machine guards, and makes **zero** JSON schema changes to any existing Purisol DocType. No existing field is renamed, retyped, or removed — Phase 4 activates reserved fields (`consumed_on`, `consumed_by_delivery_man`, `consumption_entry` on `Purisol Coupon`; `depleted_on` on `Purisol Coupon Booklet`) that have lived in the schema since Phase 1.

---

## 1. New DocType — `Purisol Coupon Consumption Entry`

**Purpose**: Submittable record of the coupons a given delivery man handed in at end of day. One record per delivery-man-per-day-per-handin event. Source of truth for coupon `Available → Consumed` transitions.

### 1.1. DocType-level properties

| Property | Value |
|----------|-------|
| `name` | `Purisol Coupon Consumption Entry` |
| `module` | `Cx Purisol` |
| `autoname` | `PCC-.YYYY.-.#####` |
| `naming_rule` | `Expression (old style)` |
| `is_submittable` | `1` |
| `track_changes` | `1` |
| `engine` | `InnoDB` |
| `sort_field` | `modified` |
| `sort_order` | `DESC` |
| `search_fields` | `delivery_man,posting_date` |

### 1.2. Fields

| # | fieldname | fieldtype | options / default | reqd | read_only | in_list_view | Notes |
|---|-----------|-----------|-------------------|------|-----------|--------------|-------|
| 1 | `posting_date` | `Date` | default: `Today` | 1 | 0 | 1 | Day the coupons were handed in. Backdating allowed; admin judgement. |
| 2 | `posting_time` | `Time` | default: `now` | 1 | 0 | 0 | Time of handin. Combined with `posting_date` into `posting_datetime`. |
| 3 | `delivery_man` | `Link` | `Employee` | 1 | 0 | 1 | The delivery man physically handing in the coupons. |
| 4 | `received_by` | `Link` | `User` | 0 | 1 | 0 | Auto-stamped in `before_insert` with `frappe.session.user`. |
| 5 | `section_break_coupons` | `Section Break` | label: `Consumed Coupons` | — | — | — | |
| 6 | `coupons` | `Table` | `Purisol Coupon Consumption Item` | 1 | 0 | 0 | One row per consumed coupon. Written by both Mode A and Mode B. |
| 7 | `total_coupons` | `Int` | default: `0` | 0 | 1 | 1 | Computed on `validate` as `len(coupons)`. |
| 8 | `section_break_reserved` | `Section Break` | label: `Reserved (Phase 5)` | — | — | — | |
| 9 | `has_warnings` | `Check` | default: `0` | 0 | 1 | 0 | Reserved — always `0` in Phase 4. Controller rejects any non-zero value. |
| 10 | `discrepancies_detected` | `Table` | `Purisol Coupon Discrepancy Item` | 0 | 1 | 0 | Reserved — always empty in Phase 4. Controller rejects any non-empty table. |
| 11 | `section_break_notes` | `Section Break` | label: `Notes` | — | — | — | |
| 12 | `notes` | `Small Text` | — | 0 | 0 | 0 | Free-text remarks. |

### 1.3. Permissions

| role | read | write | create | submit | cancel | amend | delete | print | email | export | share | report |
|------|------|-------|--------|--------|--------|-------|--------|-------|-------|--------|-------|--------|
| `Purisol Administrator` | 1 | 1 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 1 |

No other role has any access.

### 1.4. Controller lifecycle (`purisol_coupon_consumption_entry.py`)

| Hook | Responsibility |
|------|----------------|
| `before_insert` | Stamp `received_by = frappe.session.user`. |
| `validate` | Compute `total_coupons = len(self.coupons)`; reject empty child table (FR-030); reject duplicate `coupon` within `self.coupons` (FR-032); reject `has_warnings != 0` (FR-035); reject any row in `self.discrepancies_detected` (FR-035). |
| `before_submit` | Bulk-read live state of every referenced coupon; reject submit if any coupon doesn't exist (FR-031) or is already `Consumed` (FR-033). Aggregate all errors before raising. |
| `on_submit` | Per-row: write `status = Consumed`, `consumed_on = posting_datetime`, `consumed_by_delivery_man = delivery_man`, `consumption_entry = self.name` on each coupon via `frappe.db.set_value(..., update_modified=True)`. Then per distinct booklet: recompute `consumed_count` and `remaining_count`; if `consumed_count == 20` and booklet is `Sold`, save the booklet with `status = Depleted`, `depleted_on = posting_datetime` and add a `Comment`. All writes inside the submit transaction. |
| `on_cancel` | Per-row: clear `status = Available`, `consumed_on = NULL`, `consumed_by_delivery_man = NULL`, `consumption_entry = NULL` on each coupon. Then per distinct booklet: recompute aggregates; if booklet is `Depleted` and self is the trigger-of-record and recomputed `consumed_count < 20`, save with `status = Sold`, `depleted_on = NULL` and add a `Comment`. Otherwise just update aggregates. All writes inside the cancel transaction. |

### 1.5. Derived property

```python
@property
def posting_datetime(self):
    return frappe.utils.get_datetime(f"{self.posting_date} {self.posting_time}")
```

Used as `consumed_on` on every coupon and `depleted_on` on any newly-depleted booklet.

---

## 2. New DocType (child table) — `Purisol Coupon Consumption Item`

**Purpose**: One row per coupon being recorded in the parent entry. Stored rows are **mode-agnostic** — Mode A and Mode B write identical row shapes.

### 2.1. DocType-level properties

| Property | Value |
|----------|-------|
| `name` | `Purisol Coupon Consumption Item` |
| `module` | `Cx Purisol` |
| `istable` | `1` |
| `track_changes` | `1` |
| `engine` | `InnoDB` |

### 2.2. Fields

| # | fieldname | fieldtype | options | reqd | read_only | in_list_view | Notes |
|---|-----------|-----------|---------|------|-----------|--------------|-------|
| 1 | `coupon` | `Link` | `Purisol Coupon` | 1 | 0 | 1 | Search-indexed. The primary key of the row. |
| 2 | `booklet` | `Link` | `Purisol Coupon Booklet` | 0 | 1 | 1 | `fetch_from = coupon.booklet`. Auto-populated when `coupon` is set. |
| 3 | `customer` | `Link` | `Customer` | 0 | 1 | 1 | `fetch_from = coupon.booklet.customer`. May be empty if the parent booklet is not `Sold`. |

### 2.3. Controller (`purisol_coupon_consumption_item.py`)

Empty stub — no custom `validate` needed. All row-level constraints (no duplicates, existence, already-consumed check) are parent-level and live on `Purisol Coupon Consumption Entry`. The child table's existence is governed by the parent's permissions; direct writes are not exposed.

### 2.4. Why `booklet` and `customer` are stored and not just fetched

Frappe's `fetch_from` fires at form time and at `doc.set_missing_values()` — so the values are persisted on the row. Storing them (rather than recomputing on read) gives:

- Reports and print formats can render the row without joining back to `Purisol Coupon`.
- If a future phase renames or deletes a coupon (not that coupons are deletable today — permission forbids it), the historical row still carries the booklet / customer it referred to at submit time.
- Consistent with the Phase-2 pattern on `Purisol Custody Entry Booklet.booklet_status_at_entry` (snapshot-at-submit semantics).

---

## 3. New DocType (child table stub) — `Purisol Coupon Discrepancy Item`

**Purpose**: Reserved-empty child table hanging off `Purisol Coupon Consumption Entry.discrepancies_detected`. Phase 4 defines it minimally so Phase 5 can fill in real fields without schema churn on the parent.

### 3.1. DocType-level properties

| Property | Value |
|----------|-------|
| `name` | `Purisol Coupon Discrepancy Item` |
| `module` | `Cx Purisol` |
| `istable` | `1` |
| `track_changes` | `1` |
| `engine` | `InnoDB` |

### 3.2. Fields

| # | fieldname | fieldtype | reqd | read_only | Notes |
|---|-----------|-----------|------|-----------|-------|
| 1 | `notes` | `Small Text` | 0 | 0 | Placeholder field — not populated in Phase 4. Phase 5 will add real fields around this. |

### 3.3. Controller

Empty stub. The parent's `validate` enforces "no rows in Phase 4" — this DocType's presence is purely structural.

---

## 4. Controller widening on `Purisol Coupon` (existing)

### 4.1. State machine (Phase-4 rules)

```text
Available  ─→ Consumed       (Consumption Entry on_submit — Phase 4)
Available  ←─ Consumed       (Consumption Entry on_cancel — Phase 4)
```

### 4.2. Code change

Current (Phase 1):

```python
def validate(self):
    if self.status != "Available":
        frappe.throw(_("Coupon status must be 'Available' in this phase."))
    ...
```

Widened (Phase 4):

```python
_ALLOWED_STATUSES = {"Available", "Consumed"}
_ALLOWED_TRANSITIONS = {
    ("Available", "Consumed"),   # Consumption Entry submit
    ("Consumed", "Available"),   # Consumption Entry cancel
}

def validate(self):
    if self.status not in _ALLOWED_STATUSES:
        frappe.throw(_("Coupon status {0} is not allowed.").format(self.status))

    if not (1 <= (self.page_number or 0) <= 20):
        frappe.throw(_("Page number must be between 1 and 20."))

    prior = self.get_doc_before_save()
    if prior:
        for field in ("booklet", "page_number", "coupon_number"):
            if getattr(self, field) != getattr(prior, field):
                frappe.throw(_("Field {0} cannot be modified after creation.").format(field))

        if prior.status != self.status and (prior.status, self.status) not in _ALLOWED_TRANSITIONS:
            frappe.throw(
                _("Coupon status transition from {0} to {1} is not allowed.").format(
                    prior.status, self.status
                )
            )
```

### 4.3. Field write permissions

The three consumption-metadata fields remain `read_only = 1` on the JSON — they are never editable via the form. They are written exclusively by the Consumption Entry controller's `on_submit` / `on_cancel` via `frappe.db.set_value(..., update_modified=True)`, which bypasses form permissions but respects permission level (`permlevel = 0`).

### 4.4. No JSON change

`purisol_coupon.json` is not modified. All three consumption-metadata fields and the `status` options list already exist from Phase 1.

---

## 5. Controller widening on `Purisol Coupon Booklet` (existing)

### 5.1. State machine after Phase 4

```text
In Stock    ─→ In Custody   (Phase 2 — Custody Entry Assign)
In Stock    ─→ Sold          (Phase 3 — Sales Invoice submit)
In Custody  ─→ In Stock      (Phase 2 — Custody Entry Return)
In Custody  ─→ Sold          (Phase 3 — Sales Invoice submit)
Sold        ─→ In Stock      (Phase 3 — Sales Invoice cancel, no consumption)
Sold        ─→ Depleted      (Phase 4 — Consumption Entry submit drives consumed_count to 20) ← NEW
Depleted    ─→ Sold          (Phase 4 — Consumption Entry cancel drops consumed_count below 20, this entry was the trigger) ← NEW
```

### 5.2. Code change

Current (Phase 3):

```python
_ALLOWED_STATUSES = {"In Stock", "In Custody", "Sold"}
_ALLOWED_TRANSITIONS = {
    ("In Stock", "In Custody"),
    ("In Custody", "In Stock"),
    ("In Stock", "Sold"),
    ("In Custody", "Sold"),
    ("Sold", "In Stock"),
}
```

Widened (Phase 4):

```python
_ALLOWED_STATUSES = {"In Stock", "In Custody", "Sold", "Depleted"}
_ALLOWED_TRANSITIONS = {
    ("In Stock",   "In Custody"),
    ("In Custody", "In Stock"),
    ("In Stock",   "Sold"),
    ("In Custody", "Sold"),
    ("Sold",       "In Stock"),
    ("Sold",       "Depleted"),   # NEW — auto-depletion on 20th consumption
    ("Depleted",   "Sold"),       # NEW — auto-revert on cancel of the trigger entry
}
```

`validate` already enforces `status ∈ _ALLOWED_STATUSES` and `(prior.status, self.status) ∈ _ALLOWED_TRANSITIONS`; no code change needed beyond widening the two sets.

### 5.3. No JSON change

`purisol_coupon_booklet.json` is not modified. The `status` options list (`In Stock\nIn Custody\nSold\nDepleted`) and the `depleted_on` field already exist from Phase 1.

---

## 6. Validations in one place

### 6.1. Parent-level `validate` (runs on every save, including drafts)

| # | Rule | Location | On violation |
|---|------|----------|--------------|
| V1 | `coupons` must not be empty | `PurisolCouponConsumptionEntry.validate` | `frappe.throw(_("Consumption Entry must list at least one coupon."))` (FR-030) |
| V2 | No duplicate `coupon` in `coupons` | `PurisolCouponConsumptionEntry.validate` | `frappe.throw(_("Coupon {0} appears more than once in this entry.").format(name))` (FR-032) |
| V3 | `total_coupons` is set to `len(coupons)` | `PurisolCouponConsumptionEntry.validate` | — (pure compute) |
| V4 | `has_warnings == 0` | `PurisolCouponConsumptionEntry.validate` | `frappe.throw(_("has_warnings is reserved for Phase 5 and cannot be set."))` (FR-035, defensive) |
| V5 | `discrepancies_detected` is empty | `PurisolCouponConsumptionEntry.validate` | `frappe.throw(_("discrepancies_detected is reserved for Phase 5."))` (FR-035, defensive) |

### 6.2. Submit-time `before_submit` (runs inside the submit transaction)

All errors below are **aggregated** into a single message via `"<br>".join(errors)` so the Administrator sees every bad row on one rejection (matches the Phase-2 custody-entry validate pattern; spec SC-006).

| # | Rule | On violation |
|---|------|--------------|
| S1 | Every `coupon` resolves to an existing `Purisol Coupon` | `_("Coupon {0} does not exist.").format(name)` (FR-031) |
| S2 | Every `coupon` has current `status != "Consumed"` | `_("Coupon {0} is already Consumed (recorded on entry {1}).").format(name, prior_entry)` (FR-033) |

Link-integrity errors on `delivery_man` (Employee) and other Link fields are enforced by Frappe's default behaviour — no custom check needed.

### 6.3. Submit-time `on_submit` (side effects, no further validation)

Per row in `self.coupons`:

```
coupon.status                    = "Consumed"
coupon.consumed_on               = self.posting_datetime
coupon.consumed_by_delivery_man  = self.delivery_man
coupon.consumption_entry         = self.name
```

Per distinct booklet among `{row.booklet for row in self.coupons}`:

```
booklet.consumed_count  = count(Purisol Coupon WHERE booklet=name AND status="Consumed")
booklet.remaining_count = 20 - booklet.consumed_count
if booklet.consumed_count == 20 and booklet.status == "Sold":
    booklet.status       = "Depleted"
    booklet.depleted_on  = self.posting_datetime
    booklet.add_comment("Info", _("Depleted via {0}").format(self.name))
```

### 6.4. Cancel-time `on_cancel` (reversal)

Per row in `self.coupons`:

```
coupon.status                    = "Available"
coupon.consumed_on               = NULL
coupon.consumed_by_delivery_man  = NULL
coupon.consumption_entry         = NULL
```

Per distinct booklet among `{row.booklet for row in self.coupons}`:

```
booklet.consumed_count  = count(Purisol Coupon WHERE booklet=name AND status="Consumed")
booklet.remaining_count = 20 - booklet.consumed_count
if booklet.status == "Depleted" and self is the trigger-of-record and booklet.consumed_count < 20:
    booklet.status       = "Sold"
    booklet.depleted_on  = NULL
    booklet.add_comment("Info", _("Depletion reverted — entry {0} cancelled.").format(self.name))
```

"Trigger-of-record" = the most-recent non-cancelled (`docstatus = 1`) Consumption Entry whose `coupons.coupon.booklet == booklet.name` is `self.name` — checked via:

```python
latest = frappe.db.sql(
    """
    SELECT parent FROM `tabPurisol Coupon Consumption Item` item
    INNER JOIN `tabPurisol Coupon Consumption Entry` entry ON entry.name = item.parent
    WHERE item.booklet = %s AND entry.docstatus = 1 AND entry.name != %s
    ORDER BY entry.creation DESC LIMIT 1
    """,
    (booklet_name, self.name),
)
# If no other entry is a candidate, self was the trigger; fall through to revert.
# If another later entry exists but booklet.consumed_count < 20 after our revert, revert anyway.
```

If the revert path is taken but the booklet's `consumed_count` is still `20` (because another later entry also drove it to 20), the booklet stays `Depleted` — we do not revert. This is the FR-052 safety net.

### 6.5. Cancel-time integrity failure

If any database operation in `on_cancel` raises (e.g. a booklet write fails because the booklet has since been deleted, which should never happen but defensively matters), the raise propagates out and Frappe rolls the cancel transaction back. The Administrator sees the error message and no coupon or booklet is modified (FR-053).

---

## 7. Relationships diagram

```
            Purisol Coupon Consumption Entry  (new, submittable)
             ├── posting_date                  : Date
             ├── posting_time                  : Time
             ├── delivery_man                  → Employee
             ├── received_by                   → User   (auto-stamped)
             ├── total_coupons                 : Int    (derived)
             ├── has_warnings                  : Check  (reserved, always 0 in Phase 4)
             ├── notes                         : Small Text
             │
             ├── coupons (1:N)                 → Purisol Coupon Consumption Item  (new child)
             │       ├── coupon                → Purisol Coupon                    (1:1 write on submit)
             │       ├── booklet               → Purisol Coupon Booklet            (fetched)
             │       └── customer              → Customer                           (fetched, nullable)
             │
             └── discrepancies_detected (1:N)  → Purisol Coupon Discrepancy Item   (new child — Phase-5 stub)

            Purisol Coupon  (existing)
             ├── status                        : Available | Consumed
             ├── consumed_on                   : Datetime  (written on submit, cleared on cancel)
             ├── consumed_by_delivery_man      → Employee  (written on submit, cleared on cancel)
             └── consumption_entry             → Purisol Coupon Consumption Entry  (written on submit, cleared on cancel)

            Purisol Coupon Booklet  (existing)
             ├── status                        : In Stock | In Custody | Sold | Depleted
             ├── consumed_count                : Int        (recomputed on submit and cancel)
             ├── remaining_count               : Int        (= 20 - consumed_count)
             └── depleted_on                   : Datetime   (stamped on auto-depletion; cleared on auto-revert)
```

---

## 8. Fixtures / migrations

### 8.1. Fixtures

No new fixture files beyond the three DocType JSONs themselves (which ship as DocType code, not as `fixtures = [...]` entries in `hooks.py`). The existing `Purisol Administrator` role fixture already grants the permissions our new DocType JSONs reference — no role change needed.

### 8.2. `patches.txt`

Add one post-model-sync entry:

```
cx_purisol.patches.v0_4_0.widen_states_for_consumption
```

The patch is a no-op on fresh installs (logs a single `frappe.msgprint` / `print` for visibility). On upgraded sites it serves as a durable anchor ("this site was migrated through Phase 4"), matching the Phase-2 and Phase-3 patterns.

---

## 9. What is deliberately NOT changed

- **No change to `purisol_coupon.json`**. All three consumption-metadata fields already exist (reserved-empty since Phase 1).
- **No change to `purisol_coupon_booklet.json`**. `depleted_on` and the `Depleted` status option already exist since Phase 1.
- **No change to `purisol_settings.json`**. Phase 4 has no settings of its own.
- **No new role.** `Purisol Administrator` covers every Phase-4 interaction.
- **No new whitelisted API beyond `list_available_coupons` and `resolve_coupons`** — both are read-only helpers for the Mode A / Mode B UX; submit-time validation is authoritative.
- **No new fixtures JSON.** The three DocTypes' own JSONs declare their permissions inline.
- **No notification, no report, no discrepancy record** — deferred to Phases 5/6/7.
- **No bulk-day or background-job path.** Submit runs synchronously; the 200-coupon worst case fits comfortably in the gunicorn 120 s window.
