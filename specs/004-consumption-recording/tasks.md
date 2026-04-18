---
description: "Task list for implementing Consumption Recording (Phase 4)"
---

# Tasks: Consumption Recording

**Input**: Design documents from `/specs/004-consumption-recording/`
**Prerequisites**: plan.md (✓), spec.md (✓), research.md (✓), data-model.md (✓), contracts/consumption-recording.md (✓), quickstart.md (✓)

**Tests**: Tests are explicitly required — the spec's SC-005, SC-008, SC-009 and Constitution Principle X mandate unit, API, and integration tests. Test tasks are included below.

**Organization**: Tasks are grouped by user story so each story can be implemented, merged, and demoed as an independent increment. Foundational work (new DocTypes + widened state machines) must land before any user story, because the four user stories share the same submit/cancel seam.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no unmet dependencies)
- **[Story]**: Maps task to the user story it serves (US1, US2, US3, US4)
- File paths are absolute to the repo root unless otherwise noted

## Path Conventions

Frappe custom-app layout, consistent with Phases 1–3:

- App package root: `cx_purisol/cx_purisol/` (Python) and `cx_purisol/public/js/` (assets)
- DocType folders: `cx_purisol/cx_purisol/doctype/<name>/`
- Whitelisted APIs: `cx_purisol/cx_purisol/api/`
- Shared test fixtures: `cx_purisol/cx_purisol/tests/`
- Patches: `cx_purisol/patches/v0_4_0/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffolding on disk so later tasks can create JSON / Python files in place.

- [x] T001 Create DocType folders and empty `__init__.py` at `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/__init__.py`, `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_item/__init__.py`, and `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy_item/__init__.py`; ensure `cx_purisol/cx_purisol/api/__init__.py` exists; ensure `cx_purisol/cx_purisol/tests/__init__.py` exists
- [x] T002 Create Phase-4 anchor patch at `cx_purisol/patches/v0_4_0/__init__.py` (empty) and `cx_purisol/patches/v0_4_0/widen_states_for_consumption.py` (no-op `execute()` that prints a single log line); append `cx_purisol.patches.v0_4_0.widen_states_for_consumption` to `cx_purisol/patches.txt`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: DocType JSONs, widened state machines, parent-controller skeleton, and the shared test-fixtures helper that every user story builds on.

**⚠️ CRITICAL**: No user story work can begin until Phase 2 is complete — all four stories invoke the same submit/cancel seam.

- [x] T003 [P] Create child-table DocType JSON at `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_item/purisol_coupon_consumption_item.json` with `istable = 1`, `track_changes = 1`, and fields `coupon` (Link Purisol Coupon, reqd, search-indexed, in_list_view), `booklet` (Link Purisol Coupon Booklet, read_only, `fetch_from = coupon.booklet`, in_list_view), `customer` (Link Customer, read_only, `fetch_from = coupon.booklet.customer`, in_list_view) — per data-model §2.2
- [x] T004 [P] Create empty controller stub at `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_item/purisol_coupon_consumption_item.py` (`class PurisolCouponConsumptionItem(Document): pass`) — per data-model §2.3
- [x] T005 [P] Create reserved-empty child-table stub DocType JSON at `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy_item/purisol_coupon_discrepancy_item.json` with `istable = 1`, `track_changes = 1`, single `notes` field (Small Text) — Phase-5 placeholder per data-model §3
- [x] T006 [P] Create empty controller stub at `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy_item/purisol_coupon_discrepancy_item.py`
- [x] T007 [P] Create parent DocType JSON at `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/purisol_coupon_consumption_entry.json` with `is_submittable = 1`, `track_changes = 1`, `autoname = PCC-.YYYY.-.#####`, `search_fields = delivery_man,posting_date`, fields `posting_date` / `posting_time` / `delivery_man` (Link Employee, reqd) / `received_by` (Link User, read_only) / `coupons` (Table → Purisol Coupon Consumption Item, reqd) / `total_coupons` (Int, read_only) / `has_warnings` (Check, read_only, default 0) / `discrepancies_detected` (Table → Purisol Coupon Discrepancy Item, read_only) / `notes` (Small Text) plus the three Section Breaks, and `permissions` granting create/write/submit/cancel/amend/print/read to `Purisol Administrator` only — per data-model §1.1–§1.3
- [x] T008 Create parent controller skeleton at `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/purisol_coupon_consumption_entry.py` with (a) `PurisolCouponConsumptionEntry(Document)` class, (b) `posting_datetime` `@property` returning `frappe.utils.get_datetime(f"{self.posting_date} {self.posting_time}")`, (c) `before_insert` stamping `self.received_by = frappe.session.user`, (d) `validate` computing `self.total_coupons = len(self.coupons or [])` and raising on empty table (FR-030), duplicate `coupon` across rows (FR-032), `has_warnings != 0` (FR-035 defensive), any row in `self.discrepancies_detected` (FR-035 defensive) — all error messages wrapped in `frappe._()`; (e) placeholder `before_submit`/`on_submit`/`on_cancel` methods with `pass` (filled in by later stories)
- [x] T009 [P] Widen `cx_purisol/cx_purisol/doctype/purisol_coupon/purisol_coupon.py` — set `_ALLOWED_STATUSES = {"Available", "Consumed"}` and `_ALLOWED_TRANSITIONS = {("Available", "Consumed"), ("Consumed", "Available")}`; keep the page_number range check and frozen-field check on `booklet`/`page_number`/`coupon_number`; update `validate` to raise on out-of-set statuses and on disallowed prior→new transitions, using translated messages — per data-model §4
- [x] T010 [P] Widen `cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/purisol_coupon_booklet.py` — extend `_ALLOWED_STATUSES` to include `"Depleted"`, extend `_ALLOWED_TRANSITIONS` with `("Sold", "Depleted")` and `("Depleted", "Sold")`; no other change to the existing validate body — per data-model §5
- [x] T011 [P] Extend `cx_purisol/cx_purisol/tests/fixtures.py` with `make_sold_booklet_ready_for_consumption(customer_name="Acme Co.", employee_name="Ali", booklet_name=None)` — seeds an ERPNext Customer, an ERPNext Employee, runs the Phase-1 `purisol_generate_booklets` helper for one booklet, drives it `Sold` via the Phase-3 `purisol_create_sales_invoice_for_booklets` + `si.submit()` flow, and returns `(customer_name, employee_doc, booklet_name, [coupon_names])` — per research.md §12

**Checkpoint**: Foundation ready. Every user story below can start.

---

## Phase 3: User Story 1 — Record Consumption by Picking Coupons from a Booklet (Priority: P1) 🎯 MVP

**Goal**: Administrator creates a Consumption Entry, picks a delivery man, enters booklets in Mode A, ticks Available coupons, clicks Add to Entry, and submits. On submit, every listed coupon transitions `Available → Consumed` with the three consumption-metadata fields stamped, and every touched booklet's `consumed_count` / `remaining_count` are recomputed — all in one transaction. Cancel reverses.

**Independent Test**: Seed one Sold booklet `WP-00001` with 20 Available coupons and one Employee `Ali`. Create a Consumption Entry with `delivery_man=Ali`, pick `WP-00001` in Mode A, tick `CP-00001`–`CP-00003`, Add to Entry, submit. Verify the three coupons are `Consumed` with correct metadata, `WP-00001.consumed_count = 3`, `remaining_count = 17`, booklet still `Sold`. Cancel the entry: verify all three revert to `Available` with cleared metadata and `consumed_count = 0`.

### Implementation for User Story 1

- [x] T012 [US1] Implement `on_submit` in `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/purisol_coupon_consumption_entry.py` — per row: `frappe.db.set_value("Purisol Coupon", row.coupon, {"status": "Consumed", "consumed_on": self.posting_datetime, "consumed_by_delivery_man": self.delivery_man, "consumption_entry": self.name}, update_modified=True)`; then for each distinct `row.booklet` across `self.coupons`: `consumed_count = frappe.db.count("Purisol Coupon", {"booklet": b, "status": "Consumed"})`, `remaining_count = 20 - consumed_count`, load the booklet via `frappe.get_doc`, set both fields, `booklet.save(ignore_permissions=True)`; **do not** implement the `consumed_count == 20 → Depleted` branch yet (US3 adds it)
- [x] T013 [US1] Implement `on_cancel` in the same parent controller — per row: `frappe.db.set_value("Purisol Coupon", row.coupon, {"status": "Available", "consumed_on": None, "consumed_by_delivery_man": None, "consumption_entry": None}, update_modified=True)`; for each distinct booklet: recompute `consumed_count` / `remaining_count` via the same helper and `booklet.save(ignore_permissions=True)`; **do not** implement the `Depleted → Sold` revert branch yet (US3 adds it)
- [x] T014 [US1] Create whitelisted endpoint `list_available_coupons(booklet: str) -> list[dict]` at `cx_purisol/cx_purisol/api/consumption.py` — begin with `frappe.only_for("Purisol Administrator")`; raise translated `_("Booklet name is required.")` when `booklet` is empty; return `frappe.get_all("Purisol Coupon", filters={"booklet": booklet, "status": "Available"}, fields=["name as coupon", "page_number"], order_by="page_number asc")`; unknown booklet returns `[]` (never raises) — per contracts §3
- [x] T015 [US1] Create form client script `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/purisol_coupon_consumption_entry.js` — hook `frappe.ui.form.on("Purisol Coupon Consumption Entry", { refresh(frm) { ... } })`; inject a mode switcher (two toggle buttons / radio: "By Booklet" vs "By Coupon Number", default Mode A); Mode A panel: booklet Link autocomplete + a call to `cx_purisol.cx_purisol.api.consumption.list_available_coupons` that renders a checkbox list of `{coupon, page_number}`; "Add to Entry" button loops ticked rows, calls `frm.add_child("coupons", {coupon})` per tick, `frm.refresh_field("coupons")`, clears the checklist; reserve a placeholder section for the Mode B panel (filled by T021); all strings wrapped in `__()` — per research.md §8

### Tests for User Story 1

- [x] T016 [P] [US1] Unit tests at `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/test_purisol_coupon_consumption_entry.py` — `FrappeTestCase` subclass, uses `make_sold_booklet_ready_for_consumption`; assert (a) validate rejects empty `coupons` with translated FR-030 message, (b) validate rejects duplicate `coupon` in `coupons` naming the dup, (c) validate rejects `has_warnings = 1` (FR-035), (d) validate rejects a manually-added row in `discrepancies_detected` (FR-035), (e) `before_insert` stamps `received_by = frappe.session.user` and it is not editable on reload, (f) `total_coupons` equals `len(coupons)` after validate
- [x] T017 [P] [US1] Extend `cx_purisol/cx_purisol/doctype/purisol_coupon/test_purisol_coupon.py` with Phase-4 transition tests — assert (a) `Available → Consumed` permitted (simulated by `frappe.db.set_value` + `frappe.get_doc(...).save(ignore_permissions=True)`), (b) `Consumed → Available` permitted, (c) any other target status raises `frappe.ValidationError` with the "not allowed" message, (d) direct form-style write to `consumed_on` while `status` stays `Available` is still rejected by the frozen-field guard (if the old test asserted the Phase-1 "must be Available" invariant, update it to the widened rule)
- [x] T018 [P] [US1] API tests at `cx_purisol/cx_purisol/api/test_consumption.py` for `list_available_coupons` — (a) non-`Purisol Administrator` caller raises `frappe.PermissionError`; (b) happy path: 20 Available coupons of `WP-00001` return 20 rows sorted by `page_number`; (c) after marking 3 as `Consumed` directly in DB, the endpoint returns only 17 rows; (d) unknown `booklet` returns `[]`; (e) empty `booklet` raises with translated "required" message
- [x] T019 [P] [US1] Integration tests at `cx_purisol/cx_purisol/tests/test_consumption_flows.py` — `FrappeTestCase` subclass using the fixtures helper; tests: (a) `test_mode_a_three_coupons_happy_path` — submit entry with 3 coupons from one booklet, assert all post-conditions from contracts §1.2 (coupons `Consumed` with triple metadata; booklet aggregates = 3 / 17; other 17 coupons untouched); (b) `test_mode_a_multi_booklet_single_entry` — seed two Sold booklets, submit one entry with 2 coupons from each; assert all 4 coupons `Consumed` and both booklets' aggregates updated in the same submit; (c) `test_cancel_round_trip_no_depletion` — submit the 3-coupon entry, cancel it, assert every coupon reverts to `Available` with cleared metadata and booklet back to `consumed_count = 0` / `remaining_count = 20` / `status = Sold` (no depletion to revert yet)

**Checkpoint**: Story 1 is demoable. The system can record coupon consumption end-to-end via Mode A, and cancel reverses it. Depletion and Mode B are not yet functional.

---

## Phase 4: User Story 2 — Record Consumption by Typing or Pasting Coupon Numbers (Priority: P2)

**Goal**: Administrator switches to Mode B, types or pastes coupon numbers, each Enter resolves the coupon and appends a row to the same child table Mode A writes to. Mode A and Mode B may be freely mixed in one entry; submit processes all rows identically.

**Independent Test**: Seed two Sold booklets `WP-00001` (customer Acme) and `WP-00002` (customer Beta), each with 20 Available coupons. Create a Consumption Entry, set delivery man, switch to Mode B, paste `CP-00001\nCP-00022\nCP-99999`; assert two rows land with correct auto-filled booklet/customer and `CP-99999` shows an inline red-line error without losing the valid rows. Submit; assert both valid coupons are `Consumed` and each booklet's `consumed_count = 1`. Separately: submit an entry built with 3 Mode-A rows + 2 Mode-B rows and assert all 5 process identically.

### Implementation for User Story 2

- [x] T020 [US2] Add `resolve_coupons(coupon_numbers: list[str]) -> dict` to `cx_purisol/cx_purisol/api/consumption.py` — begin with `frappe.only_for("Purisol Administrator")`; filter blank/whitespace-only strings; raise translated `_("No coupon numbers to resolve.")` if filtered list is empty; one `frappe.get_all("Purisol Coupon", filters={"name": ["in", filtered]}, fields=["name", "booklet"])` plus one `frappe.get_all("Purisol Coupon Booklet", filters={"name": ["in", booklet_names]}, fields=["name", "customer"])`; return `{"resolved": [{"coupon": name, "booklet": b, "customer": c}, ...], "unresolved": [names not in the first result, in input order]}`; preserve input order in `resolved` (after blank-filtering) — per contracts §4
- [x] T021 [US2] Extend `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/purisol_coupon_consumption_entry.js` with the Mode B widget — a multi-line textarea input; Enter-on-single-line splits on `\n`, paste-many collects all new lines; on commit call `cx_purisol.cx_purisol.api.consumption.resolve_coupons` with the list; for each `resolved` entry call `frm.add_child("coupons", {coupon, booklet, customer})`; render one inline red-line error per `unresolved` number without clearing the valid rows; Enter-commit keystroke handler is plain keyboard input (forward-compatible with USB/Bluetooth barcode scanners per FR-022) — per research.md §8

### Tests for User Story 2

- [x] T022 [P] [US2] Extend `cx_purisol/cx_purisol/api/test_consumption.py` with `resolve_coupons` tests — (a) role gate raises for non-admin; (b) 3 valid numbers resolve with correct `booklet`/`customer` and preserved order; (c) mixed list of 2 valid + 1 unknown returns 2 in `resolved` and 1 in `unresolved`; (d) blank lines / whitespace-only strings are filtered out silently; (e) all-blank input raises the "No coupon numbers to resolve." translated error; (f) already-Consumed coupons still appear in `resolved` (filtering is the UI's/submit-time job, not the endpoint's) — per contracts §4.2 rationale
- [x] T023 [P] [US2] Extend `cx_purisol/cx_purisol/tests/test_consumption_flows.py` with Story 2 flows — (a) `test_mode_b_two_booklets_happy_path`: submit an entry built programmatically from two coupons from two different booklets, assert both `Consumed` and each booklet's `consumed_count = 1`; (b) `test_mode_a_plus_mode_b_mixed`: build an entry with 3 rows from Mode A seeding + 2 rows from Mode B seeding (programmatically mimicked), submit, assert all 5 transition identically (SC-007); (c) `test_resolve_coupons_partial`: call `resolve_coupons` with a list containing one unknown number, assert the good rows can still be appended and the unknown is surfaced per FR-021

**Checkpoint**: Stories 1 and 2 demoable. Both modes produce structurally identical child-table rows and submit behaves identically regardless of which mode created a row.

---

## Phase 5: User Story 3 — Auto-Deplete a Booklet on the 20th Consumed Coupon (Priority: P2)

**Goal**: When a Consumption Entry's submit drives a booklet's `consumed_count` to 20, the booklet transitions `Sold → Depleted` with `depleted_on` stamped, inside the same transaction. On cancel of the entry that triggered the depletion, the booklet reverts `Depleted → Sold` with `depleted_on` cleared — unless a later entry now holds the booklet at 20, in which case it stays `Depleted`.

**Independent Test**: (a) Seed a Sold booklet with 19 coupons already `Consumed` via a prior entry and 1 still `Available`. Submit a new entry containing the 20th coupon; assert booklet is now `Depleted` with `depleted_on ≈ entry.posting_datetime` and a `Comment` body matches `Depleted via <entry.name>`. (b) Cancel that entry; assert booklet reverts to `Sold` with `depleted_on = None` and a reciprocal Comment. (c) Seed a Sold booklet with all 20 Available; submit one entry listing all 20; assert exactly one `Sold → Depleted` transition in the change log. (d) Seed a depletion, submit a second depleting entry over the same booklet (conceptual only — in practice would require amend), then cancel the first entry: assert the booklet remains `Depleted`.

### Implementation for User Story 3

- [x] T024 [US3] Extend `on_submit` in `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/purisol_coupon_consumption_entry.py` — inside the per-booklet recompute loop from T012, add: `if consumed_count == 20 and booklet.status == "Sold": booklet.status = "Depleted"; booklet.depleted_on = self.posting_datetime`; save via `booklet.save(ignore_permissions=True)` so the widened booklet `validate` runs the `(Sold, Depleted)` transition check; then `frappe.get_doc("Purisol Coupon Booklet", booklet.name).add_comment("Info", _("Depleted via {0}").format(self.name))` — all inside the submit transaction — per data-model §6.3 and research.md §6
- [x] T025 [US3] Extend `on_cancel` in the same parent controller — after the per-booklet aggregate recompute from T013, for each booklet currently `Depleted`: run the "trigger-of-record" query (`frappe.db.sql` per data-model §6.4 — find the most-recent `docstatus=1` Consumption Entry referencing that booklet, excluding `self`); if no other entry exists → self is the trigger; if self is the trigger AND `consumed_count < 20` after recompute: set `status = "Sold"`, clear `depleted_on`, save via `booklet.save(ignore_permissions=True)`, add a reciprocal Comment `_("Depletion reverted — entry {0} cancelled.").format(self.name)`; otherwise leave the booklet as-is — per data-model §6.4 and research.md §6

### Tests for User Story 3

- [x] T026 [P] [US3] Extend `cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/test_purisol_coupon_booklet.py` with Phase-4 transition tests — assert (a) `Sold → Depleted` permitted via controller widening; (b) `Depleted → Sold` permitted; (c) `Depleted → In Stock` still rejected with the "not allowed" message (terminal-state safeguard); (d) `Depleted → In Custody` still rejected; (e) `In Stock → Depleted` and `In Custody → Depleted` still rejected (depletion can only be reached via `Sold`)
- [x] T027 [P] [US3] Extend `cx_purisol/cx_purisol/tests/test_consumption_flows.py` with Story 3 flows — (a) `test_auto_deplete_19_plus_1`: seed booklet with 19 Consumed coupons, submit entry for the 20th; assert booklet is `Depleted`, `depleted_on` is populated, and a Comment `"Depleted via <entry.name>"` exists on the booklet; (b) `test_auto_deplete_all_20_in_single_entry`: seed booklet with all 20 Available, submit one entry listing all 20; assert exactly one `Sold → Depleted` transition in `tabVersion`; (c) `test_multi_booklet_one_depletes_one_partial`: entry touches two booklets, one finishes at 20, one at 5; assert only the finished one is `Depleted`, the other remains `Sold`; (d) `test_cancel_reverts_depletion`: submit the 19+1 scenario, cancel, assert booklet reverts to `Sold` with `depleted_on = None` and the reciprocal Comment; (e) `test_cancel_keeps_depletion_when_later_entry_holds_20`: seed booklet to `Depleted` via entry A, then simulate a later-submitted entry B (by directly inserting matching `Consumed` coupons referencing a new submittable entry, or by submitting entry B that replaces A's coupons — document the simulation in the test), cancel A; assert booklet stays `Depleted`

**Checkpoint**: Stories 1–3 demoable. Auto-depletion and its symmetrical cancel-revert are live and well-covered.

---

## Phase 6: User Story 4 — Reject Invalid Submissions All-or-Nothing (Priority: P3)

**Goal**: Before any coupon is touched, the submit rejects the entire entry if any row's coupon doesn't exist (FR-031) or is already `Consumed` (FR-033); empty-table (FR-030) and duplicate-in-entry (FR-032) already reject at validate from Phase 2. All rejections are atomic — the Administrator sees the draft intact with no coupon or booklet touched.

**Independent Test**: (a) Build a 10-coupon entry with 1 row referencing `CP-99999` (non-existent); submit, assert `frappe.ValidationError` naming `CP-99999`, and assert every other coupon and booklet is bit-for-bit unchanged. (b) Seed one coupon `CP-00001` already `Consumed` by a prior entry; submit a new entry listing `CP-00001`; assert rejection names the coupon and references the prior entry. (c) Build an entry with a duplicate coupon; assert rejection at validate. (d) Submit an empty entry; assert rejection at validate. (e) Build an entry listing a coupon from an `In Stock` booklet (non-Sold); assert submit succeeds (Phase 5 defers the warning). (f) Two simultaneous submits referencing the same coupon: exactly one succeeds, the other rejects with the already-consumed error (or `TimestampMismatchError`), and there is no partial state.

### Implementation for User Story 4

- [x] T028 [US4] Implement `before_submit` in `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/purisol_coupon_consumption_entry.py` — collect `coupon_names = [row.coupon for row in self.coupons]`, bulk-read via `frappe.get_all("Purisol Coupon", filters={"name": ["in", coupon_names]}, fields=["name", "status", "consumption_entry"])`, build a dict keyed by `name`; iterate `coupon_names` and accumulate errors: `_("Coupon {0} does not exist.").format(n)` for names missing from the result (FR-031), `_("Coupon {0} is already Consumed (recorded on entry {1}).").format(n, prior)` for rows whose current `status == "Consumed"` (FR-033); if the errors list is non-empty, `frappe.throw("<br>".join(errors))` — all translated, inside the submit transaction — per research.md §2 and contracts §1.4

### Tests for User Story 4

- [x] T029 [P] [US4] Extend `cx_purisol/cx_purisol/tests/test_consumption_flows.py` with Story 4 flows — (a) `test_reject_unknown_coupon_atomically`: submit entry with 10 valid + 1 unknown row, assert rejection names the unknown coupon and every one of the 10 valid coupons is still `Available` with unchanged `modified` (SC-005); (b) `test_reject_already_consumed_with_prior_entry_diagnostic`: submit a second entry referencing a coupon consumed by a first entry, assert error message names the coupon and includes the prior entry's name; (c) `test_reject_empty_entry_at_validate_and_submit`: both insert-with-empty-then-submit and reload-draft-then-submit paths raise FR-030; (d) `test_reject_duplicate_in_entry`: entry lists the same coupon twice (Mode A + Mode B simulated), assert validate rejects naming the duplicate; (e) `test_coupon_from_non_sold_booklet_does_not_block` (edge / future-proofing): seed a coupon whose booklet is `In Stock`, submit entry including it, assert submit succeeds and no discrepancy record is created (FR-035, Phase-5 deferral); (f) `test_concurrent_submit_race`: two Consumption Entries referencing the same coupon submitted via `threading.Thread` or `frappe.enqueue` simulation, assert exactly one succeeds and the other raises either `frappe.ValidationError` matching "already Consumed" or `frappe.TimestampMismatchError`, and final-state invariants hold (coupon is `Consumed` exactly once, one entry `docstatus = 1`, the other `docstatus = 0`) — per FR-061 / SC-009

**Checkpoint**: All four user stories demoable. The submit path is safe, atomic, and all blocking paths are covered.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T030 [P] Add a unit test in `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/test_purisol_coupon_consumption_entry.py` that asserts non-`Purisol Administrator` users cannot create, write, submit, cancel, or amend the Consumption Entry (FR-070), and that `received_by` is not user-editable after insert (FR-071)
- [x] T031 [P] Extract newly-translatable strings with `bench --site <site> get-untranslated ar` and land the Phase-4 Arabic translations in `cx_purisol/translations/ar.csv` — labels on the new DocTypes, mode-switcher UI, every validation message, and both Comment bodies
- [ ] T032 [P] Apply and smoke-test the Phase-4 migration: run `bench --site <site> migrate` on a fresh install (assert the three new DocTypes land, the anchor patch logs its one-line message) and on an upgraded site (assert idempotence)
- [ ] T033 Full-suite run `bench --site <site> run-tests --app cx_purisol` must pass on a clean test database — the phase's definition-of-done gate (constitution Principle X)
- [ ] T034 [P] Execute the manual UI walkthrough from `specs/004-consumption-recording/quickstart.md` §7 on a bench site — confirm Mode A autocomplete + checklist + Add to Entry, Mode B paste-with-bad-line, submit, booklet auto-deplete, and cancel round-trip all behave as the spec prescribes

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1. **BLOCKS all user stories.** T008 depends on T007 (JSON must exist before controller skeleton references its fields). T011 depends on Phase-1/2/3 fixtures already present on the branch.
- **User Story 1 (Phase 3)**: Depends on Phase 2. T012 and T013 both modify the parent controller, so T012 must land before T013 (or they can be implemented in one sitting then split at commit time). T014 and T015 [P] with T012/T013 only after the controller skeleton landed in T008.
- **User Story 2 (Phase 4)**: Depends on Phase 2 (controller skeleton + shared form JS file) and Phase 3 only for the JS file being created in T015. If US1 and US2 are worked in parallel by different developers, T015 must land first so T021 can extend it; T020 (`api/consumption.py`) depends on the `consumption.py` file created in T014.
- **User Story 3 (Phase 5)**: Depends on Phase 3 — T024 and T025 modify the same `on_submit` / `on_cancel` methods T012/T013 introduced. Also depends on T010 (booklet controller widening) so the `(Sold, Depleted)` transitions are allowed by `booklet.save(ignore_permissions=True)`.
- **User Story 4 (Phase 6)**: Depends on Phase 3 — T028 lives alongside T012/T013 in the parent controller and exercises the same submit transaction. Integration tests (T029) need US1–US3 plumbing to produce the full rejection-path coverage.
- **Polish (Phase 7)**: Depends on all user stories being implemented.

### User Story Dependencies

- **US1 (P1)**: Independent after Phase 2 — foundational MVP.
- **US2 (P2)**: Depends on US1 only for the shared form JS file (T015 creates it, T021 extends it). Server-side `resolve_coupons` (T020) is independent of US1 once `api/consumption.py` exists.
- **US3 (P2)**: Depends on US1's `on_submit` / `on_cancel` methods existing (T024/T025 extend them). Independent of US2.
- **US4 (P3)**: Depends on US1's `on_submit` existing (T028 is a new lifecycle hook running before it). Independent of US2 and US3.

### Within Each User Story

- DocType JSONs before controllers that reference them.
- Server-side implementation before tests that exercise the contract.
- Unit tests and integration tests for the same story can be written in parallel once the implementation has landed (or, if TDD is preferred, write tests first and expect them to FAIL before the impl task lands).

### Parallel Opportunities

- **Phase 1**: T001 and T002 are independent.
- **Phase 2**: T003/T004/T005/T006/T007 are all [P] (different files). T009/T010/T011 are [P] with each other and with T003–T007. T008 is NOT [P] — it depends on T007 (parent JSON).
- **Phase 3**: T016/T017/T018/T019 tests are all [P] once the implementation tasks (T012–T015) have landed. T012 and T013 are in the same file (not [P]). T014 and T015 are [P] with each other.
- **Phase 4**: T022 [P] with T023.
- **Phase 5**: T024 and T025 are same-file (not [P]). T026 and T027 tests are [P].
- **Phase 6**: T029 is the only test task and is [P] with the tests from other stories if worked concurrently.
- **Phase 7**: T030/T031/T032/T034 are [P]; T033 must run last (it's the gate).

---

## Parallel Example: User Story 1 Implementation + Tests

```bash
# After T008 (parent controller skeleton) lands:

# Developer A — implementation (serial within one file):
Task T012: Implement on_submit per-coupon + per-booklet recompute
Task T013: Implement on_cancel per-coupon + per-booklet recompute

# Developer B — in parallel with A:
Task T014: Implement list_available_coupons in api/consumption.py
Task T015: Create form client script with mode switcher + Mode A widget

# Once T012–T015 merged, tests can all run in parallel:
Task T016 [P]: Unit tests for validate rules in test_purisol_coupon_consumption_entry.py
Task T017 [P]: Coupon-transition tests in test_purisol_coupon.py
Task T018 [P]: API tests for list_available_coupons in api/test_consumption.py
Task T019 [P]: Integration tests for Mode A happy paths in tests/test_consumption_flows.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational — the blocking prerequisite.
3. Complete Phase 3: User Story 1 (Mode A + core submit/cancel, minus auto-deplete).
4. **STOP and VALIDATE** — the MVP: Administrator can record consumption by picking coupons from a booklet, submit, and cancel. Demoable.
5. Deploy/demo if ready.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. Add User Story 1 (Mode A + core submit/cancel) → MVP demoable.
3. Add User Story 2 (Mode B entry) → Fast-path and barcode-scanner-ready flows demoable.
4. Add User Story 3 (Auto-deplete on 20th) → Full lifecycle loop demoable, including the Phase-6 notification seam.
5. Add User Story 4 (Blocking validations + atomicity) → Hardened submit path; SC-005 / SC-008 / SC-009 covered.
6. Polish phase runs all four stories' tests clean-green (T033).

### Parallel Team Strategy

With 2–3 developers after Phase 2 lands:

- Developer A: US1 (Phase 3) — the critical-path MVP.
- Developer B: US2 (Phase 4) — extends the form JS and the API module US1 already created.
- Developer C: US3 (Phase 5) — waits for US1's `on_submit`/`on_cancel` to land, then layers auto-deplete.
- US4 lands last — it has the smallest surface but covers every other story's rejection paths; assign to whoever finishes first.

---

## Notes

- Every user-facing string wrapped in `frappe._()` (constitution IX). Translation strings land in `cx_purisol/translations/ar.csv` in T031.
- Every state-changing write goes through a DocType save (either `frappe.db.set_value(..., update_modified=True)` on reserved fields or `doc.save(ignore_permissions=True)` on booklets) — no raw SQL writes (constitution II / plan.md).
- All submit / cancel logic runs inside the single Frappe request transaction. No `frappe.enqueue`, no explicit `frappe.db.commit()` (research.md §3).
- Tests use `FrappeTestCase` with the extended `make_sold_booklet_ready_for_consumption` helper; clean-database `bench run-tests --app cx_purisol` is the phase's definition of "done" (T033).
- Phase 4 emits **zero** discrepancy records and **zero** notifications (FR-035, FR-044, SC-011). The `discrepancies_detected` table exists as a reserved-empty Phase-5 seam, and the `has_warnings` flag stays `0`. Defensive guards in T008's `validate` enforce this even under future accidental edits.
