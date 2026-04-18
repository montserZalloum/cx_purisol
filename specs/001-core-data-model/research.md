# Phase 0 — Research: Core Data Model

**Feature**: `001-core-data-model` · **Date**: 2026-04-18

All items are Phase-1 scoped. No `[NEEDS CLARIFICATION]` markers remain in the spec; this research consolidates the design decisions that back the plan.

---

## 1. Sequential Numbering Strategy (`WP-NNNNN`, `CP-NNNNN`)

**Decision**: Use Frappe's built-in naming series `WP-.#####` for `Purisol Coupon Booklet` and `CP-.#####` for `Purisol Coupon`, via the `autoname` field in the DocType JSON. Use `frappe.model.naming.make_autoname(...)` inside the booklet-generation code to *pre-compute* booklet and coupon names deterministically before record creation, instead of letting each `.insert()` allocate its own name.

**Rationale**:
- Frappe maintains `tabSeries` as a single serialized row per prefix; `SELECT ... FOR UPDATE` in `frappe.model.naming.getseries` serializes concurrent consumers, satisfying spec FR-021 (single serialized numbering authority).
- Pre-computing names lets the coupon loop for each booklet derive `CP-((N-1)*20+1)…CP-(N*20)` from the booklet's own number, rather than re-querying the series for each coupon (→ avoids the O(N×20) round-trips that would dominate background-job latency).
- Zero-padded 5-digit format is native to the `#####` placeholder; no custom formatter needed.

**Alternatives considered**:
- Custom sequence table (`Purisol Number Counter`): rejected — duplicates what `tabSeries` already provides, adds a migration, violates constitution II (do not reinvent).
- Per-booklet child table of coupons (rather than sibling DocType): rejected — 20 coupons × thousands of booklets as child rows on a single parent bloats form rendering and kills coupon-level querying. The PRD (§7.2) and the constitution (per-coupon audit metadata) both require coupons as a first-class DocType.
- UUID or ULID identifiers: rejected — spec explicitly mandates human-readable `WP-NNNNN` / `CP-NNNNN` serials (PRD §6).

**Key implementation notes**:
- `make_autoname("WP-.#####")` → next free `WP-NNNNN`.
- For generation of N booklets, call `make_autoname` once per booklet (N times) → N contiguous `WP` numbers.
- For each booklet `WP-K` (where K is parsed from the name), coupons are `CP-{(K-1)*20+1:05d}` … `CP-{K*20:05d}`. This derivation makes the coupon series *computed*, not *allocated*: `tabSeries` row for `CP` is kept in sync by calling `frappe.db.set_value("Series", "CP", "current", K*20)` at the end of the batch, so any other code path that naïvely calls `make_autoname("CP-.#####")` still gets a non-colliding value. This is the key to the WP↔CP invariant (spec FR-008, SC-002).

---

## 2. Background-Job Dispatch (`frappe.enqueue`)

**Decision**: The whitelisted entry point `purisol_generate_booklets(quantity, batch_id=None)` branches on `quantity`:
- `quantity ≤ 20` → run inline, return the summary dict.
- `quantity > 20` → `frappe.enqueue("cx_purisol.api.booklet_generation._run_generate_booklets_job", queue="long", timeout=1800, quantity=quantity, batch_id=batch_id, user=frappe.session.user)` and return `{"enqueued": True, "job_name": ..., "channel": ...}`.

The inner job function `_run_generate_booklets_job` does the same work as the sync path and emits progress via `frappe.publish_realtime(event="purisol_generate_booklets_progress", message={...}, user=user)`.

**Rationale**:
- Constitution VIII mandates `frappe.enqueue` for any operation creating > 100 records. The 20-booklet threshold (→ 420 records inc. the booklet itself) is the natural inflection point and matches the user-input brief.
- `queue="long"` isolates this work from short interactive jobs.
- `publish_realtime` is the same transport used by ERPNext's bell notifications → future notification-channel refactor (constitution VII) does not need to change the transport, only the dispatch wrapping.

**Alternatives considered**:
- `frappe.call_later`: rejected — not durable; worker restart loses the job.
- Celery/external queue: rejected — Frappe ships with RQ (via `frappe.enqueue`); external queues violate constitution II (leverage platform).
- Chunked inline processing with `frappe.db.commit()` every N: rejected — doesn't solve the gunicorn 120 s timeout (the HTTP request still blocks), and breaks atomicity guarantees.

**Idempotency**: The job consumes series values in order; a retry after partial success resumes from the current `tabSeries` head, producing no gaps and no duplicates. This satisfies spec SC-006. The job function does not accept a "starting number" argument — it always calls `make_autoname` — precisely so that retries are safe.

---

## 3. Atomicity of Each Booklet + Its 20 Coupons

**Decision**: Each booklet and its 20 coupons are created inside a single transactional unit using `frappe.db.savepoint("purisol_booklet_%d" % i)` with rollback on exception. `frappe.db.commit()` is called once per completed booklet inside the background job (so a 50-booklet run produces 50 commits — small enough that a failure discards at most the in-flight booklet's work, large enough that per-row commit overhead is avoided).

**Rationale**:
- Spec FR-017 requires atomicity per booklet (no dangling booklet without 20 coupons).
- Per-booklet commit (rather than per-batch) keeps the transaction size bounded (21 INSERTs) and avoids long-lock contention with other writers during a 1,000-booklet run.
- The sync path uses the request's default transaction and commits on successful return.

**Alternatives considered**:
- One giant transaction for all N booklets: rejected — transaction time grows linearly with N; risk of MariaDB deadlock with concurrent writers rises; a late-stage failure rolls back all prior work (bad UX for large batches).
- Per-record commit (after each coupon): rejected — magnifies commit overhead and creates windows where a booklet has partial coupons visible to other queries.

---

## 4. Progress Feedback Contract

**Decision**: The background job publishes:
- On enqueue: `{"status": "started", "total": N, "done": 0}` (emitted by the job on first execution, not by the dispatcher, so the client always sees the event on the job's channel).
- On each completed booklet: `{"status": "progress", "total": N, "done": k, "last_booklet": "WP-000XX"}` — throttled to at most every 1% of the run OR every 500 ms, whichever is less frequent (to avoid overwhelming the realtime bus on large runs).
- On completion: `{"status": "complete", "total": N, "first_booklet": "WP-000AA", "last_booklet": "WP-000BB", "total_coupons": N*20}` — the same shape as the sync path's return value.
- On failure: `{"status": "failed", "done": k, "error": "<safe error message>"}`.

The client attaches a `frappe.realtime.on("purisol_generate_booklets_progress", ...)` handler for the current user.

**Rationale**: Matches spec FR-018 / SC-004. Keeps the sync and async summary shapes identical so the UI renders one summary component regardless of path (spec FR-019a).

**Alternatives considered**:
- Storing progress on a `Purisol Generation Job` DocType with client polling: rejected — introduces a DocType solely as a progress marker; `publish_realtime` does the job without a new entity.
- Server-sent events over a custom HTTP endpoint: rejected — Frappe's realtime channel is idiomatic and already wired.

---

## 5. Settings Singleton Enforcement

**Decision**: Mark `Purisol Settings` with `"issingle": 1` in its DocType JSON. No controller logic is needed to prevent duplicates — Frappe's single-DocType machinery stores the record as a flat row in `tabSingles` (key/value) and does not permit creation of a second instance.

**Rationale**:
- Constitution II: leverage platform primitives.
- `issingle=1` also suppresses the "New" button in list views, forbids `frappe.get_doc("Purisol Settings").insert()` from creating a second record (returns the singleton), and mounts a desk route `/app/purisol-settings` that opens the single form directly.
- The test for "cannot be duplicated" becomes a test of Frappe's own guarantee: `assertRaises(frappe.ValidationError)` when a second `insert` is attempted — a cheap regression check that documents the invariant in our own tests.

**Alternatives considered**:
- Regular DocType + a `validate` hook that errors if `frappe.db.count("Purisol Settings") > 1`: rejected — reintroduces a race condition the singleton model already solves at the schema level.

---

## 6. Role and Permissions

**Decision**: Ship a fixture-defined `Purisol Administrator` role. DocType-level permission rules grant:
- `Purisol Settings`: read=1, write=1, create=0, delete=0 (singleton → create/delete meaningless).
- `Purisol Coupon Booklet`: read=1, write=1, create=0 (records are created only by the generation API, not by hand), delete=0.
- `Purisol Coupon`: read=1, write=0 (Phase 1 exposes coupons as read-only; later phases permit write via Consumption Entry only), create=0, delete=0.

System Manager retains its standard ERPNext-wide permissions.

**Rationale**:
- Constitution VI caps MVP roles at one custom role.
- Removing UI `create` on booklets/coupons keeps the generation flow as the single creation surface (the API `@frappe.whitelist()` bypasses DocType `create` perms by design for system-level actions, but using `ignore_permissions=True` inside the API with explicit role check at the entry point).

**Alternatives considered**:
- Granting Administrator `create` on booklets: rejected — allows manual creation that bypasses numbering/validation guarantees.
- Having no role at all (rely on System Manager): rejected — downstream phases will grant/deny on this role; introducing it in Phase 1 lets later phases layer cleanly.

---

## 7. Reserved Fields for Later Phases

**Decision**: The full MVP schema (from PRD §7.1 and §7.2) is defined in the DocType JSON now, including:
- Booklet: `current_delivery_man`, `customer`, `sold_on`, `sales_invoice`, `depleted_on`.
- Coupon: `consumed_on`, `consumed_by_delivery_man`, `consumption_entry`.

These fields are declared but left unrequired in this phase, so that Phase 1 generation can populate only the in-scope fields without violating required-field rules.

**Rationale**:
- Avoids a later schema migration that would force backfill on an active production dataset.
- Makes the DocType JSON the single source of truth for the schema throughout the project.
- Constitution's migration-safety rule (Additional Constraints → "Migrations") favours upfront schema over incremental `patches.txt` entries when the fields are already fully specified in the PRD.

**Alternatives considered**:
- Adding reserved fields in later phases: rejected — requires `patches.txt` entries for every phase that adds a field, raising PR-review and data-safety cost.
- Reserving fields as `Data (hidden)` placeholders: rejected — no savings, and hidden-then-unhidden fields make form layout review noisy.

---

## 8. Testing Strategy

**Decision**: Three test files, all using `frappe.tests.utils.FrappeTestCase`:

- `cx_purisol/cx_purisol/cx_purisol/tests/test_numbering.py` — **unit**:
  - `test_coupon_range_for_booklet_1` → `CP-00001`..`CP-00020`.
  - `test_coupon_range_for_booklet_2` → `CP-00021`..`CP-00040`.
  - `test_coupon_range_for_booklet_50` → `CP-00981`..`CP-01000`.
  - Property test: for any `N` in `1..1000`, the computed range has length 20 and `first + 20 == next.first`.

- `cx_purisol/cx_purisol/cx_purisol/tests/test_booklet_generation.py` — **integration**:
  - `test_sync_generation_5_booklets` → inline path, asserts 5 booklets + 100 coupons, all `In Stock` / `Available`.
  - `test_sync_generation_then_another_batch` → first `generate(3)`, then `generate(2)`: 5 booklets total, `WP-00002`'s coupons are `CP-00021..CP-00040`, no overlap.
  - `test_async_generation_50_booklets` → uses `frappe.enqueue(..., now=True)` (synchronous execution of the enqueued function) to run the job path in-test; asserts the final state matches a direct call.
  - `test_generation_rejects_zero_quantity` / `test_generation_rejects_negative_quantity` → `assertRaises(frappe.ValidationError)`.
  - `test_generation_with_batch_id` → all generated booklets have the supplied `batch_id`.
  - `test_generation_summary_shape` → sync return has keys `{first_booklet, last_booklet, total_coupons}`.

- `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_settings/test_purisol_settings.py` — **unit**:
  - `test_singleton_exists_after_install` → `frappe.get_single("Purisol Settings")` returns a document.
  - `test_cannot_duplicate_singleton` → attempting `frappe.get_doc({"doctype": "Purisol Settings"}).insert()` raises (Frappe's own guarantee; documented as a regression fence).
  - `test_defaults` → `customer_low_stock_threshold == 3`, `warehouse_low_stock_threshold == 5`, `enable_consumption_warnings == 1`.

**Rationale**: Satisfies constitution X (unit + integration, FrappeTestCase) and all spec acceptance scenarios and success criteria that are testable in this phase.

**Alternatives considered**:
- Mocking `frappe.enqueue` with `unittest.mock`: rejected in favour of `frappe.enqueue(..., now=True)` which actually runs the registered function and thus exercises the real code path.
- Skipping the "cannot duplicate" test because it's a Frappe-framework guarantee: rejected — the test is a cheap regression fence if a future PR accidentally flips `issingle` off, and the user explicitly requested this test.

---

## Open Items

None. All spec requirements and the user's Phase-1 brief are resolved.
