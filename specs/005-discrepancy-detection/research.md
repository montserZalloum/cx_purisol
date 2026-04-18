# Phase 0 Research — Discrepancy Detection & Resolution

**Feature**: 005-discrepancy-detection | **Date**: 2026-04-18

This document resolves every `NEEDS CLARIFICATION` flag implicit in the Technical Context and documents, for each non-trivial choice, the **decision**, the **rationale**, and the **alternatives considered**. All decisions are tight-bounded by the Phase-5 spec, the Purisol constitution, and the realities of the existing Phase 1–4 codebase.

---

## 1. Where in the Consumption Entry submit lifecycle does detection run?

**Decision**: Detection runs at the **end** of `PurisolCouponConsumptionEntry.on_submit`, after the coupon-status flips and booklet-aggregate recomputes from Phase 4 have been written, but **before** the `on_submit` returns — i.e. still inside the same database transaction. If the detection service raises for any reason, the whole `on_submit` rolls back (and with it the Phase-4 side effects).

**Rationale**:
- Spec FR-001: "detection happens after Phase 4's blocking validations and coupon/booklet updates, within the same database transaction."
- Spec FR-002: "detection MUST NOT block the consumption entry submission."
- These two requirements look tense but are not actually in conflict. "MUST NOT block" means the detector has no business rule whose failure prevents the entry from committing. "Within the same transaction" means the discrepancy records and the entry itself cannot end up in inconsistent states (entry committed but discrepancies lost, or vice versa).
- Detection is **purely read-and-insert**. It reads Phase-4's own outputs (updated coupon statuses, updated booklet counts) and inserts fresh `Purisol Coupon Discrepancy` rows. It never touches existing coupons/booklets/consumption entries (FR-021). Therefore the only way detection can raise is an infrastructure failure (DB error, serialization conflict) — at which point rolling the entry back is the correct posture, because the entry was never atomically committed in the first place.
- Running detection *after* the coupon flips is essential. The Missing Coupons rule is defined as "coupons between the min and max of the **union** of previously-consumed and currently-consumed coupons that are still `Available`" — and the cleanest way to compute that union is to let Phase 4 write the current entry's consumptions first, then read `status = "Consumed"` for every coupon of the booklet. If detection ran *before*, the service would have to reproduce Phase 4's logic mentally to "project" the post-submit state, which is fragile.

**Alternatives considered**:
- *Detection in `after_submit` hook (post-transaction)* — rejected. Decouples the discrepancy record from the entry: a server crash after `on_submit` commits but before `after_submit` runs would leave the entry committed with no discrepancies, violating FR-001's "same transaction" requirement.
- *Detection enqueued as a background job fired from `on_submit`* — rejected. Same problem (entry commits before the job runs; job may fail silently). Also overkill for the actual workload (at most ~20 discrepancy documents per submit, well below the 100-record synchronous threshold from constitution VIII).
- *Detection as a separate `doc_events` hook on `Purisol Coupon Consumption Entry`* — rejected for code-locality reasons. The detection logic is tightly coupled to "this entry's coupons + this entry's touched booklets"; an external hook adds indirection without isolation benefit since it would still run in the same transaction.

---

## 2. How is the Missing-Coupons gap computed exactly?

**Decision**: For each distinct booklet `B` in the submitting entry's `coupons` child table:

1. Read every coupon of `B` from the DB (`frappe.get_all("Purisol Coupon", filters={"booklet": B}, fields=["name", "page_number", "status"])`). All 20 rows, single indexed query per booklet.
2. From that list, compute `consumed_pages = {r.page_number for r in rows if r.status == "Consumed"}`. Because detection runs post-Phase-4, this set **includes** the coupons just flipped by this entry.
3. If `len(consumed_pages) < 2`: no gap is possible, skip this booklet for Missing Coupons.
4. Else `lo = min(consumed_pages)`, `hi = max(consumed_pages)`; `gap_pages = set(range(lo + 1, hi)) - consumed_pages`. `gap_pages` is the "interior gap" — every page number strictly between the lowest and highest consumed page that is not itself consumed.
5. Filter to `Available` (a gap page whose coupon is somehow `Consumed` would contradict step 2, but defensively): `gap_rows = [r for r in rows if r.page_number in gap_pages and r.status == "Available"]`.
6. Subtract dedup set: `open_names = _list_open_missing_coupon_names(B)` (names of coupons listed in `affected_coupons` of any Open Missing Coupons discrepancy for `B`). `new_rows = [r for r in gap_rows if r.name not in open_names]`.
7. If `new_rows` is empty: no discrepancy, next booklet. Otherwise create one `Purisol Coupon Discrepancy` of type `Missing Coupons` for `B` listing `new_rows`.

**Rationale**:
- The "union of previously-consumed + now-consumed" in spec FR-003 is identical to "all coupons with status=Consumed after this submit", because Phase 4 already flipped the current entry's coupons in the same transaction before detection runs. We never need to read "the current entry's coupons" separately.
- Coupon `page_number` is 1–20 and is the natural ordering key. The spec talks in terms of coupon numbers (`CP-00003`), but those are app-level names; the gap is defined on the page number within the booklet. Per-booklet page numbers are always 1..20 and monotonic, so "min..max" is unambiguous.
- Steps 6 is the idempotence layer (FR-010). Resolved discrepancies don't count — an admin who resolved a gap as "Admin Error" may legitimately want the system to re-flag the gap later if the same coupons remain Available (spec Assumption on dedup). We only dedupe against `status = "Open"`.
- All work is in-memory per booklet (at most 20 rows) plus one indexed `frappe.get_all` for the dedup; constant-time per booklet.

**Alternatives considered**:
- *Compute gap only from the current-entry's coupons* — rejected. Would miss the whole point of the feature (spec Acceptance Scenario 1.2: the union of previously-consumed coupons `{1,2}` plus newly-consumed `{7,8}` produces the correct gap `{3,4,5,6}`).
- *Compute gap from an absolute 1..20 range minus Consumed* — rejected. Would flag every unconsumed prefix/suffix (e.g. `{15..20}` when `{1..14}` are consumed), which is exactly what the spec Edge Cases "Gap below min" and "Gap above max" say should **not** fire.
- *Store the gap as a page-number range `[lo..hi]` instead of enumerating each affected coupon* — rejected. `affected_coupons` is a list of concrete coupons (FR-003) so each missing coupon can be traced back to a concrete physical page when the administrator investigates; the user story's "listed in `affected_coupons`" language assumes per-coupon rows.

---

## 3. How is `estimated_amount` computed?

**Decision**: `estimated_amount = coupon_unit_price × len(affected_coupons)`, with `coupon_unit_price` resolved in this order:

1. **Sales Invoice line** — If `booklet.sales_invoice` is set (set by Phase 3 on booklet sale), `frappe.get_all("Sales Invoice Item", filters={"parent": booklet.sales_invoice, "purisol_booklet": booklet.name}, fields=["rate", "qty"], limit=1)`. The item's `qty` is 1 (one Sales Invoice Item per booklet, per Phase 3) and `rate` is the per-booklet rate. `coupon_unit_price = rate / 20`.
2. **Price list fallback** — If step 1 produced nothing (e.g., booklet has no invoice, i.e. this is an Unassigned Booklet discrepancy), read `settings = frappe.get_cached_doc("Purisol Settings")`. If `settings.coupon_item` and `settings.default_price_list` are both set, `frappe.get_all("Item Price", filters={"item_code": settings.coupon_item, "price_list": settings.default_price_list}, fields=["price_list_rate"], limit=1)`. If a row exists, `coupon_unit_price = price_list_rate / 20`.
3. **Zero fallback** — If neither step yielded a rate, `coupon_unit_price = 0.0` and `estimated_amount = 0.0`. Spec Assumption: "the Administrator edits it manually before resolving".

**Rationale**:
- Matches the spec Assumption verbatim. Keeps Phase 5 self-contained by reusing Phase 3's Sales Invoice integration (the custom field `Sales Invoice Item.purisol_booklet` already exists — it's in the fixture list in `hooks.py`).
- Division by 20 is the correct per-coupon factor because one booklet contains exactly 20 coupons (enforced by Phase 1).
- The fallback cascade means the admin sees a sensible default in the common case (Sold booklet with invoice) and a manual-edit prompt in the rare case (Unassigned Booklet with no invoice).

**Alternatives considered**:
- *Always use the price list, regardless of invoice* — rejected. If a customer got a promotional price at sale time, the discrepancy should value the missing coupons at the price the shop actually charged, not today's list price.
- *Snapshot the price on the discrepancy at detection time and never recompute* — partially adopted. The Administrator can edit `estimated_amount` on the draft discrepancy before submit; once submitted, the amount is frozen via ERPNext's locked-submittable semantics. Re-computing on every save would fight the administrator's manual override.
- *Use `frappe.get_cached_doc` for Item Price lookup* — rejected. Item Price rows can change frequently and caching them app-wide would waste memory; a single indexed `frappe.get_all` is cheaper.

---

## 4. How are `related_delivery_men` auto-populated?

**Decision**: Called immediately after the parent `Purisol Coupon Discrepancy` is built but before `.insert()`, `_auto_populate_related_delivery_men(doc, entry, booklet)` runs:

1. **Custody Holder row** — If `booklet.status == "In Custody"`, read the most-recent submitted `Purisol Custody Entry` whose `Purisol Custody Entry Booklet` child rows include `booklet.name` and whose `entry_type = "Assign"` (i.e., the custody entry that put the booklet into the current holder's possession). Append `{delivery_man: entry.delivery_man, role: "Custody Holder", custody_entry: entry.name, consumption_entry: None}`. If the booklet's status is not `In Custody`, skip this row (spec Acceptance Scenario 6.2).
2. **Submitted Adjacent Coupons rows** — Read every distinct `delivery_man` who has submitted (`docstatus = 1`) any `Purisol Coupon Consumption Entry` referencing `booklet` (i.e. whose `coupons.booklet = booklet.name`) whose `posting_date >= entry.posting_date - 30 days` AND which is not `entry` itself. For each distinct `(delivery_man, most_recent_entry_referencing_booklet)`, append `{delivery_man, role: "Submitted Adjacent Coupons", custody_entry: None, consumption_entry: entry_name}`. If the triggering entry's own delivery_man is the only touchpoint and the booklet is not `In Custody`, that delivery_man appears as `Submitted Adjacent Coupons` referencing `entry` itself — spec Acceptance Scenario 6.2 implies this (booklet is Sold, no custody holder, and the triggering entry's delivery_man should still be surfaced as a candidate).
3. **Deduplication** — An employee who is both the current custody holder and who submitted entries within 30 days appears **once** with `role = "Custody Holder"` (the more-specific role wins). Implemented by building the `Custody Holder` set first, then filtering the 30-day adjacency set.

**Rationale**:
- Spec FR-007 specifies exactly this structure. The 30-day window is anchored to `entry.posting_date` per spec Assumption (not to `now()`), so back-dated entries are handled deterministically.
- The custody-entry reference in step 1 is essential for Story 6's "click-through from the related-person row to the custody entry that caused them to show up".
- Querying via `Purisol Custody Entry Booklet` child rows (with `entry_type = "Assign"`) is the correct way to find the most-recent custody assignment — Phase 2 established this pattern, and `booklet.current_delivery_man` is the cache field that derives from it.
- The 30-day window query is cheap: `Purisol Coupon Consumption Entry.posting_date` is indexed, and at single-shop scale the candidate set is tiny (dozens of entries per month).

**Alternatives considered**:
- *Use `booklet.current_delivery_man` directly instead of querying the Custody Entry* — rejected. We need the custody entry's name for the `custody_entry` reference field on the child row; `current_delivery_man` is just the employee name.
- *Include all historical adjacent delivery men, not just the last 30 days* — rejected. The spec explicitly specifies 30 days (FR-007) and widening the window pollutes the shortlist with stale candidates.
- *Separate the triggering entry's delivery_man out into a dedicated "Triggering Delivery Man" role* — rejected. Spec only defines two roles (`Custody Holder`, `Submitted Adjacent Coupons`); the triggering delivery_man falls naturally into the second.

---

## 5. How is Unassigned-Booklet detection shaped?

**Decision**: Per-coupon, not per-booklet. For each row in `entry.coupons`, fetch `booklet.status`; if `booklet.status != "Sold"`, create **one** `Purisol Coupon Discrepancy` of type `Unassigned Booklet` whose `affected_coupons` contains exactly the row's coupon (list of length 1), with `customer = null` (the booklet has no customer if it isn't Sold). No dedup is needed — each coupon is submitted at most once across all entries (enforced by the coupon state machine: `Consumed` can only transition back to `Available` via cancel, which re-opens the path for fresh detection only on the next consumption; this is rare and intended).

**Rationale**:
- Spec Acceptance Scenario 2.3: "three coupons `CP-00025, CP-00026, CP-00027` all from the same unassigned booklet → three distinct discrepancies". Per-coupon granularity matters because the resolution path (`Add to Liability Ledger`) sets amount on each discrepancy independently — a customer could decide to pay for some but not others.
- FR-004 explicitly mandates per-coupon ("creating one `Purisol Coupon Discrepancy` per such coupon").
- "Status not Sold" is the rule — In Stock, In Custody, or even the theoretical Depleted all trigger (spec Acceptance Scenario 2.2). The rule is deliberately not "is In Stock"; it's "is not Sold".

**Alternatives considered**:
- *Create one per-booklet discrepancy listing every unassigned coupon* — rejected. Would diverge from Acceptance Scenario 2.3 and conflate independently-resolvable anomalies.
- *Check booklet.customer instead of booklet.status* — rejected. A booklet can have `customer` set (e.g. a historical retroactive assignment edge case) while `status` is not `Sold`; the authoritative signal is `status`.

---

## 6. How is resolution-submit atomicity maintained?

**Decision**: All resolution side effects — `Journal Entry` creation for "Add to Liability Ledger", `Payment Entry` creation for "Immediate Cash Payment" — happen in `before_submit`, not `on_submit`. Reason: `before_submit` runs inside the submit transaction before the parent's `docstatus` flip; any throw there cleanly rolls back (the parent discrepancy stays in draft, no JE/PE is partially created). Both helpers call `.insert()` then `.submit()` on the created ERPNext primitive; a Frappe-native `frappe.ValidationError` inside the primitive's own validation propagates out, rolling both the primitive and the discrepancy back. On success, the helper stores the created document's name on `self.journal_entry` / `self.payment_entry`, which persists when the discrepancy submit commits.

**Rationale**:
- Spec FR-013 last sentence: "If any step fails, the whole resolution submit MUST roll back."
- Using `before_submit` (instead of `on_submit`) for the side effects is the idiomatic Frappe pattern for "conditional submit" — `on_submit` is conventionally for post-commit fan-out (notifications, etc.), while `before_submit` is where preconditions and coupled writes live.
- The JE's and PE's own validations (e.g., Journal Entry requires the debits and credits to balance) run automatically inside `.submit()` — we don't need to pre-validate the accounts; ERPNext does that for us. If `employee_liability_account` doesn't exist as an `Account`, ERPNext's link integrity rejects the JE insert and we see that error.

**Alternatives considered**:
- *Two-phase submit (persist to draft, then enqueue JE creation)* — rejected. Breaks the atomicity contract and introduces an ambiguous intermediate state ("discrepancy resolved but no JE yet").
- *Validate account existence explicitly before creating the primitive* — partially adopted. We do check `Purisol Settings.employee_liability_account` is set (non-null) in `before_submit` so we can throw a clean `_("Employee liability account is not configured in Purisol Settings.")` error. Whether that account actually exists as an `Account` is ERPNext's job to check.

---

## 7. Journal Entry shape for "Add to Liability Ledger"

**Decision**:

```
JournalEntry
  voucher_type = "Journal Entry"
  posting_date = today
  company      = default company (from Global Defaults; ERPNext default)
  user_remark  = _("Discrepancy {0} — liable {1}").format(discrepancy.name, liable_delivery_man)
  accounts:
    [0]
      account        = Purisol Settings.employee_liability_account
      party_type     = "Employee"
      party          = discrepancy.liable_delivery_man
      debit_in_account_currency = discrepancy.estimated_amount
    [1]
      account        = Purisol Settings.discrepancy_offset_account
      credit_in_account_currency = discrepancy.estimated_amount
```

Plus a reference in the JE's `reference_doctype` / `reference_name` pointing at the discrepancy (via the parent doc metadata, not via a child-line reference — ERPNext's convention for custom "cause of JE" linkages).

**Rationale**:
- ERPNext's `Journal Entry` requires at least two account lines whose debits and credits balance. Spec FR-013 is explicit about which account is debited and which is credited.
- `party_type = "Employee"` + `party = <delivery_man>` is the canonical ERPNext way to attach the JE amount to a specific employee's ledger (so the amount shows up in the Employee Ledger report and can be deducted on a Salary Slip, matching spec User Story 4's last sentence).
- User remark is localized and traceable back to the discrepancy.
- No reference row inside the child `accounts` table is needed because the party_type/party on the debit line handles the employee linkage; the discrepancy-level reference on the JE parent gives auditors a click-through.

**Alternatives considered**:
- *Put the discrepancy reference in each account row's `reference_type`/`reference_name`* — rejected. Those columns in ERPNext are for linking a JE line to an invoice for auto-reconciliation, not a general "cause of this transaction" link.
- *Create two JEs (one per account)* — rejected; ERPNext requires balance within a single JE.

---

## 8. Payment Entry shape for "Immediate Cash Payment"

**Decision**:

```
PaymentEntry
  payment_type     = "Receive"
  posting_date     = today
  company          = default company
  paid_from        = Purisol Settings.discrepancy_offset_account
  paid_to          = Purisol Settings.default_cash_account
  paid_amount      = discrepancy.estimated_amount
  received_amount  = discrepancy.estimated_amount
  party_type       = "Employee"            # optional; helps the PE appear on employee transactions
  party            = discrepancy.liable_delivery_man
  references:
    [0]
      reference_doctype = "Purisol Coupon Discrepancy"
      reference_name    = discrepancy.name
      allocated_amount  = discrepancy.estimated_amount
```

**Rationale**:
- Payment Entry is the ERPNext primitive for cash moving between accounts; `payment_type = "Receive"` + `paid_from = <offset account>` + `paid_to = <cash account>` is the canonical shape of "cash coming in against an adjustment liability".
- The `references` row makes the PE traceable back to the discrepancy from standard ERPNext cash-flow reports (spec FR-015, User Story 5 Acceptance Scenario 4).
- `party_type = "Employee"` is optional on a receive-against-offset-account payment, but including it makes the PE show up in employee-transaction reports, which matches the business semantics of "this delivery man paid cash".
- ERPNext auto-generates a `name` for the PE; we save the name on `discrepancy.payment_entry`.

**Alternatives considered**:
- *Use Journal Entry for cash payment too* — rejected. ERPNext convention is that cash movement uses `Payment Entry`, not `Journal Entry`; using JE here would break bank reconciliation workflows.
- *Skip the `party_type` + `party` on the PE* — rejected. Removes traceability from the delivery-man-transactions report.

---

## 9. Where does the post-submit modal come from?

**Decision**: Render as `frappe.msgprint({ message, title, indicator, wide })` from the JS `frm.on("submit")` handler on `Purisol Coupon Consumption Entry`, using the live `frm.doc.discrepancies_detected` table that the server controller just populated. The handler checks `frm.doc.has_warnings == 1` and `frm.doc.discrepancies_detected.length > 0`; if both, builds an HTML block listing each discrepancy (name rendered as an anchor to `/app/purisol-coupon-discrepancy/<name>`, plus type and booklet columns) and shows it via `frappe.msgprint`. Title: `__("Discrepancies detected")`. Indicator: `"orange"`. `wide = true` so the list has room.

**Rationale**:
- Spec FR-009 mandates "non-blocking" — `frappe.msgprint` with `indicator: "orange"` is exactly that (the user can dismiss; the submit already committed). Anything that blocks (e.g. `frappe.prompt`) would violate FR-002.
- Using the already-populated `discrepancies_detected` child table means no extra server round-trip to fetch the list — the data is on the client by the time `after_save` fires.
- Rendering as HTML (via `frappe.msgprint` with a `message` string containing anchor tags) gives the administrator one-click navigation to each discrepancy, matching the spec's "click-through link per entry" (FR-009, SC-010).

**Alternatives considered**:
- *Use `frappe.show_alert`* — rejected. Alert is too ephemeral (auto-dismisses in 5 s) and doesn't render HTML links well.
- *Use a custom Frappe dialog (`new frappe.ui.Dialog`)* — rejected. Adds complexity for a simple read-only listing; `msgprint` is the idiomatic Frappe choice.
- *Emit a `frappe.publish_realtime` event and have a system-wide handler render the modal* — rejected. Overkill for a synchronous submit-success message on the same user's browser.

---

## 10. How does Phase 5 interact with the Phase 4 test suite?

**Decision**: Phase 4's `test_purisol_coupon_consumption_entry.py` has assertions of the form "after submit, `has_warnings == 0` and `discrepancies_detected` is empty". These assertions need to be updated, not deleted — the Phase-5 semantics are "after submit, `has_warnings == 0` **iff no anomaly was detected** and `discrepancies_detected` is empty **iff no discrepancy was created**". Because the Phase-4 tests seed a fully-valid state (Sold booklet, all coupons Available, no gap), Phase 5's detection would naturally not fire — so the assertions remain true, but their spelling changes from "always zero" to "zero for this seeded state".

Phase 4's defensive guards (`validate` throws on `has_warnings == 1` or non-empty `discrepancies_detected`) are explicitly **removed** in Phase 5. Tests that asserted those guards threw ("attempting to set has_warnings manually") are repurposed to assert that the fields are still `read_only = 1` on the **form** (controllers can write them, but admins cannot).

**Rationale**:
- Running Phase-4 tests unchanged would immediately fail post-Phase-5 because the guards that made those tests pass have been removed. Proactively updating the tests is cleaner than bundling the change later.
- The "read-only on form, writable from controller" distinction is important — it preserves the spec's integrity (admin can't manually fake a `has_warnings` flag) without letting the Phase-4 guard interfere with Phase-5 detection's legitimate writes.
- Phase-4 integration tests (`tests/test_consumption_flows.py`) already seed a fully-valid state and never cover a discrepancy-triggering path, so none of them start creating discrepancies as a Phase-5 side effect. The assertion "no discrepancies created" continues to hold for those tests; we just reinterpret it as "the seeded state had no anomaly", not "detection was skipped".

**Alternatives considered**:
- *Leave the Phase-4 guards in place and have the Phase-5 detection bypass them via `flags.ignore_validate`* — rejected. Leaves dead code in `validate` and couples Phase-5 to a Phase-4 implementation detail. Cleaner to remove the guards and widen the controller.
- *Create a new controller subclass for Phase 5* — rejected. The Consumption Entry is a single DocType; subclassing for a behaviour change would violate Frappe's convention (DocType controllers are 1:1 with their JSON).

---

## 11. Amend-disabled semantics

**Decision**: The `Purisol Coupon Discrepancy` DocType JSON's permission set has `amend = 0` for every role. This disables the "Amend" button Frappe would otherwise offer on a cancelled/submitted doc.

**Rationale**:
- Spec FR-017: "amendment is not permitted and any correction goes through a separate reversing Journal Entry or Payment Entry."
- Constitution IV: audit trail by default — amending a submitted record would replace the history with a new version that hides the original. Reversing JE/PE preserves both.

**Alternatives considered**:
- *Allow amend but override `before_amend` to always throw* — rejected. Shows an amend button that then errors, which is a bad UX; disabling the permission hides the button entirely.
- *Use a custom `allow_amend` DocType setting* — not a real Frappe property; permissions are the right level for this.

---

## 12. Where does the "Open Discrepancies" list view live?

**Decision**: Add a `doctype_list_js` entry in `hooks.py` pointing at `public/js/purisol_coupon_discrepancy_list.js` — but do not use `public/js/`; colocate the list script inside the DocType folder (`doctype/purisol_coupon_discrepancy/purisol_coupon_discrepancy_list.js`) following the convention already established by Phase 3. The script sets `frappe.listview_settings["Purisol Coupon Discrepancy"]` with `onload: listview => listview.filter_area.add("Purisol Coupon Discrepancy", "status", "=", "Open")` — but only when the user hasn't applied their own filter in the URL.

Alternatively — simpler and more idiomatic — create a **saved ERPNext List View** via fixture, named "Open Discrepancies", filtered to `status = "Open"` and `sort by opened_on desc`. This shows up as a selectable saved view in the list header without any custom JS.

**Decision revised**: Ship the saved-list-view fixture; skip the JS. Simpler, no runtime code, ERPNext-native.

**Rationale**:
- Fixture-driven saved views are ERPNext's idiomatic way to ship pre-configured list filters (spec FR-018 says "available to the `Purisol Administrator` role", which a role-scoped list view covers).
- Zero client-script code to maintain — the fixture is a single JSON record.
- No need to worry about "what if the admin has applied another filter" — the saved view is a named alternate filter, not a forced one.

**Alternatives considered**:
- *Default the list view's filter via `listview_settings.onload`* — rejected in favour of the saved view (cleaner). If the saved view turns out to not meet the requirement in the Phase-5 QA pass, we can add the JS fallback in a follow-up without schema churn.

---

## 13. What does the `Purisol Coupon Discrepancy Item` widening look like?

**Decision**: Phase 4 created this child-table stub with only a `notes` field. Phase 5 adds:

- `discrepancy` — Link → `Purisol Coupon Discrepancy`, `reqd = 1`, `in_list_view = 1`. The actual pointer.
- `discrepancy_type` — Select with options `Missing Coupons\nUnassigned Booklet`, `fetch_from = discrepancy.discrepancy_type`, `read_only = 1`, `in_list_view = 1`. So the row display shows the type without the admin clicking through.

Field order updated in JSON. The `notes` field stays but is optional. No controller code change (empty Document subclass continues to suffice).

**Rationale**:
- The widening is strictly additive — no rename, no retype, no delete — so existing Phase-4 DB rows (of which there are exactly zero, since Phase 4 rejected any non-empty `discrepancies_detected`) remain valid.
- `fetch_from` is Frappe's standard way to denormalize a linked value for list display without needing a join; matches the pattern in `Purisol Coupon Consumption Item.booklet`.

**Alternatives considered**:
- *Introduce a wholly new child table named `Purisol Consumption Entry Discrepancy Row`* and repoint the parent's `discrepancies_detected` table to it — rejected. Violates Phase 4's explicit design decision (data-model.md §3) to reserve the stub specifically for Phase-5 additive widening. Pointing the parent at a new table would force a patch to migrate (empty) rows, for no benefit.
- *Add the `discrepancy` link and drop the `notes` field* — rejected. Harmless to keep; removing it would be a schema delete that buys nothing.

---

## 14. Testing: how do we seed discrepancies for resolution-only tests?

**Decision**: Extend `cx_purisol/cx_purisol/tests/fixtures.py` with a helper `seed_open_discrepancy(*, discrepancy_type, booklet, customer=None, triggering_entry=None, affected_coupons=(), estimated_amount=0.0)` that constructs a `Purisol Coupon Discrepancy` directly, bypassing the detection service, and `.insert()`s it in draft. Resolution tests then set `liable_delivery_man` / `resolution_action` / settings accounts and `.submit()` to exercise the resolution path in isolation.

**Rationale**:
- Detection and resolution are architecturally orthogonal concerns. Testing them together every time is both slow (requires a full Consumption Entry seed) and noisy (a resolution-path failure shouldn't be masked by an orthogonal detection-setup bug).
- Direct insertion is legitimate because every field we'd otherwise get from the detection service is trivially specifiable in the test. The `validate` hook still runs on insert, so structural invariants (e.g., `affected_coupons` is non-empty, `booklet` resolves) still get exercised.

**Alternatives considered**:
- *Always go through the detection path in tests* — rejected for the reasons above (slower, noisier).
- *Expose a whitelisted API to create discrepancies* — rejected. No production need for external discrepancy creation; only the Consumption Entry controller should do it. Tests bypass via the DocType API directly, same as any other Frappe test.

---

## 15. Is a patch needed?

**Decision**: Yes — one post-model-sync entry, `cx_purisol.patches.v0_5_0.relax_consumption_entry_reserved_guards`. The patch body is a no-op with a single `frappe.msgprint` announcing Phase-5 migration on the site. Matches the Phase 2/3/4 pattern (those patches are also effectively no-op anchors).

**Rationale**:
- On fresh installs, the widened JSON + widened controller both land from the start; nothing to migrate.
- On upgraded sites, no existing data needs conversion (Phase 4 rejected any non-empty discrepancy table, so no real rows exist; the `Purisol Coupon Discrepancy Item` stub becomes a real table entry when the JSON merges on migrate).
- Having an explicit anchor makes it easy to tell "did this site go through Phase 5?" by inspecting the `tabPatch Log` table.

**Alternatives considered**:
- *Skip the patch entirely* — rejected. The anchor pattern is consistent across phases; skipping it introduces a gap that is harder to reason about during maintenance than a no-op entry.
