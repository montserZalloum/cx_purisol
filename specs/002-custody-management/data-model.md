# Phase 1 — Data Model: Custody Management

**Feature**: `002-custody-management` · **Date**: 2026-04-18

Phase 2 introduces two new DocTypes (`Purisol Custody Entry` and its child table `Purisol Custody Entry Booklet`) and makes a targeted, additive change to one Phase-1 DocType (`Purisol Coupon Booklet`). The `Employee` DocType is leveraged as-is from ERPNext; no modifications.

Frappe-specific DocType flags:
- `track_changes = 1` on every new custom DocType (constitution IV).
- `is_submittable = 1` on `Purisol Custody Entry` (constitution IV: state-changing action must be a submittable record).
- `istable = 1` on `Purisol Custody Entry Booklet` (child table).

---

## 1. Purisol Custody Entry (submittable)

Justification for custom DocType (per constitution II): ERPNext has no existing concept that models physical custody of a company-internal asset transferring between employees. `Stock Entry` is the closest analogue but is tightly coupled to stock/warehouse accounting, which is explicitly not how booklets are modelled (non-stock Item per PRD §9.1). A dedicated submittable DocType keeps the custody chain clean, auditable, and decoupled from stock semantics.

**Naming**: `autoname = "PCE-.YYYY.-.#####"` (year-scoped, zero-padded 5 digits).
**Module**: `Cx Purisol`.
**DocType flags**: `track_changes = 1`, `is_submittable = 1`.

### Fields

| Field name | Type | Required | Default | Read-only | Notes |
|------------|------|----------|---------|-----------|-------|
| `entry_type` | Select | Yes | — | No (until submit) | Options: `Assign \n Transfer \n Return`. Drives all per-type validation. |
| `from_delivery_man` | Link → Employee | Conditional³ | — | No (until submit) | Required for `Transfer` and `Return`; must be unset for `Assign`. |
| `to_delivery_man` | Link → Employee | Conditional³ | — | No (until submit) | Required for `Assign` and `Transfer`; must be unset for `Return`. |
| `entry_datetime` | Datetime | Yes | `now()` | No (until submit) | When the physical custody change happened. Administrator may backdate. |
| `notes` | Small Text | No | — | No (until submit) | Free text. |
| `created_by` | Link → User | Yes | `frappe.session.user` | Yes | Populated in `before_insert`. |
| `booklets` | Table → Purisol Custody Entry Booklet | Yes | — | No (until submit) | Child table of affected booklets. Must be non-empty; no booklet may appear twice. |

³ Required-ness is enforced both by `mandatory_depends_on` (declarative, Frappe form-level) and by `validate` (authoritative, Python server-side). The pair, together with the "forbid when not applicable" rule, is:
- `Assign`: `to_delivery_man` required; `from_delivery_man` forbidden.
- `Transfer`: both required; `from_delivery_man != to_delivery_man`.
- `Return`: `from_delivery_man` required; `to_delivery_man` forbidden.

### Validation rules (`validate` hook)

Evaluated in order; all failures collected, single `frappe.throw(_(…))` at the end with the full list.

1. **Child table shape**:
   - `len(self.booklets) > 0` else `_("Custody Entry must list at least one booklet.")`.
   - No duplicate `booklet` across child rows else `_("Booklet {0} is listed more than once in this entry.").format(name)`.
2. **Delivery-man presence per type** (see ³ above).
3. **Per-booklet source-state check** (one `frappe.get_all("Purisol Coupon Booklet", filters={"name": ["in", …]}, fields=["name", "status", "current_delivery_man"])` to avoid N+1):
   - `Assign`: booklet `status == "In Stock"` else `_("Booklet {0} is not In Stock (current: {1}).")`.
   - `Transfer` / `Return`: booklet `status == "In Custody"` and `current_delivery_man == self.from_delivery_man` else `_("Booklet {0} is held by {1} (current holder), not by {2}.")` or `_("Booklet {0} is not In Custody (current: {1}).")`.
4. **Self-transfer check** (`Transfer` only): `from_delivery_man != to_delivery_man` else `_("A Transfer from a delivery man to themselves is not meaningful.")`.

Validation runs on every save of a draft *and* re-runs on submit (Frappe framework behaviour). It does **not** run on cancel — cancel has its own pre-condition check (§5).

### `before_submit` (snapshot)

For each child row, populate:
- `booklet_status_at_entry` = booklet's current `status` at this instant.
- `delivery_man_at_entry` = booklet's current `current_delivery_man` at this instant (may be null for `Assign`).

This is done in a single batched query and `frappe.db.set_value(..., update_modified=False)` per child row. The snapshot is needed for cancellation reversal.

### `on_submit`

For each child row, atomically (within the request transaction):
- `Assign`: `booklet.status = "In Custody"`, `booklet.current_delivery_man = self.to_delivery_man`.
- `Transfer`: `booklet.status` stays `"In Custody"`, `booklet.current_delivery_man = self.to_delivery_man`.
- `Return`: `booklet.status = "In Stock"`, `booklet.current_delivery_man = None`.

Each booklet is saved via `booklet.save(ignore_permissions=True)` which runs the booklet's widened `validate` (defense in depth — see the Phase-1 DocType amendment in §4 below).

### `on_cancel` (cancellation reversal with pre-condition)

For each child row:
1. Re-fetch current booklet `status`, `current_delivery_man`.
2. Compute expected post-submit state from `self.entry_type`:
   - `Assign` / `Transfer`: expected `status = "In Custody"`, `current_delivery_man = self.to_delivery_man`.
   - `Return`: expected `status = "In Stock"`, `current_delivery_man = None`.
3. If current ≠ expected, collect mismatch: `_("Cannot cancel: booklet {0} has since moved (current status: {1}, current holder: {2}). Cancel the subsequent custody event first.").format(...)`.
4. If all child rows are in their expected post-states, iterate again and revert:
   - `booklet.status = row.booklet_status_at_entry`
   - `booklet.current_delivery_man = row.delivery_man_at_entry`
   - `booklet.save(ignore_permissions=True)`.
5. If any mismatch existed, `frappe.throw` with the collected list — cancel aborts.

### Permissions

- `Purisol Administrator`: `read = 1, write = 1, create = 1, submit = 1, cancel = 1, amend = 0, delete = 0`.
- `System Manager`: inherits standard rights.

### Relationships

- Many → one `Employee` via `from_delivery_man` / `to_delivery_man`.
- One → many `Purisol Custody Entry Booklet` (child).
- Indirectly: every child row references a `Purisol Coupon Booklet`, the true target of all side-effects.

---

## 2. Purisol Custody Entry Booklet (child table)

Justification for custom DocType (per constitution II): a child table is the idiomatic Frappe way to attach a variable-length list of records to a parent. No ERPNext primitive fits.

**Module**: `Cx Purisol`.
**DocType flags**: `istable = 1`, `track_changes = 1`.

### Fields

| Field name | Type | Required | Default | Read-only | Notes |
|------------|------|----------|---------|-----------|-------|
| `booklet` | Link → Purisol Coupon Booklet | Yes | — | No (until parent submit) | The booklet affected by this row. |
| `booklet_status_at_entry` | Data | Yes (at submit) | — | Yes | Snapshot of `Purisol Coupon Booklet.status` at parent `before_submit`. Used for cancel reversal. |
| `delivery_man_at_entry` | Link → Employee | No | — | Yes | Snapshot of `Purisol Coupon Booklet.current_delivery_man` at parent `before_submit`. May be null for `Assign` source (booklet was `In Stock`). |

### Validation rules

- `booklet` must reference an existing `Purisol Coupon Booklet` (Frappe Link field semantics).
- Uniqueness across rows within one parent enforced by the parent's `validate` (see §1), not by the child itself.

### Relationships

- Many → one `Purisol Custody Entry` (parent).
- Many → one `Purisol Coupon Booklet`.
- Many → one `Employee` (via `delivery_man_at_entry`, optional).

---

## 3. Employee (ERPNext standard, leveraged)

Referenced from `from_delivery_man`, `to_delivery_man`, `delivery_man_at_entry`, and `Purisol Coupon Booklet.current_delivery_man`. No modifications to the `Employee` DocType; no custom fields added. Delivery-man representation in the system is the standard ERPNext `Employee` record, created through the standard HR onboarding flow. This feature neither creates nor validates Employee records themselves — it only references them.

---

## 4. Purisol Coupon Booklet (Phase-1 DocType; widened in this phase)

No schema change. The DocType JSON (fields, types, defaults, permissions) is unchanged from Phase 1 — the `current_delivery_man` field was already declared.

Three controller-level changes land in this phase:

1. **Widened `validate` guard**: the Phase-1 rule "reject any `status` other than `In Stock`" becomes "reject any `status` not in `{In Stock, In Custody}`". `Sold` and `Depleted` remain rejected with the same `frappe.ValidationError` (deferred to Phases 3 and 4 respectively). Transition correctness across the allowed pair is enforced by the Custody Entry controller, not by the booklet itself (one-way data flow).
2. **`current_delivery_man` form-level read-only**: a new `purisol_coupon_booklet.js` sets `frm.set_df_property("current_delivery_man", "read_only", 1)` on `refresh`. The server remains free to write, as required by the Custody Entry controller.
3. **`status` form-level read-only** (consolidated): the same client script locks `status` as well, so Administrators cannot hand-edit either field from the desk. Both changes are done only from the Custody Entry controller (and, in later phases, from Sales Invoice / Consumption Entry controllers).

A `patches.txt` entry for the phase is added (no data migration; the patch is effectively a version marker). The entry ensures upgraded sites re-run any necessary DocType-level refresh (e.g., re-installing the client script).

---

## State Transitions (Phase 2 activation)

Booklet status:

```
In Stock ←→ In Custody
```

Concretely:

| From | To | Trigger | Controller |
|------|-----|---------|------------|
| `In Stock` | `In Custody` | Custody Entry submit, type `Assign` | `purisol_custody_entry.on_submit` |
| `In Custody` | `In Custody` | Custody Entry submit, type `Transfer` | `purisol_custody_entry.on_submit` |
| `In Custody` | `In Stock` | Custody Entry submit, type `Return` | `purisol_custody_entry.on_submit` |
| `In Custody` | `In Stock` | Custody Entry cancel (of an `Assign` where nothing moved after) | `purisol_custody_entry.on_cancel` |
| `In Stock` | `In Custody` | Custody Entry cancel (of a `Return` where nothing moved after) | `purisol_custody_entry.on_cancel` |

Blocked in this phase (deferred):

| From | To | Status in Phase 2 |
|------|-----|-------------------|
| `In Custody` / `In Stock` | `Sold` | Rejected (Phase 3 unlocks) |
| `Sold` | `Depleted` | Rejected (Phase 4 unlocks) |
| Any | Any reverse from a terminal state | Forbidden by constitution III |

Coupon status (`Available`, `Consumed`) is **unaffected** by this phase — Custody Entries do not touch coupon records at all.

---

## Migration Plan

- **Fixtures**: `Purisol Custody Entry` + `Purisol Custody Entry Booklet` DocType JSONs install via standard Frappe fixture sync on `bench migrate`. Role permissions for `Purisol Administrator` on these DocTypes ship as additional entries in the existing role-permissions fixture.
- **Patches**: one `patches.txt` entry for this phase, located at `cx_purisol/patches/v0_2_0/widen_booklet_validate_allowed_states.py`. The patch is a no-op on fresh installs; on upgraded sites, it `bench migrate`-invokes a module that confirms the widened allowed-state set is in effect and installs the new client script. No data is mutated.
- **Client script**: `purisol_coupon_booklet.js` is added as a new file alongside the Phase-1 DocType; Frappe picks it up automatically on `bench build`.
- **Query Report**: `Current Custody by Delivery Man` installs as a Frappe Report fixture (JSON) under the module's `report/` directory.

---

## Referential Integrity

- `Purisol Custody Entry Booklet.booklet` is a **non-nullable Link**. Frappe's Link semantics prevent deletion of a referenced `Purisol Coupon Booklet` (booklets are already `delete = 0` at the permission level; this is belt-and-suspenders).
- `Purisol Custody Entry.from_delivery_man` / `to_delivery_man` / `Purisol Custody Entry Booklet.delivery_man_at_entry` are Links to `Employee`. Employee deletion would already be blocked by Frappe if any of these Links references them; no explicit referential-integrity logic is added.
- Cancelling a Custody Entry does **not** delete any row — Frappe's `docstatus = 2` makes the entry read-only-cancelled, with the full audit preserved.

---

## Invariants Maintained by This Phase

1. Every `In Custody` booklet has exactly one non-null `current_delivery_man`.
2. Every `In Stock` booklet has a null `current_delivery_man`.
3. For any booklet, replaying all Custody Entries referencing it (in `entry_datetime` order, docstatus = 1) reconstructs its current `status` and `current_delivery_man`. This is the spec FR-041 guarantee.
4. For any cancelled Custody Entry, the booklets it references are in the state they were *before* that entry applied — *unless* a subsequent Custody Entry moved them (in which case the cancel is rejected, not silently dropped).
5. The Phase-1 numbering invariant (`WP-K ↔ CP-((K-1)*20+1)…CP-(K*20)`) is untouched — this phase does not create or modify any coupon record.
