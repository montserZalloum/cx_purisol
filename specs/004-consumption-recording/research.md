# Phase 0 Research — Consumption Recording

**Feature**: 004-consumption-recording | **Date**: 2026-04-18

This document resolves every open question in the feature spec and plan Technical Context. Each section follows the format: **Decision** (what was chosen), **Rationale** (why), **Alternatives considered** (what else evaluated and why rejected).

---

## 1. Shape of the new DocType: single submittable parent with one child table

**Decision**: Create one submittable parent DocType `Purisol Coupon Consumption Entry` (`is_submittable = 1`, `track_changes = 1`, naming series `PCC-.YYYY.-.#####`) with a required child table `coupons` of type `Purisol Coupon Consumption Item`. Both Mode A and Mode B write into the same child table. A second, **reserved-empty** child table `discrepancies_detected` of type `Purisol Coupon Discrepancy Item` is declared on the parent now, but never populated in Phase 4 — it exists as a schema anchor so Phase 5 can add discrepancy rows without renaming or restructuring the parent.

**Rationale**:
- Consumption is a domain concept that ERPNext does not model — it is not a stock movement, not a payment, not a journal entry. It is a physical-paper-to-digital audit record. Per constitution Principle II, a custom Purisol DocType is justified because no ERPNext primitive fits (explicit one-line justification required by the constitution — satisfied here).
- `is_submittable = 1` matches constitution Principle IV: every state-changing action on coupons must be represented by a submittable record. The Consumption Entry is the submittable source of truth for `Available → Consumed` transitions; the coupon's own `consumed_on`, `consumed_by_delivery_man`, `consumption_entry` fields are the per-coupon cache of that truth (constitution IV.3).
- One parent + one child-table row-per-coupon is the simplest shape that supports both Mode A and Mode B writing into the same structure (spec FR-003). Adding a row is mode-agnostic once the UI has resolved the coupon reference.
- Declaring `discrepancies_detected` now as a stub child-table makes Phase 5 purely additive — it can add fields to `Purisol Coupon Discrepancy Item` and populate rows, without changing Phase 4's JSON or code paths. The Phase 5 seam is called out explicitly in spec FR-035 and Assumption "Discrepancy detection is Phase 5".
- Naming series `PCC-.YYYY.-.#####` follows the Phase-2 `PCE-.YYYY.-.#####` custody-entry convention: prefix keys the DocType family, year scopes the counter, 5-digit zero-pad supports up to 99 999 entries per year (≫ expected volume of ≤ 5 entries/day ≈ 2 000/year).

**Alternatives considered**:
- **Two parallel DocTypes, one per mode** (e.g. `Purisol Coupon Consumption By Booklet` and `Purisol Coupon Consumption By Number`) — rejected. Stores twice as much surface area, doubles the validation code, and fragments reports that must aggregate across both. The spec explicitly requires a single shape downstream of the input box (FR-003, SC-007).
- **Non-submittable DocType** — rejected. Violates constitution IV ("every state-changing action MUST be represented by a submittable record") and forfeits Frappe's built-in cancel/amend transaction atomicity — we'd have to re-implement it ourselves.
- **Add consumption rows as a child table directly on `Purisol Coupon Booklet`** — rejected. A single end-of-day consumption event almost always spans multiple booklets; modelling it per-booklet fragments the event and makes cross-booklet validation (e.g. "duplicate coupon within the entry" across booklets) awkward. It would also conflict with the delivery-man attribution being an entry-level field.
- **Skip the `discrepancies_detected` stub and let Phase 5 add the table** — rejected. Frappe fixtures / migrations are easier when the child table's parent relationship exists from day one. Adding a child table later forces a `Custom Field` or a JSON rename, both of which create migration friction.

---

## 2. Where in the document lifecycle each validation runs

**Decision**: The four blocking validations (FR-030 empty child table, FR-031 coupon exists, FR-032 duplicate within entry, FR-033 already consumed) are split across Frappe's standard lifecycle hooks:

- `validate` (runs on every save, including drafts): FR-030 (empty child table) and FR-032 (duplicate coupon within entry), plus compute `total_coupons = len(coupons)`. These are pure in-memory checks that do not inspect live coupon state, so they apply to drafts as well as submits.
- `before_submit` (runs inside the submit transaction, once, just before `docstatus = 1` is persisted): FR-031 (coupon exists) and FR-033 (already consumed). These check **live** coupon state in a single bulk read (`frappe.get_all("Purisol Coupon", filters={"name": ["in", names]}, fields=["name", "status", "consumption_entry"])`). Any failure raises `frappe.ValidationError` with a combined message, which Frappe rolls back inside the submit transaction.
- `on_submit` (runs inside the submit transaction, after `before_submit`): no further validation — strictly the side-effect pass (FR-040 / FR-041 / FR-042). If a write fails mid-pass (e.g. `TimestampMismatchError` from concurrent submit), the raise bubbles out of `on_submit` and Frappe rolls back.

**Rationale**:
- FR-030 and FR-032 are logically impossible independent of what's in the database — they apply to a draft the moment the Administrator adds a duplicate row. Putting them in `validate` surfaces the error at save time (fast feedback) rather than waiting until submit.
- FR-031 and FR-033 depend on **live** state that can change between draft-save and submit (another entry submitted in between may have consumed one of the referenced coupons). Running them in `before_submit` gives the latest snapshot and matches the spec edge case "Booklet is Depleted before the draft submits" — drafts are explicitly not reservations; the error surfaces at submit.
- Splitting validation between `validate` (pure) and `before_submit` (live) keeps the code pure-function-shaped where possible, which is easier to unit-test without touching the database.
- Bulk reading with a single `frappe.get_all` instead of per-row `frappe.get_doc` keeps the worst-case 200-coupon entry to one query instead of 200. Avoids N+1 (research.md §4 of Phase 3 applied the same idiom for the booklet-consumption check).

**Alternatives considered**:
- **All four checks in `validate`** — rejected. Would fire on every save-of-draft; a draft held overnight would re-check live state every time the Administrator opened the form, making the form slow and producing confusing error messages on a half-built draft.
- **All four checks in `before_submit`** — rejected. Duplicate-within-entry and empty child table would not surface until submit, wasting the Administrator's time on an unsaveable draft.
- **Checks in `on_submit`** — rejected. `on_submit` runs after `docstatus = 1` is written; raising there still rolls back the transaction but wastes the persisted `docstatus` flip. `before_submit` is the canonical seam for "block submit after final live-state check".

---

## 3. Transaction atomicity: relying on Frappe's request transaction

**Decision**: No explicit savepoints, no explicit `frappe.db.commit()`, no `frappe.enqueue`. All writes in `on_submit` and `on_cancel` run inside the single transaction Frappe opens around the Document submit/cancel; any `frappe.throw` unwinds every pending write together.

**Rationale**:
- Frappe opens an implicit transaction per HTTP request; `Document.submit()` / `Document.cancel()` run inside it. `validate`, `before_submit`, `on_submit`, `on_update`, etc. are all inside the same transaction. A `frappe.throw` anywhere rolls back to the beginning of the request. This matches FR-034 (submit all-or-nothing) and FR-053 / FR-060 (cancel all-or-nothing) by construction — no extra machinery needed.
- Background jobs (`frappe.enqueue`) would **break** atomicity: the job runs after the submit commits, so a job failure would leave a committed Consumption Entry with un-`Consumed` coupons — exactly the invariant violation SC-003 and SC-005 forbid.
- Explicit savepoints would matter only if we wanted to `rollback_to_savepoint` and continue. We never want that — any failure must unwind the whole entry.
- Per-coupon write via `frappe.db.set_value(doctype, name, fields, update_modified=True)` is bundled into the same transaction as the parent save. Each call issues one `UPDATE` but writes `tabVersion` via `track_changes`, so the audit trail is preserved without us writing to `tabVersion` by hand (matches constitution IV).

**Alternatives considered**:
- **Per-booklet savepoint (so a single bad coupon only rolls back its own booklet)** — rejected. Would violate FR-034's invoice-wide all-or-nothing (spec explicitly says the whole entry rejects, not per-booklet).
- **Enqueued background submit** — rejected as above.
- **Explicit `frappe.db.commit()` after each row** — rejected. This would commit partial state, violating FR-060 and leaving the Administrator staring at a partially-Consumed entry if the Nth row fails.

---

## 4. Bulk-reading coupon state vs. per-row `get_doc`

**Decision**: In `before_submit`, do a single `frappe.get_all("Purisol Coupon", filters={"name": ["in", coupon_names]}, fields=["name", "status", "consumption_entry"])` to fetch live state for every referenced coupon in one query. Build the errors list from the returned dict. If any referenced name is **missing** from the result (link broken or coupon deleted between draft and submit), that counts as "coupon does not exist" under FR-031.

**Rationale**:
- One query scales O(1) in round-trips regardless of the entry size. For a worst-case 200-coupon entry, we save 199 queries versus the `get_doc` approach — each `get_doc` also pulls every child table of the coupon (none in this case, but the idiom is wasteful anyway).
- `frappe.get_all` is a thin wrapper over `SELECT ... FROM \`tabPurisol Coupon\` WHERE name IN (...)`. The DB issues a single plan; the result lands in Python as a list of dicts. Sufficient for read-only validation.
- Missing-from-result is a clean signal for non-existence: the `IN (...)` filter only returns rows that exist, so a name we passed that isn't in the result is, by construction, a broken link. This matches FR-031's "coupon does not resolve to an existing `Purisol Coupon` record."
- Mirrors the Phase-2 `_validate_assign` / `_validate_transfer` pattern in `purisol_custody_entry.py`, which uses the same bulk-read idiom for the same reason.

**Alternatives considered**:
- **Per-row `frappe.get_doc`** — rejected, N+1 overhead.
- **Raw SQL (`frappe.db.sql`)** — rejected, constitution "no raw SQL writes outside `frappe.db` helpers" extends by convention to reads as well (to keep permission filtering / ORM semantics uniform).

---

## 5. Concurrency: two concurrent submits referencing the same coupon

**Decision**: Rely on per-coupon optimistic locking via the `modified` timestamp. The `before_submit` bulk read captures each coupon's state; any subsequent `frappe.db.set_value(..., update_modified=True)` rejects with `frappe.TimestampMismatchError` if another request updated the coupon in the meantime. Frappe rolls back the losing submit entirely; the winner's side effects are already committed.

**Rationale**:
- Spec SC-009 and FR-061 require "exactly one succeeds; the other is rejected at the 'already consumed' blocking check". Two outcomes are acceptable in practice:
  - **Common race (reads are sequential)**: the second request's `before_submit` reads `status = Consumed` and rejects with FR-033's blocking error — clean path, exactly what the spec prescribes.
  - **Tight race (reads interleave)**: both `before_submit` passes read `Available`; one writes first, the other's `db.set_value` loses on the `modified`-stamp check and raises `TimestampMismatchError`. Frappe translates this into a user-facing "this document was modified — please retry" and rolls back. Functionally equivalent to FR-033 from the Administrator's perspective.
- No `SELECT ... FOR UPDATE` is required. Pessimistic locking at this scale (1–200 coupons per submit, a handful of entries per day) creates deadlock potential for no real benefit.
- `frappe.TimestampMismatchError` is already localised by Frappe core; we do not need to catch and re-raise a Purisol-specific message. If real-world feedback demands a more specific wording, a future phase can wrap the call site.

**Alternatives considered**:
- **Explicit `SELECT ... FOR UPDATE` on every referenced coupon in `before_submit`** — rejected. Deadlocks under interleaving entry orders (entry A holds coupon X and needs coupon Y; entry B holds coupon Y and needs coupon X). At our scale, the optimistic-lock retry path is simpler.
- **Redis advisory lock per coupon** — rejected. Over-engineered; introduces a new failure mode (lock leaks on crashed RQ worker).
- **Serialize all Consumption Entry submits via a single application-level lock** — rejected. Correct but ruinous for throughput; during a busy end-of-day period multiple administrators may submit simultaneously (the spec does not rule this out).

---

## 6. Auto-depletion on submit and auto-revert on cancel

**Decision**:

**On submit** — after the per-coupon `status → Consumed` writes, iterate the **distinct** booklets touched by the entry. For each booklet:

1. `consumed_count = frappe.db.count("Purisol Coupon", {"booklet": name, "status": "Consumed"})`.
2. `remaining_count = 20 - consumed_count`.
3. Write `consumed_count` and `remaining_count` on the booklet doc.
4. If `consumed_count == 20` and the booklet's current `status` is `Sold`:
   - Set `status = "Depleted"` and `depleted_on = self.posting_datetime` on the same doc.
   - Save the booklet with `booklet.save(ignore_permissions=True)` so the booklet controller's widened `validate` runs and the `Sold → Depleted` transition is checked.
   - Add a `Comment`: `_("Depleted via {0}").format(self.name)`.

**On cancel** — after the per-coupon consumption-metadata clearing pass, iterate the distinct booklets touched. For each booklet:

1. Recompute `consumed_count` and `remaining_count` (same formulas, using the now-updated coupon statuses).
2. If the booklet's current `status == "Depleted"` AND this entry was the one that triggered the depletion — **defined as**: the most recent (by `creation` timestamp) non-cancelled Consumption Entry whose child-table contains any of this booklet's coupons is `self.name` — then:
   - If the recomputed `consumed_count < 20`: set `status = "Sold"` and clear `depleted_on`. Save via `booklet.save(ignore_permissions=True)`. Add a `Comment`: `_("Depletion reverted — entry {0} cancelled.").format(self.name)`.
   - Else (some later entry has kept the booklet at 20): leave `status = Depleted`; the later entry now owns the depletion.
3. If `status != Depleted`: just save the updated aggregate counts. No state transition.

**Rationale**:
- Step 1–3 on submit treat `consumed_count` / `remaining_count` as a cache recomputed from the per-coupon source of truth (constitution IV: "aggregates lie; per-coupon metadata does not"). The recompute is cheap — one `COUNT(*)` per touched booklet, at most 3 booklets per typical entry.
- Deriving "which entry triggered the depletion" from the most-recent-entry-of-record rather than storing a `depleted_by_entry` field on the booklet is deliberate: (a) it keeps the booklet's schema stable, (b) on cancellation of a much-older entry, the derivation correctly attributes depletion to whichever entry currently sits at the 20-count mark, (c) the audit trail for the depletion is already on the booklet as a `Comment` naming the entry, so the information is preserved.
- Saving via `booklet.save(ignore_permissions=True)` (rather than `db_set`) deliberately re-runs the booklet `validate`, which exercises the widened `_ALLOWED_TRANSITIONS` set and rejects any accidental skip (e.g. from `In Stock` directly to `Depleted`). This is the same idiom used by Phase 2's `_on_submit_assign` / `_on_submit_return` handlers — consistent.
- `Depleted → Sold` is narrowly gated: it fires only on a Consumption Entry cancel that also drops `consumed_count` below 20 **and** where the entry was the trigger of record. A `Depleted` booklet reached by a non-cancellable path stays `Depleted`. This preserves the spirit of constitution III.3 ("terminal states are strictly terminal") while still supporting the spec's cancel round-trip requirement (FR-052, SC-008).
- The "no intermediate state" requirement (FR-042, SC-004: never observe `consumed_count == 20` with `status != Depleted`) is satisfied by running the recompute and the transition write inside the same save on the same booklet doc — `booklet.save()` issues one transactional UPDATE with both fields.

**Alternatives considered**:
- **Store `depleted_by_entry` on the booklet and check it during cancel** — rejected. Adds a field whose only purpose is cancel-time attribution, when the same information is derivable from the consumption log and from `tabVersion`. Avoids a JSON schema change on `Purisol Coupon Booklet`.
- **Recompute aggregates inside a background job** — rejected. Breaks atomicity (see §3).
- **Per-coupon `db_set` on the booklet instead of `save()`** — rejected. Would skip booklet `validate`, allowing a bug that introduces a disallowed transition to land silently. Running `validate` on every booklet touch is the safety net.
- **Allow `Depleted → In Stock|In Custody` as additional narrow transitions** — rejected. The spec's cancel semantics only need `Depleted → Sold`; anything beyond that is future speculation and risks un-auditable re-opening.

---

## 7. Audit-trail attribution: Comment + tabVersion

**Decision**: `track_changes = 1` on both new DocTypes writes the base audit entries to `tabVersion` automatically. On top of that, add explicit `Comment` (via `frappe.get_doc("Purisol Coupon Booklet", name).add_comment("Info", _("Depleted via {0}").format(self.name))`) on every booklet whose status changes to `Depleted`, and a reciprocal `Comment` ("Depletion reverted — entry X cancelled.") on cancel-driven reverts. Per-coupon status changes do **not** receive an explicit `Comment` — the coupon's `consumption_entry` link field is self-explanatory ("which entry consumed this coupon?" is answered by following the link).

**Rationale**:
- Matches FR-043 and SC-010 ("any later viewer can answer 'why did this change?' from the target record alone").
- `Comment` entries appear in the Frappe timeline alongside the Version history, are trivially searchable, and survive exports. Using them for the booklet's status change (which is a derived side-effect, less obvious than a primary write) makes the "why" visible without hunting through Version diffs.
- Not adding a Comment per coupon keeps the audit trail uncluttered for the overwhelmingly common case (10–20 coupons per entry → 10–20 Comments would be noise). The coupon's own `consumption_entry` Link field is the natural navigation path.

**Alternatives considered**:
- **Custom `Purisol Audit Log` DocType** — rejected. Duplicates `tabVersion` + `Comment`, exactly the kind of parallel-system the constitution forbids in spirit (II) and violates the "no parallel ledger" rule by analogy.
- **Explicit Comment on every coupon state change** — rejected as noisy above.

---

## 8. Mode A vs. Mode B UX: client-side state + whitelisted server helpers

**Decision**: Deliver the dual-mode form as a client-side script (`public/js/purisol_coupon_consumption_entry.js`) that augments the standard Frappe form with:

1. A **mode switcher** (two tabs / radio buttons: "By Booklet" / "By Coupon Number") above the `coupons` grid.
2. A **Mode A widget**: a booklet autocomplete (Frappe's `Link` control against `Purisol Coupon Booklet`) + an "Available Coupons" checklist populated by calling the whitelisted endpoint `cx_purisol.cx_purisol.api.consumption.list_available_coupons(booklet)` + an "Add to Entry" button that iterates ticked rows and calls `cur_frm.add_child("coupons", {coupon, booklet, customer})` + `cur_frm.refresh_field("coupons")` + clears the checklist.
3. A **Mode B widget**: a multi-line text input + Enter-on-single-line + paste-many support that, on commit, collects the new lines, calls `cx_purisol.cx_purisol.api.consumption.resolve_coupons(coupon_numbers)`, and for each resolved coupon appends a child row; for each unresolved coupon, shows an inline error line naming the missing number (and leaves the valid resolved rows in place — FR-020, FR-021, edge case "multi-line paste with bad lines").

Both widgets write into the **same** `coupons` grid; the grid itself is the single source of truth the server validates on submit. Removing a row before submit (via the grid's built-in "×" button) is a pure client-side edit with no server side-effect (spec edge case "draft state is not a reservation").

**Rationale**:
- Frappe's form framework (`frappe.ui.form.Form`, `cur_frm.add_child`) supports all the pieces we need — custom HTML widgets above the grid, `frappe.call` for server round-trips, grid refresh — without a custom SPA.
- Splitting the server helpers into two pure-read endpoints (`list_available_coupons`, `resolve_coupons`) keeps them trivially cacheable / unit-testable / permission-gated. They never mutate state — submit-time validation (FR-030–FR-033) is authoritative, so even a stale Mode A checklist that includes a coupon another admin consumed in the meantime is harmless (submit rejects the duplicate with a clear error).
- The "paste-many, partial error reporting" UX (FR-020, FR-021) works because `resolve_coupons` accepts a list and returns both `resolved` and `unresolved` buckets in one call — the client renders the bad ones inline without losing the good ones. This matches the Story 2 acceptance scenario 4.
- Forward-compatibility with USB/Bluetooth barcode scanners (FR-022) is free: a barcode scanner acts as a keyboard that types the scanned number and Enter, and our Enter-to-commit handler in Mode B accepts that path without any special code.

**Alternatives considered**:
- **Standalone workflow DocType holding UI state** — rejected. Would be a non-submittable persistent DocType whose only purpose is to carry draft-form state between keystrokes — overkill, and violates Principle II by analogy.
- **A dedicated single-page-app / Frappe Desk Page** — rejected. Adds a new UI surface that diverges from every other Purisol form and breaks the Administrator's mental model ("every Purisol thing is a DocType form"). Also adds translation overhead — the `_()`-wrapped strings in a standard form are automatically discoverable by `bench get-untranslated`.
- **Mode B only (drop Mode A)** — rejected by spec P1 priority: Mode A is the primary visual-reconciliation flow.
- **Render the Mode A checklist server-side via a print format / web view** — rejected. Adds cross-request state, complicates the "Add to Entry" submit button, and doesn't match Frappe's form idiom.

---

## 9. Permissions and role enforcement

**Decision**: The Consumption Entry DocType's JSON `permissions` rule grants create/write/submit/cancel/amend/print/read exclusively to `Purisol Administrator`. Every whitelisted API endpoint (`list_available_coupons`, `resolve_coupons`) starts with `frappe.only_for("Purisol Administrator")`. The `received_by` field is declared `read_only = 1` in the JSON and stamped in `before_insert` with `frappe.session.user`.

**Rationale**:
- `frappe.only_for` is the standard authoritative server-side check; it raises `frappe.PermissionError` which Frappe translates to HTTP 403. Bypass is not possible via curl / bench requests (unlike a pure JS check).
- Stamping `received_by` in `before_insert` (not `before_save`) ensures it is set once, immutably, at record creation — identical to Phase 2's `created_by` pattern on `Purisol Custody Entry`.
- `read_only = 1` on `received_by` in the JSON prevents a user from editing it via the form UI; combined with the insert stamp, the field's value is tamper-evident.
- Standard Frappe link-field integrity handles the `delivery_man` Employee reference and the `coupon` reference — we don't need custom checks for "does this Employee exist?"

**Alternatives considered**:
- **JS-only role check (no `frappe.only_for`)** — rejected, bypassable via direct API calls.
- **Let any user create but restrict submit** — rejected. FR-070 is explicit: create/write/submit/cancel/amend all require `Purisol Administrator`.
- **Store `received_by` via `fetch_from = User.name`** — rejected. `fetch_from` only fires when a link field changes; `received_by` has no user-editable parent link to fetch from. `before_insert` is the correct seam.

---

## 10. Draft state is not a reservation — implications for UX and tests

**Decision**: Accept the spec's explicit model (edge case "draft state is not a reservation"): a draft Consumption Entry with rows has no server-side effect on the referenced coupons. If the Administrator abandons a draft that listed `CP-00005`, another entry can still submit `CP-00005` successfully; the original draft simply fails on submit with FR-033's "already consumed" error when the Administrator later tries to submit it.

**Rationale**:
- Matches spec edge case "Consumption Entry created but never submitted" and "Two drafts both listing the same coupon".
- Implementing reservations would require a separate "reserved coupons" table and a sweep-to-expire job — huge complexity for a UX edge that almost never occurs (administrators don't usually build two drafts for the same coupons).
- Surfacing the conflict at submit time (rather than at draft-save time) is also clearer: the Administrator who actually handed in the coupon first wins, which matches the physical reality.

**Alternatives considered**:
- **Reserve coupons on draft save** — rejected as above.
- **Lock coupons by draft** — rejected; no clean release semantics if the Administrator closes the tab.

---

## 11. Empty vs. populated `discrepancies_detected` in Phase 4

**Decision**: The `discrepancies_detected` child table is declared in Phase 4's JSON as a `Table` field of type `Purisol Coupon Discrepancy Item`, read-only (`read_only = 1`), and the controller's `validate` raises if any row exists (defensive check — the form can't add rows, and there's no code path that appends rows in Phase 4). `has_warnings` is also declared, `read_only = 1`, with a default of `0`, and the controller ensures it is never set to `1` in Phase 4.

**Rationale**:
- Matches FR-035 ("Phase 4 MUST NOT implement any non-blocking warning [...] MUST integrate on top of this spec without breaking the Phase 4 submit path") and SC-011 ("Phase 4 introduces zero discrepancy records").
- The defensive check is belt-and-braces: even if a future dev mistakenly appends a row in a hot-fix, the Phase 4 controller rejects it loudly — no silent scope creep.
- Phase 5's integration becomes purely additive: (a) add real fields to `Purisol Coupon Discrepancy Item`'s JSON, (b) remove the Phase 4 "no rows allowed" guard, (c) populate rows from the new warning detectors. No rename, no parent-schema churn.

**Alternatives considered**:
- **Omit `discrepancies_detected` entirely from Phase 4** — rejected. Phase 5 would then need to add the table, which is a JSON schema churn and a risk of accidental field-order changes.
- **Allow Phase 4 to populate `discrepancies_detected` with empty-string dummy rows as a test** — rejected; literally violates FR-035.

---

## 12. Reusing the Phase-1/2/3 test fixtures

**Decision**: Extend `cx_purisol/cx_purisol/tests/fixtures.py` with a `make_sold_booklet_ready_for_consumption(...)` helper that returns a tuple `(customer, employee, booklet, coupons)` where the booklet is `Sold` to the customer and all 20 coupons are `Available`. Phase 4 tests call this helper in `setUp` rather than seeding fixtures by hand. Each integration test then records consumption on some subset of the returned coupons.

**Rationale**:
- Consistent with the Phase-2 / Phase-3 pattern: each phase's tests extend the shared fixtures helper rather than duplicating seed logic.
- Keeps per-test seed code to one line, matching the constitution's "tests mandatory" principle (X) while keeping them readable.
- Reuses the Phase-3 "sell a booklet via Sales Invoice" helper under the hood — so our consumption tests exercise the real Phase-3 → Phase-4 hand-off path (booklet gets to `Sold` via the real sales integration, not a manually-set status), which guards against regressions between phases.

**Alternatives considered**:
- **Per-test inline seed** — rejected, duplicates setup across every test and drifts over time.
- **Pytest fixtures** — rejected; Frappe's `FrappeTestCase` uses unittest-style `setUp` / `tearDown`, not pytest.

---

## 13. Posting datetime derivation

**Decision**: `posting_datetime` on the entry is the combination of `posting_date + posting_time`, computed as a property on the controller:

```python
@property
def posting_datetime(self):
    return frappe.utils.get_datetime(f"{self.posting_date} {self.posting_time}")
```

This value is what `on_submit` writes into each coupon's `consumed_on` and (if applicable) each booklet's `depleted_on`.

**Rationale**:
- Frappe conventionally stores date and time separately on submittable DocTypes (mirrors `Sales Invoice.posting_date` + `Sales Invoice.posting_time` from Phase 3). Keeping two separate fields makes print formats, reports, and list filters behave as users expect.
- Combining them at the controller level (via `frappe.utils.get_datetime`) rather than at every callsite keeps the "what goes on the coupon?" answer in one place, testable in one unit test.
- The spec explicitly mentions "the entry's posting datetime" for `consumed_on` (FR-040, Acceptance Scenario 1); a derived property makes that concrete.

**Alternatives considered**:
- **Single `Datetime` field on the entry** — rejected. Breaks parity with `Sales Invoice` and the Phase-2 `Purisol Custody Entry` (which uses `entry_datetime` — single Datetime — because custody entries are moment-in-time, not day-in-time). The Consumption Entry is a daily record keyed by a date; two-field shape is more appropriate.
- **Store only `posting_date` and use `creation` as the time** — rejected. `creation` is set by Frappe at insert; the spec explicitly supports backdating ("the entry accepts whatever posting datetime the Administrator sets"), and `creation` does not move.
