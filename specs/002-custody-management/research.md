# Phase 0 — Research: Custody Management

**Feature**: `002-custody-management` · **Date**: 2026-04-18

All items are Phase-2 scoped. No `[NEEDS CLARIFICATION]` markers remain in the spec; this research consolidates the design decisions that back the plan.

---

## 1. Submittable DocType for Custody Events

**Decision**: Model each custody event as a single submittable DocType `Purisol Custody Entry` with `is_submittable = 1`, `track_changes = 1`, and `autoname = "PCE-.YYYY.-.#####"`. Year-scoped sequential numbering matches PRD §6.3 and keeps the naming visually distinct from `WP-#####` and `CP-#####`.

**Rationale**:
- Constitution IV: every state-changing action on domain objects must be represented by a submittable record — never a silent field update. The booklet's `status` and `current_delivery_man` fields become caches derived from Custody Entries.
- Frappe's submittable doc semantics give us `docstatus` (draft = 0, submitted = 1, cancelled = 2), immutability after submit, a native cancel path, and audit via `tabVersion`.
- Year scope on the naming prefix keeps the sequence bounded per year (simpler operational inspection, cleaner reports).
- A single DocType with an `entry_type` discriminator is simpler than three separate DocTypes for Assign/Transfer/Return — the three types share 95% of their fields and validation shape, and the discriminator keeps the audit log homogeneous.

**Alternatives considered**:
- **Three separate DocTypes** (`Purisol Assign Entry`, `Purisol Transfer Entry`, `Purisol Return Entry`): rejected — triples the maintenance burden, fragments the "Current Custody" audit chain, and makes cross-type reporting (e.g., "all custody events for this booklet") harder.
- **Non-submittable tracking record**: rejected — violates constitution IV ("state-changing action MUST be represented by a submittable record"). The cancel path is also critical for operational correctness.
- **Embedding custody entries as a child table on the booklet**: rejected — a custody *event* is shop-level (it groups many booklets under one act of handoff). Representing it as per-booklet children would force one row per booklet per event, losing the "one submit per handoff" audit property (spec SC-007).

---

## 2. Child Table with Pre-State Snapshot

**Decision**: The child table `Purisol Custody Entry Booklet` (child of `Purisol Custody Entry`, `istable = 1`) carries one row per booklet in the entry. Each row captures:
- `booklet` → Link to `Purisol Coupon Booklet` (required).
- `booklet_status_at_entry` → Data (read-only, snapshotted).
- `delivery_man_at_entry` → Link to `Employee` (read-only, snapshotted, may be null for booklets that were `In Stock`).

The snapshot is filled automatically during `before_submit` (after validation, before booklet writes). Users do not populate these fields by hand.

**Rationale**:
- On cancel, the controller must know what the booklet looked like *before* this entry applied, so it can restore that state. Recomputing it from earlier Custody Entries is possible but expensive and brittle (one cancel would require re-playing history for every listed booklet). A snapshot makes reversal a simple field assignment.
- The snapshot also enables a critical safety check (§5 below): if the booklet's current state no longer matches this entry's *post-state*, cancellation is rejected with a precise error.
- PRD §7.3 specifies `booklet_status_at_entry` explicitly; the plan extends it with `delivery_man_at_entry` for symmetric reversal. The extension is semantically identical — a pre-state snapshot for audit and reversal — and keeps the child table the single source of reversal data.

**Alternatives considered**:
- **Snapshot stored separately on a parallel DocType**: rejected — introduces a DocType that lives only to shadow the child table, with no independent lifecycle.
- **Rely on `tabVersion` to reconstruct prior state during cancel**: rejected — `tabVersion` is audit-oriented, not a primary data source; parsing diff payloads is fragile and couples controller logic to Frappe internals.
- **Re-compute prior state from the preceding Custody Entry during cancel**: rejected — requires ordered-entry scanning, which is slower and races against simultaneous new entries.

---

## 3. Validation Strategy

**Decision**: All per-entry-type validation happens in the `validate` hook of `Purisol Custody Entry`. Validation is exhaustive and ordered as:

1. Normalize the child table: reject empty list, reject duplicate booklets.
2. Validate required-field presence by `entry_type`:
   - `Assign`: require `to_delivery_man`; forbid `from_delivery_man`.
   - `Transfer`: require both; reject `from == to`.
   - `Return`: require `from_delivery_man`; forbid `to_delivery_man`.
3. For each booklet, fetch current `status` and `current_delivery_man` (single `frappe.get_all` with `for_update=False` during validate — locking happens at submit).
4. Apply the type-specific source-state rule:
   - `Assign`: `status == "In Stock"`.
   - `Transfer`: `status == "In Custody"` and `current_delivery_man == from_delivery_man`.
   - `Return`: `status == "In Custody"` and `current_delivery_man == from_delivery_man`.
5. Collect every failure, then `frappe.throw(_(…))` with a message that names the booklet, its actual status, and (for Transfer/Return) its actual holder.

Errors use `frappe.throw` (blocking) per constitution V.

**Rationale**:
- Frappe runs `validate` before `before_submit`/`on_submit`, so failing here prevents any booklet write. Atomicity (spec FR-020) is a natural consequence.
- Collecting all failures before throwing (rather than failing on first) gives the Administrator a complete punch list in one pass — substantially better UX for a 50-booklet entry.
- Reading status/holder in `validate` (without `for_update`) is deliberate: optimistic locking at submit time (§6) ensures correctness even if another submit lands between `validate` and `on_submit`.

**Alternatives considered**:
- **Check rules inside `on_submit` only**: rejected — then a failure aborts the submit after some booklets have been modified, contradicting "all-or-nothing" unless we also rely on transaction rollback. Running in `validate` catches errors earlier and produces cleaner Frappe default UX (the red toast appears before any transaction starts).
- **Fail-fast on first error**: rejected — degrades UX for multi-booklet entries where several rows are wrong.

---

## 4. Atomic Submit: Writes via the Frappe Transaction

**Decision**: `on_submit` iterates the child table and for each row:
1. `frappe.get_doc("Purisol Coupon Booklet", row.booklet)` — reloads the booklet under the request's transaction.
2. Captures the pre-state into the child row (`booklet_status_at_entry`, `delivery_man_at_entry`) via `frappe.db.set_value(..., update_modified=False)` on the child row — snapshotting. (In practice this happens in `before_submit`; see §2.)
3. Applies the type-specific post-state:
   - `Assign`: `status = "In Custody"`, `current_delivery_man = self.to_delivery_man`.
   - `Transfer`: `status = "In Custody"`, `current_delivery_man = self.to_delivery_man`.
   - `Return`: `status = "In Stock"`, `current_delivery_man = None`.
4. `booklet.save(ignore_permissions=True)` — triggers the booklet's `validate` (widened in this phase), which confirms the transition is allowed.

All writes share the request's single transaction. A late-stage exception raises to Frappe, which rolls back the transaction — no partial state is visible to any subsequent reader.

**Rationale**:
- Uses the existing Frappe primitive (request-scoped transaction) rather than inventing a nested transaction mechanism.
- `booklet.save()` (rather than `frappe.db.set_value`) ensures the Phase-1 booklet `validate` runs and will catch any illegal value the Custody Entry might emit (defense in depth — if a future refactor introduces a bug in Custody Entry controller logic, the Booklet's own invariants still hold).
- `ignore_permissions=True` is justified because the caller already passed the Custody Entry's DocType-level submit perm — but the Booklet DocType's Phase-1 `create=0, write=1, delete=0` perms mean a normal write would succeed anyway; `ignore_permissions=True` is defensive.

**Alternatives considered**:
- **Raw `frappe.db.set_value`** on each booklet: rejected — bypasses the booklet's `validate` hook, undermining defense-in-depth; also bypasses `track_changes` diff capture.
- **Per-booklet savepoints** (like Phase 1's generation): rejected — Phase 1 needed per-booklet commits because a 1,000-booklet batch was possible; here the worst-case entry is ~50 booklets, well within a single transaction. Savepoints add complexity without benefit.

---

## 5. Cancellation with Pre-Condition Check

**Decision**: `on_cancel` iterates the child table and for each row:
1. Fetches the booklet's current `status` and `current_delivery_man`.
2. Computes the expected post-submit state from `self.entry_type` + `self.to_delivery_man` / (None for Return):
   - `Assign`: expected `status = "In Custody"`, `current_delivery_man = self.to_delivery_man`.
   - `Transfer`: expected `status = "In Custody"`, `current_delivery_man = self.to_delivery_man`.
   - `Return`: expected `status = "In Stock"`, `current_delivery_man = None`.
3. If current state ≠ expected, `frappe.throw(_(…))` naming the booklet and the mismatch — preserves spec FR-031 ("rejected if reversal would conflict").
4. If current state = expected, revert the booklet to `(booklet_status_at_entry, delivery_man_at_entry)` from the snapshot via `booklet.save(ignore_permissions=True)`.

Collect mismatches; if any exist, throw once with the full list.

**Rationale**:
- This is the precise semantics spec FR-030 / FR-031 require: reversal is safe only if nothing has moved since.
- The check relies solely on fields already captured on the Custody Entry (`entry_type`, `to_delivery_man`) plus the snapshot — no dependency on other entries' ordering or state.
- If a future subsequent Custody Entry has moved a booklet onward, the Administrator must first cancel that later entry (or transfer the booklet back) before cancelling this one. That constraint is the chain-of-custody invariant; violating it would produce an inconsistent audit trail.

**Alternatives considered**:
- **Force-overwrite on cancel** (ignore current state): rejected — breaks audit integrity and lets cancellation silently discard a subsequent handoff.
- **No cancel support** (require a reverse Custody Entry instead): rejected — Frappe's submittable-doc model provides cancel natively; not exposing it is surprising and forces Administrators to construct reverse entries manually for simple mistakes. The spec explicitly requires cancel (FR-030, edge case "Cancellation of a submitted Custody Entry").

---

## 6. Concurrency Safety

**Decision**: Rely on Frappe's existing optimistic locking (`modified` timestamp per document). When two Custody Entries touching the same booklet submit concurrently:
- The first `booklet.save()` commits; the booklet's `modified` timestamp advances.
- The second `booklet.save()` sees a stale `modified` (loaded earlier in its `on_submit`) and raises `frappe.TimestampMismatchError` — Frappe aborts the second transaction.
- The second Administrator sees a clear error and retries (or investigates, depending on severity).

No additional locking primitives (SELECT FOR UPDATE, advisory locks) are introduced.

**Rationale**:
- Works for the expected concurrency level (at most a handful of simultaneous administrators; most sites have one).
- Uses a mechanism already battle-tested across the Frappe ecosystem.
- Satisfies spec edge case "Concurrent custody changes": exactly one succeeds, the other is rejected, state and audit trail remain consistent.

**Alternatives considered**:
- **`SELECT ... FOR UPDATE` on each booklet in `validate`**: rejected — holds row locks across the validate-to-submit window, which can be long if the Administrator pauses; increases deadlock risk.
- **Application-level queue** that serializes custody submits: rejected — over-engineered for the expected concurrency profile; adds a new moving part (worker, queue, retry) for a problem Frappe already solves.

---

## 7. Widening the Phase-1 Booklet Validator

**Decision**: Modify `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/purisol_coupon_booklet.py`:
- Replace the Phase-1 guard `if self.status != "In Stock": raise` with:
  - Allowed states: `{"In Stock", "In Custody"}`.
  - Disallowed-in-this-phase states `{"Sold", "Depleted"}` continue to raise `frappe.ValidationError` (they're unlocked in Phases 3 and 4 respectively).
  - Reject any transition other than `In Stock ↔ In Custody` by consulting `self.get_doc_before_save()`.
- Keep `current_delivery_man` editable on the record (no `read_only = 1` at the DocType level — that would prevent the controller writes). Instead, mark the field as read-only **in the form** using a tiny client script (`purisol_coupon_booklet.js`) that sets `frm.set_df_property("current_delivery_man", "read_only", 1)`. The server remains free to write.
- Add one `patches.txt` entry pointing to a no-op patch module that confirms the new allowed-state set is in effect — required by the constitution's migration-safety rule even though the data change is zero.

**Rationale**:
- Constitution III: disallowed transitions must raise, not silently succeed. The widened guard keeps that semantics, only widens the allowed set.
- `read_only` at the DocType level would block the controller too; the form-script technique is the Frappe-idiomatic way to lock a field in the UI while keeping it server-writable.
- The `patches.txt` entry documents the migration intent even when no data is mutated — keeps the release audit honest.

**Alternatives considered**:
- **Leave the Phase-1 guard unchanged and let Custody Entry bypass it with `frappe.db.set_value`**: rejected — bypasses the booklet's `validate` (loses defense-in-depth and `track_changes` diffs).
- **Mark `status` write-only to a specific role**: rejected — Frappe doesn't support field-level role scoping cleanly; the form-script approach is simpler and has the same effect for the Administrator (the only user with write access).

---

## 8. "Current Custody by Delivery Man" — Report Type Choice

**Decision**: Ship as a Frappe **Query Report** named `Current Custody by Delivery Man` under the `Cx Purisol` module. The report queries `Purisol Coupon Booklet` filtered to `status = "In Custody"`, with columns:

| Column | Type | Source |
|--------|------|--------|
| `current_delivery_man` | Link (Employee) | `Purisol Coupon Booklet.current_delivery_man` |
| `booklet` | Link (Purisol Coupon Booklet) | `name` |
| `days_in_custody` | Int | `DATEDIFF(NOW(), MAX(custody_entry.entry_datetime))` from the most recent `Purisol Custody Entry` that references this booklet (docstatus = 1) |
| `customer` | Link (Customer) | `Purisol Coupon Booklet.customer` (null in this phase; present for forward-compat with Phase 3) |
| `batch_id` | Data | `Purisol Coupon Booklet.batch_id` |

Grouping is enabled via Frappe's built-in report grouping; the Administrator selects `current_delivery_man` as the group dimension.

**Rationale**:
- Query Report supports custom SQL + JOINs (needed for `days_in_custody`) while remaining declarative and translation-friendly.
- Uses a single JOIN onto the Custody Entry child table (where `docstatus = 1`) to compute "days in custody" from the latest event; index on `Purisol Custody Entry Booklet.booklet` keeps this fast.
- Report Builder alone would not give us `days_in_custody`; a Script Report would give us full Python flexibility but is heavier than needed for a two-column computation.

**Alternatives considered**:
- **Saved list view with filter `status = In Custody`**: rejected — no `days_in_custody` column, and grouping by delivery man is less flexible than report-level grouping.
- **Script Report**: rejected — overkill; Query Report handles the computation cleanly.
- **Dashboard card**: deferred — Phase 8 introduces the dashboard; this phase's report feeds into that dashboard later.

---

## 9. Permissions for the New DocTypes

**Decision**: Fixture-extend the `Purisol Administrator` role with:
- `Purisol Custody Entry`: `read = 1, write = 1, create = 1, submit = 1, cancel = 1, amend = 0, delete = 0`.
- `Purisol Custody Entry Booklet` (child table): inherits from parent; no independent permissions needed.
- `Current Custody by Delivery Man` report: `read = 1` (standard report permission model).

`System Manager` retains its standard ERPNext-wide permissions.

**Rationale**:
- Matches PRD §13 table (Custody Entry has Create / Read / Write / Submit / Cancel / Amend all Yes; we set `amend = 0` in Phase 2 because amend semantics for custody would require re-processing snapshots and are not required by any spec requirement — a cancel + fresh entry achieves the same operational outcome with cleaner audit).
- Constitution VI: only one custom role in MVP.

**Alternatives considered**:
- **Enable amend**: deferred — amend is not required by spec; can be enabled in a later phase if operational feedback demands it without breaking compatibility (Frappe's amend mechanism produces a new document with the same number + `-1` suffix, preserving history).
- **Delete permission**: rejected — a deleted Custody Entry would break the audit chain; cancel is the correct path.

---

## 10. Testing Strategy

**Decision**: Three test files, all using `frappe.tests.utils.FrappeTestCase`:

- `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_custody_entry/test_purisol_custody_entry.py` — **unit**:
  - `test_assign_requires_to_delivery_man`
  - `test_assign_forbids_from_delivery_man`
  - `test_transfer_requires_both`
  - `test_transfer_rejects_self`
  - `test_return_requires_from_delivery_man`
  - `test_rejects_empty_child_table`
  - `test_rejects_duplicate_booklet_in_entry`
  - `test_assign_rejects_booklet_not_in_stock`
  - `test_transfer_rejects_booklet_held_by_other`
  - `test_return_rejects_booklet_held_by_other`
  - `test_snapshot_filled_before_submit`
  - Each test uses a minimal Phase-1 seed: 2–3 booklets and 2 Employee records created via a helper in `tests/fixtures/`.

- `cx_purisol/cx_purisol/cx_purisol/tests/test_custody_flows.py` — **integration**:
  - `test_assign_end_to_end` — booklets `In Stock` → `In Custody` with correct `current_delivery_man`.
  - `test_return_end_to_end` — booklets `In Custody` → `In Stock`, `current_delivery_man` cleared.
  - `test_partial_transfer` — subset moves, rest stays; exactly one Custody Entry record produced.
  - `test_atomic_rollback_on_invalid_booklet` — one booklet in a 3-booklet entry is invalid; no booklet changes state.
  - `test_custody_history_reconstructible` — a booklet goes through Assign → Transfer → Return; querying Custody Entries for that booklet returns all three in order.
  - `test_cancel_reverses_assign` — cancel an Assign entry, booklet returns to `In Stock`, `current_delivery_man` cleared.
  - `test_cancel_rejected_if_booklet_subsequently_moved` — Assign → Transfer; cancel of the Assign fails with a clear error (expected post-state mismatch).
  - `test_cancel_reverses_transfer` — cancel a Transfer, booklet returns to `from_delivery_man`.
  - `test_phase1_booklet_form_field_read_only_via_client_script` — verifies the form-script marker is present (a sanity check against accidental removal of the UI guard).

- `cx_purisol/cx_purisol/cx_purisol/report/current_custody_by_delivery_man/test_current_custody_by_delivery_man.py` — **integration**:
  - `test_report_lists_only_in_custody` — seed a mix of states; report returns only `In Custody` rows.
  - `test_report_grouping_by_delivery_man` — with two delivery men and four booklets, grouping produces two groups.
  - `test_report_days_in_custody_matches_latest_entry` — seed a Transfer after an Assign; `days_in_custody` reflects the Transfer's timestamp, not the Assign's.

**Rationale**: Satisfies constitution X and every spec acceptance scenario / success criterion testable in this phase.

**Alternatives considered**:
- **Mocking `frappe.db`**: rejected — `FrappeTestCase` runs against a real test DB; real writes catch index/constraint bugs that mocks would hide.
- **Skipping the report tests**: rejected — SC-005 is a measurable criterion; a direct assertion against a seeded dataset is the cheapest way to verify it.

---

## 11. JavaScript (Client Script) Scope

**Decision**: One small `purisol_custody_entry.js` file attached to the Custody Entry DocType, doing exactly:
1. On `entry_type` change: toggle visibility and required-ness of `from_delivery_man` / `to_delivery_man` based on the type (`Assign`: hide `from`, require `to`; `Transfer`: show + require both; `Return`: show + require `from`, hide `to`).
2. On `entry_type` change: apply a filter to the booklet link in the child table so the Administrator only sees eligible booklets (e.g., `Assign` shows only `In Stock`; `Return`/`Transfer` with `from_delivery_man` shows only booklets currently held by that delivery man).

Server-side validation (§3) remains authoritative — the client script is purely a UX aid. No business logic is duplicated; if the client script is missing or bypassed (e.g., REST API submit), the server still enforces every rule.

**Rationale**:
- UX-only client filters are the Frappe-idiomatic approach to multi-state forms.
- Keeping the client small avoids drift between client and server rules.
- Separately required by Phase-1 precedent: `purisol_coupon_booklet.js` (to be added) is how we lock `current_delivery_man` in the form (see §7).

**Alternatives considered**:
- **Generate a DocType per entry type** (so required-ness can be encoded in JSON): rejected — rejected already in §1.
- **Set fields required dynamically via DocType `depends_on`/`mandatory_depends_on`**: acceptable as an alternative and can be used alongside the JS filters; will be implemented *in addition to* the JS where possible (e.g., `mandatory_depends_on = "eval:doc.entry_type === 'Assign'"` for `to_delivery_man`).

---

## Open Items

None. All spec requirements and the constitutional gates are resolved.
