# Phase 1 — Data Model: Core Data Model

**Feature**: `001-core-data-model` · **Date**: 2026-04-18

All three entities are Frappe DocTypes delivered as fixtures. Field lists below reflect the **full MVP schema** (PRD §7.1, §7.2, §7.6); fields marked `(reserved for later phases)` are declared now but are neither populated nor required by Phase 1 logic.

Frappe-specific DocType flags:
- `track_changes = 1` on every custom DocType (constitution IV).
- `is_submittable = 0` on all three (state transitions in later phases happen through submittable Consumption/Custody entries; booklets and coupons themselves are state-managed but not submittable — see PRD §7.1 which explicitly specifies "Is Submittable: No").
- `issingle = 1` on `Purisol Settings`.

---

## 1. Purisol Settings (Singleton)

Justification for custom DocType (per constitution II): ERPNext has no existing singleton that models Purisol's domain configuration (thresholds, coupon-item binding, warning toggle). Standard ERPNext `Singles` stores only generic key/value; a dedicated typed singleton gives typed fields, role-scoped access, and a UI form.

| Field name | Type | Required | Default | Notes |
|------------|------|----------|---------|-------|
| `coupon_item` | Link → Item | No¹ | — | Item representing the coupon booklet. Required in Phase 3 (sale); optional here. |
| `default_price_list` | Link → Price List | No | `"Standard Selling"` | Fallback Price List for sales. |
| `customer_low_stock_threshold` | Int | Yes | `3` | Triggers Customer Low-Stock notification (Phase 5). |
| `warehouse_low_stock_threshold` | Int | Yes | `5` | Triggers Warehouse Low-Stock notification (Phase 5). |
| `employee_liability_account` | Link → Account | No¹ | — | Used in Phase 4 discrepancy resolution. |
| `discrepancy_offset_account` | Link → Account | No¹ | — | Used in Phase 4. |
| `default_cash_account` | Link → Account | No¹ | — | Used in Phase 4 payment entries. |
| `enable_consumption_warnings` | Check | Yes | `1` | Toggles discrepancy detection (Phase 4). |

¹ Optional *in this phase*. Later phases will mark these required at the phase-specific action, not at DocType level, to keep the fresh-install bootstrap workable.

**Validation rules (Phase 1)**:
- Singleton: structural via `issingle = 1`; any attempt to `insert` a second document raises `frappe.ValidationError` (spec FR-001).
- Threshold fields must be non-negative integers (Frappe `Int` default). Ranges are not further constrained in Phase 1.

**Permissions**:
- `Purisol Administrator`: `read = 1`, `write = 1`. No create/delete (structural on a singleton).
- `System Manager`: inherits standard rights.

**Relationships**: None (standalone). Links out only.

---

## 2. Purisol Coupon Booklet

**Naming**: `autoname = "WP-.#####"` — strictly sequential via `tabSeries`, zero-padded 5 digits.
**Module**: `Cx Purisol`.
**DocType flags**: `track_changes = 1`, `is_submittable = 0`.

### Fields

| Field name | Type | Required | Default | Read-only | Notes |
|------------|------|----------|---------|-----------|-------|
| `booklet_number` | Data | Yes | — | Yes | Mirror of `name`; populated in `autoname`. |
| `status` | Select | Yes | `In Stock` | Yes (Phase 1)² | Options: `In Stock \n In Custody \n Sold \n Depleted`. |
| `current_delivery_man` | Link → Employee | No | — | No | *Reserved for later phases.* |
| `customer` | Link → Customer | No | — | No | *Reserved for later phases.* |
| `sold_on` | Datetime | No | — | No | *Reserved for later phases.* |
| `sales_invoice` | Link → Sales Invoice | No | — | No | *Reserved for later phases.* |
| `depleted_on` | Datetime | No | — | No | *Reserved for later phases.* |
| `first_coupon` | Data | Yes | — | Yes | Computed on create: `CP-{(K-1)*20+1:05d}` where `K` is the parsed booklet number. |
| `last_coupon` | Data | Yes | — | Yes | Computed on create: `CP-{K*20:05d}`. |
| `total_coupons` | Int | Yes | `20` | Yes | Always 20 in Phase 1. |
| `consumed_count` | Int | Yes | `0` | Yes | Always 0 in Phase 1. |
| `remaining_count` | Int | Yes | `20` | Yes | Always 20 in Phase 1; `= total_coupons - consumed_count`. |
| `batch_id` | Data | No | — | No | Optional generation-batch identifier. |
| `notes` | Small Text | No | — | No | Free text. |

² In Phase 1, `status` is read-only in the UI so no one can hand-edit it. The Python `validate` guard rejects any value other than `In Stock` in this phase. The option set is fixed now so later phases only unlock transitions, not add states.

### Validation rules (`validate` + `autoname` hooks)

- `autoname`: compute `booklet_number = self.name` once the series has allocated a value, and derive `first_coupon` / `last_coupon` from the booklet's parsed integer.
- `validate`:
  - Reject any `status` other than `In Stock` in this phase (blocking, constitution V).
  - Reject attempts to modify `first_coupon`, `last_coupon`, `total_coupons`, `booklet_number`, `batch_id` after initial save (constitution III + spec FR-009/FR-010). Enforced by checking `self.get_doc_before_save()`.
  - Accept edits to `notes` and (in later phases) the reserved fields.

### Permissions

- `Purisol Administrator`: `read = 1, write = 1`, `create = 0`, `delete = 0`. (Creation is via the `purisol_generate_booklets` API, which uses `ignore_permissions=True` after checking the caller holds this role.)
- `System Manager`: inherits standard rights.

### Relationships

- One → many `Purisol Coupon` (via `Purisol Coupon.booklet`). Exactly 20 children by invariant.
- Link fields reserved above point to `Employee`, `Customer`, `Sales Invoice`.

---

## 3. Purisol Coupon

**Naming**: `autoname = "CP-.#####"` — strictly sequential system-wide, not reset per booklet.
**Module**: `Cx Purisol`.
**DocType flags**: `track_changes = 1`, `is_submittable = 0`.

### Fields

| Field name | Type | Required | Default | Read-only | Notes |
|------------|------|----------|---------|-----------|-------|
| `coupon_number` | Data | Yes | — | Yes | Mirror of `name`. |
| `booklet` | Link → Purisol Coupon Booklet | Yes | — | Yes | Parent booklet. Immutable after creation. |
| `page_number` | Int | Yes | — | Yes | 1–20. Immutable after creation. |
| `status` | Select | Yes | `Available` | Yes (Phase 1)² | Options: `Available \n Consumed`. |
| `consumed_on` | Datetime | No | — | No | *Reserved for later phases.* |
| `consumed_by_delivery_man` | Link → Employee | No | — | No | *Reserved for later phases.* |
| `consumption_entry` | Link → Purisol Coupon Consumption Entry | No | — | No | *Reserved for later phases. Link target DocType does not yet exist; the field is stored as `Link` with the target name as a string — Frappe tolerates this until the target DocType is installed.* |

### Validation rules

- `validate`:
  - Reject any `status` other than `Available` in this phase.
  - Reject modifications to `booklet`, `page_number`, `coupon_number` after initial save.
  - Enforce `1 ≤ page_number ≤ 20`.

### Permissions

- `Purisol Administrator`: `read = 1`, `write = 0` (Phase 1: coupons are not directly editable — they will be touched only via Consumption Entry in Phase 4), `create = 0`, `delete = 0`.
- `System Manager`: inherits standard rights.

### Relationships

- Many → one `Purisol Coupon Booklet` (required).
- Reserved link to `Employee` and to `Purisol Coupon Consumption Entry` (later phase).

---

## Numbering Invariant

For every booklet with name `WP-{K:05d}`, its 20 child coupons have names `CP-{(K-1)*20+1:05d}` … `CP-{K*20:05d}` and `page_number` values `1` … `20` respectively, in that order.

This invariant is enforced **at generation time** (the generation code computes names deterministically from `K`) and **verified by tests**:

- `tests/test_numbering.py` — unit verification of the pure function.
- `tests/test_booklet_generation.py` — integration verification of the invariant after real generation (sync and async).

The invariant is not additionally enforced by DocType-level validation (cross-DocType consistency rules are expensive on every save and the generation path is the single write surface). If a future phase introduces another write path for coupons, that path will be responsible for preserving the invariant.

---

## State Transitions (deferred)

Status domains are frozen now:

- `Purisol Coupon Booklet.status`: `In Stock → In Custody → (In Custody↔Sold) → Depleted`. Phase 1 can only create in `In Stock`; all transitions out of `In Stock` are Phase 2+ work.
- `Purisol Coupon.status`: `Available → Consumed`. Phase 1 can only create in `Available`; transition is Phase 4 work.

Phase 1's `validate` hooks reject any value other than the initial state (blocking error, constitution III + V).

---

## Migration Plan

No `patches.txt` entries are required: the schema lands as DocType JSON fixtures and is installed via `bench install-app cx_purisol` / `bench migrate`. The `Purisol Administrator` role and the `Purisol Settings` singleton are created via fixtures on first migrate.

Later phases will add submittable entry DocTypes (Custody, Consumption, Discrepancy) and will wire in reserved Link targets (e.g. `Purisol Coupon Consumption Entry`) — at which point the coupon's `consumption_entry` link resolves naturally, without a schema change to `Purisol Coupon`.
