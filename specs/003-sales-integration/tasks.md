# Tasks: Sales Integration

**Input**: Design documents from `/specs/003-sales-integration/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/sales-integration.md`, `quickstart.md`

**Tests**: Included — constitution X (Testing Discipline) mandates `FrappeTestCase`-based unit and integration tests for every user story and every edge case, and `plan.md` enumerates specific test modules to create.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- All paths are relative to the repo root `/home/corex/aurevia-bench/apps/cx_purisol/`

## Path Conventions

- App package root: `cx_purisol/` (contains `hooks.py`, `patches.txt`, `public/`, `patches/`)
- Module folder: `cx_purisol/cx_purisol/` (contains `doctype/`, `api/`, `sales_invoice/`, `fixtures/`, `tests/`, `report/`)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new package subdirectories and empty module markers introduced by Phase 3. No runtime logic yet.

- [X] T001 [P] Create `cx_purisol/cx_purisol/sales_invoice/` directory with an empty `cx_purisol/cx_purisol/sales_invoice/__init__.py` (the new sub-package that will host `Sales Invoice` `doc_events`).
- [X] T002 [P] Create `cx_purisol/patches/v0_3_0/` directory with an empty `cx_purisol/patches/v0_3_0/__init__.py` (houses the Phase-3 data-patch module).
- [X] T003 [P] Ensure `cx_purisol/public/js/` exists (from Phase 1) — no-op if already present; if missing, create `cx_purisol/public/js/.gitkeep`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Every Phase-3 user story depends on (a) the custom field that links invoice lines to booklets, (b) the widened booklet state machine that permits `*-> Sold` transitions, (c) the `hooks.py` wiring that makes Frappe actually call our `doc_events`, and (d) the test-fixture seeds that every integration test needs. Nothing in Phases 3+ can even load correctly without these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Author the `Custom Field` fixture for the booklet link on `Sales Invoice Item` in `cx_purisol/cx_purisol/fixtures/custom_field.json`. Contents: a single-entry array with `"doctype": "Custom Field"`, `"name": "Sales Invoice Item-purisol_booklet"`, `"dt": "Sales Invoice Item"`, `"fieldname": "purisol_booklet"`, `"label": "Purisol Booklet"`, `"fieldtype": "Link"`, `"options": "Purisol Coupon Booklet"`, `"insert_after": "item_code"`, `"in_list_view": 1`, `"read_only_depends_on": "eval:doc.parent && doc.docstatus==1"`, `"no_copy": 1`, `"allow_on_submit": 0`, `"translatable": 0`. Matches data-model.md §1.
- [X] T005 Register fixtures, `doc_events`, and the list-view JS in `cx_purisol/hooks.py`. Add/extend: `fixtures = [..., {"dt": "Custom Field", "filters": [["name", "in", ["Sales Invoice Item-purisol_booklet"]]]}]`; `doc_events = {"Sales Invoice": {"validate": "cx_purisol.sales_invoice.sales_invoice_hooks.validate_booklet_lines", "on_submit": "cx_purisol.sales_invoice.sales_invoice_hooks.mark_booklets_sold", "on_cancel": "cx_purisol.sales_invoice.sales_invoice_hooks.reverse_booklets_sale", "on_trash": "cx_purisol.sales_invoice.sales_invoice_hooks.guard_trash"}}`; `doctype_list_js = {"Purisol Coupon Booklet": "public/js/purisol_coupon_booklet_list.js"}`. Preserve existing Phase-1/Phase-2 entries.
- [X] T006 Widen the booklet controller state machine in `cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/purisol_coupon_booklet.py`. Extend `_ALLOWED_STATUSES` to `{"In Stock", "In Custody", "Sold"}` and add to `_ALLOWED_TRANSITIONS` the three pairs `("In Stock", "Sold")`, `("In Custody", "Sold")`, `("Sold", "In Stock")`. Keep `Depleted` out of `_ALLOWED_STATUSES` (Phase 4). Keep the existing read-only protection on `status`, `customer`, `sold_on`, `sales_invoice`, `current_delivery_man` — no change to the UI-edit guard. Matches data-model.md §3.3.
- [X] T007 Create the Phase-3 data-patch stub in `cx_purisol/patches/v0_3_0/widen_booklet_validate_for_sale.py`. Contents: a single `def execute(): pass` with a docstring explaining that the patch is a no-op anchor for sites migrated through Phase 3 (matches plan.md's patches note + Phase-2 convention).
- [X] T008 Append one entry to `cx_purisol/patches.txt`: `cx_purisol.patches.v0_3_0.widen_booklet_validate_for_sale`. Place it under the post-`model-sync` section (after any existing Phase-2 entries), preserving prior entries.
- [X] T009 Create the `Sales Invoice` hook module skeleton in `cx_purisol/cx_purisol/sales_invoice/sales_invoice_hooks.py`. Define four module-level functions (`validate_booklet_lines(doc, method=None)`, `mark_booklets_sold(doc, method=None)`, `reverse_booklets_sale(doc, method=None)`, `guard_trash(doc, method=None)`), each short-circuiting immediately when `not any(getattr(it, "purisol_booklet", None) for it in doc.items)`. Bodies are empty (`pass`) at this phase — actual logic lands in later phases. This makes the `doc_events` in T005 resolvable so `bench migrate` does not crash.
- [X] T010 Extend the shared test fixtures module `cx_purisol/cx_purisol/tests/fixtures.py` with helpers used across all Phase-3 tests: `ensure_coupon_item()` (non-stock Item with `stock_uom="Booklet"`, `is_sales_item=1`, linked to a default Income Account via the test Company), `ensure_price_list(name, currency="INR", is_selling=1)`, `ensure_item_price(item_code, price_list, rate)`, `ensure_customer(name, default_price_list=None)`, `configure_purisol_settings(coupon_item=None, default_price_list=None)`. Each helper is idempotent (`get_or_create` style). Preserve the Phase-2 helpers already in the file.

**Checkpoint**: Foundation ready — `bench migrate` runs clean, the Custom Field appears on `Sales Invoice Item`, the booklet controller accepts the new transitions when invoked through `db_set`, the `doc_events` are resolvable but inert, and integration tests have the seed helpers they need.

---

## Phase 3: User Story 1 — Sell a Single Booklet to a Customer (Priority: P1) 🎯 MVP

**Goal**: An Administrator can launch the Sell Booklets workflow from the booklet list view, pick a customer, pick one `In Stock` or `In Custody` booklet, review the draft invoice, submit it, and see the booklet flip to `Sold` with `customer`, `sold_on`, `sales_invoice` populated and `current_delivery_man` cleared — on exactly one Sales Invoice.

**Independent Test**: Seed one Customer, one Employee, one `In Stock` booklet, a configured `coupon_item` Item and a Price List with a non-zero rate, and `Purisol Settings.default_price_list`. Call `purisol_create_sales_invoice_for_booklets(customer, [booklet], None)` → draft returned. Submit the returned invoice → booklet status is `Sold`, `customer`, `sold_on = posting_datetime`, `sales_invoice = invoice.name`, `current_delivery_man` is empty. Repeat with an `In Custody` booklet → same result, custody cleared.

### Tests for User Story 1 ⚠️

> **Write these tests FIRST, ensure they FAIL (or error with `ImportError`/`AttributeError`) before implementation lands.**

- [X] T011 [P] [US1] Unit tests for widened booklet transitions in `cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/test_purisol_coupon_booklet.py`. Add cases: `test_in_stock_to_sold_via_db_set_allowed`, `test_in_custody_to_sold_via_db_set_allowed`, `test_sold_to_in_stock_via_db_set_allowed`, `test_sold_to_in_custody_rejected`, `test_sold_to_sold_rejected`, `test_depleted_still_unreachable`. Keep the Phase-2 tests intact.
- [X] T012 [P] [US1] Unit tests for the workflow API and price-list helper in `cx_purisol/cx_purisol/api/test_sell_booklets.py`. Cases: `test_resolve_price_list_prefers_explicit`, `test_resolve_price_list_falls_back_to_customer_default`, `test_resolve_price_list_falls_back_to_settings_default`, `test_resolve_price_list_raises_when_nothing_configured`, `test_api_rejects_non_administrator` (uses `frappe.set_user`), `test_api_rejects_when_coupon_item_unset`, `test_api_rejects_empty_booklets_list`, `test_api_rejects_duplicate_booklet_input`, `test_api_rejects_booklet_in_wrong_status`, `test_api_creates_draft_invoice_with_one_line_per_booklet`.
- [X] T013 [P] [US1] Integration tests for the single-booklet sale flow in `cx_purisol/cx_purisol/tests/test_sales_flows.py` (NEW file, `FrappeTestCase` subclass). Cases for US1: `test_submit_single_in_stock_booklet_transitions_to_sold`, `test_submit_single_in_custody_booklet_clears_current_delivery_man`, `test_draft_invoice_does_not_change_booklet_status`, `test_sold_booklet_cannot_be_added_to_new_invoice`, `test_settings_default_price_list_drives_rate_when_no_other_choice`. `setUp` uses the helpers from T010.

### Implementation for User Story 1

- [X] T014 [P] [US1] Implement `_resolve_price_list(customer, explicit)` in `cx_purisol/cx_purisol/api/sell_booklets.py` (new file). Signature and body exactly as research.md §3 — three-tier fallback, `frappe.throw` when nothing resolves. Pure helper, no side effects.
- [X] T015 [US1] Implement the whitelisted entry point `purisol_create_sales_invoice_for_booklets(customer, booklets, price_list=None)` in the same file `cx_purisol/cx_purisol/api/sell_booklets.py`. Order of operations: `frappe.only_for("Purisol Administrator")` → read `Purisol Settings.coupon_item`, throw if unset (P2) → parse `booklets` (accept list or JSON string from JS) → throw on empty (P4) or duplicates (P5) → per-booklet existence + status check `∈ {In Stock, In Custody}` (P6) → call `_resolve_price_list` (P7) → build `Sales Invoice` via `frappe.new_doc("Sales Invoice")`, set `customer`, `selling_price_list = resolved`, append one line per booklet with `item_code = coupon_item`, `qty = 1`, `purisol_booklet = <name>` → call `doc.set_missing_values()` and `doc.calculate_taxes_and_totals()` → `doc.insert(ignore_permissions=False)` → return `{"name": doc.name}`. Add a companion helper `@frappe.whitelist() def get_coupon_item_code()` returning `Purisol Settings.coupon_item` for the client script.
- [X] T016 [US1] Implement `validate_booklet_lines(doc, method=None)` in `cx_purisol/cx_purisol/sales_invoice/sales_invoice_hooks.py` (replacing the T009 stub). Short-circuit if no line has `purisol_booklet`. Read `Purisol Settings.coupon_item` once. For each booklet-bearing line, enforce V1 (booklet exists) via `frappe.db.exists`, V2 (`item_code == coupon_item`), V3 (booklet status ∈ `{In Stock, In Custody}` via `frappe.db.get_value`), V4 (no duplicate booklet across lines — accumulate booklet names in a set and throw on re-seen), V5 (`line.qty == 1`). Error messages exactly as contracts/sales-integration.md §2.3, wrapped in `frappe._()` with named placeholders.
- [X] T017 [US1] Implement `mark_booklets_sold(doc, method=None)` in `cx_purisol/cx_purisol/sales_invoice/sales_invoice_hooks.py`. Short-circuit if no line has `purisol_booklet`. Compute `sold_datetime = frappe.utils.get_datetime(f"{doc.posting_date} {doc.posting_time or '00:00:00'}")`. For each booklet-bearing line, load the booklet via `frappe.get_doc("Purisol Coupon Booklet", line.purisol_booklet)` (for optimistic-lock / `TimestampMismatchError` semantics, research.md §9), then call `booklet.db_set({"status": "Sold", "customer": doc.customer, "sold_on": sold_datetime, "sales_invoice": doc.name, "current_delivery_man": None}, update_modified=True, notify=True)`. Then `booklet.add_comment("Info", frappe._("Sold via {0}").format(doc.name))`. No coupon writes.
- [X] T018 [P] [US1] Implement the list-view action in `cx_purisol/public/js/purisol_coupon_booklet_list.js` (new file). Export `frappe.listview_settings["Purisol Coupon Booklet"]` with an `onload(listview)` that: (a) returns early unless `frappe.user.has_role("Purisol Administrator")`, (b) adds a bulk-action button labelled `__("Sell Selected to Customer")` whose handler collects the selected rows' `name` values, checks that every selected row has `status ∈ {"In Stock", "In Custody"}` (else `frappe.msgprint` and abort), then opens `frappe.prompt` with two fields: Customer (Link, `reqd`) and Price List (Link, optional) plus a read-only `HTML` field rendering the selected booklet list. On submit, calls `frappe.call("cx_purisol.api.sell_booklets.purisol_create_sales_invoice_for_booklets", {customer, booklets: selected_names, price_list})`, and on `r.message.name` routes via `frappe.set_route("Form", "Sales Invoice", r.message.name)`. On error, leave dialog open (Frappe's default error surface handles display).

**Checkpoint**: US1 is fully functional. Running the T013 integration test suite alone is green. Manually following quickstart.md §3 works end-to-end in the desk. MVP can be demoed.

---

## Phase 4: User Story 2 — Sell Multiple Booklets to a Customer in One Invoice (Priority: P2)

**Goal**: An Administrator multi-selects several booklets (mix of `In Stock` and `In Custody`, up to 10) and sells them on one Sales Invoice with one line per booklet, sharing the same `sold_on` and `sales_invoice` across every transitioned booklet.

**Independent Test**: Seed three booklets (two `In Stock`, one `In Custody` held by an Employee). Call `purisol_create_sales_invoice_for_booklets(customer, [all three], None)` → draft with three lines returned. Submit → all three booklets are `Sold` with identical `sales_invoice` and `sold_on`, the `In Custody` one has its `current_delivery_man` cleared, and any custody-entry history prior to the sale remains intact and queryable.

### Tests for User Story 2 ⚠️

- [X] T019 [P] [US2] Integration tests for multi-booklet flows appended to `cx_purisol/cx_purisol/tests/test_sales_flows.py`. Cases: `test_multi_booklet_submit_mixed_sources_all_transition_to_sold` (two In Stock + one In Custody → all `Sold`, same `sold_on` and `sales_invoice`, in-custody one has `current_delivery_man` cleared), `test_duplicate_booklet_on_invoice_rejected_at_submit` (V4 surfaces when the same `purisol_booklet` appears on two lines — assert invoice remains draft, booklets unchanged), `test_stale_draft_with_booklet_sold_elsewhere_rejected` (draft A references booklet X; submit draft B first for X; submit draft A → `ValidationError` mentioning X, draft A's booklets all unchanged), `test_changing_price_list_on_draft_updates_all_lines` (create draft with default PL, reassign `selling_price_list` to Wholesale, save, submit → all lines re-rated), `test_all_or_nothing_no_partial_updates` (injects one wrong-status booklet among four; assert zero booklets transitioned after the throw).

### Implementation for User Story 2

- [X] T020 [US2] Verify the T015 implementation actually accepts and processes a list of >1 booklets unchanged; no code change expected. If the T019 tests surface any single-vs-multi assumption (e.g., `booklets[0]` indexing), fix `cx_purisol/cx_purisol/api/sell_booklets.py` and/or `cx_purisol/cx_purisol/sales_invoice/sales_invoice_hooks.py` to iterate cleanly. Expected outcome: no diff is needed beyond what T015–T017 already produce.

**Checkpoint**: US1 AND US2 both pass their own integration suites. Quickstart §4 walkthrough runs cleanly. The spec's acceptance scenarios 1–4 for US2 are all green.

---

## Phase 5: User Story 3 — Cancel a Sales Invoice and Reverse the Sale Where Safe (Priority: P3)

**Goal**: Cancelling a submitted `Sales Invoice` reverses every referenced booklet to `In Stock` (clearing `customer`, `sold_on`, `sales_invoice`) **only when** no coupon on any referenced booklet has `status = "Consumed"`. If any booklet has any consumed coupon, the cancel is rejected with a clear, fully-named error and no booklet is touched — all-or-nothing across the invoice.

**Independent Test**: Sell one booklet (US1 path). Cancel the invoice → booklet back to `In Stock` with cleared fields; `current_delivery_man` remains empty (spec FR-032). Sell another booklet; directly set one of its coupons to `status = "Consumed"` via `frappe.db.set_value`; cancel → rejected with error naming the booklet; booklet still `Sold`.

### Tests for User Story 3 ⚠️

- [X] T021 [P] [US3] Unit test for the `Sold → In Stock` transition path appended to `cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/test_purisol_coupon_booklet.py`. Case: `test_sold_to_in_stock_on_cancel_allowed_via_db_set` (already partially covered by T011 — this adds the fields-cleared assertion: after `db_set` to `status=In Stock`, confirm `customer`, `sold_on`, `sales_invoice` can be written to `None` through the same hook path without re-raising from the validate guard).
- [X] T022 [P] [US3] Integration tests for cancel flows appended to `cx_purisol/cx_purisol/tests/test_sales_flows.py`. Cases: `test_cancel_safe_reverses_booklet_to_in_stock` (single booklet, no consumption → back to `In Stock`, fields cleared, `current_delivery_man` still empty, Comment `"Sale reversed — ..."` present), `test_cancel_blocked_by_consumption_on_single_booklet` (mark one coupon `Consumed` via `frappe.db.set_value`, cancel → raises, booklet unchanged), `test_cancel_multi_booklet_all_or_nothing_when_one_has_consumption` (three booklets sold in one invoice, consume one coupon on the third booklet, cancel → rejected, none of the three modified, error names the consumed booklet), `test_cancel_of_draft_has_no_side_effects` (create draft, delete it without submit → no booklet ever transitioned), `test_trash_refused_while_booklets_reference_invoice` (guard_trash T1 path; requires stubbing a state where the invoice is in a deletable form but a booklet still references it — use `frappe.db.set_value` to force `docstatus` for the test).

### Implementation for User Story 3

- [X] T023 [US3] Implement `reverse_booklets_sale(doc, method=None)` in `cx_purisol/cx_purisol/sales_invoice/sales_invoice_hooks.py` (replacing the T009 stub). Short-circuit if no line has `purisol_booklet`. Collect booklet names from booklet-bearing lines. For each, run `frappe.db.count("Purisol Coupon", {"booklet": b, "status": "Consumed"})`; accumulate names whose count > 0. If the accumulator is non-empty, `frappe.throw(_("Cannot cancel — coupons have been consumed on: {0}. The only correction path is a financial adjustment (outside Phase 3 scope).").format(", ".join(names)))`. Otherwise, for each booklet: load via `frappe.get_doc`, `db_set({"status": "In Stock", "customer": None, "sold_on": None, "sales_invoice": None}, update_modified=True, notify=True)` (do **not** clear `current_delivery_man` — it's already empty and FR-032 forbids restoring prior custody), and `add_comment("Info", _("Sale reversed — invoice {0} cancelled.").format(doc.name))`.
- [X] T024 [US3] Implement `guard_trash(doc, method=None)` in `cx_purisol/cx_purisol/sales_invoice/sales_invoice_hooks.py` (replacing the T009 stub). Query `frappe.get_all("Purisol Coupon Booklet", filters={"sales_invoice": doc.name}, pluck="name")`; if non-empty, `frappe.throw(_("Cannot delete — booklets still reference this invoice. Cancel the invoice first."))`. Otherwise return silently.

**Checkpoint**: US1, US2, and US3 all pass. Quickstart §5.1 and §5.2 walkthroughs both behave as documented (safe reversal + consumption-blocked rejection).

---

## Phase 6: User Story 4 — Choose a Price List Per Sale (Priority: P3)

**Goal**: The workflow lets the Administrator override the resolved Price List on a per-sale basis. Resolution order is explicit and verified: (1) explicit workflow choice, (2) customer's `default_price_list`, (3) `Purisol Settings.default_price_list`. The chosen Price List drives the rate on every booklet line of the resulting invoice; a misconfigured Price List (no `Item Price` for `coupon_item`) surfaces a clear ERPNext error.

**Independent Test**: Seed two Price Lists ("Retail" @ 120, "Wholesale" @ 80); set Settings default to "Retail". Seed a customer whose `default_price_list` is "Wholesale". Call the workflow with (a) `price_list=None` → line rate 80 (customer default wins over Settings), (b) `price_list="Retail"` → line rate 120 (explicit wins over customer default), (c) clear the customer's `default_price_list` and call with `price_list=None` → line rate 120 (Settings fallback). Finally seed a Price List "Empty" with no `Item Price` for the coupon item and call with `price_list="Empty"` → ERPNext raises a rate-not-found error naming "Empty".

### Tests for User Story 4 ⚠️

- [X] T025 [P] [US4] Integration tests for Price List resolution appended to `cx_purisol/cx_purisol/tests/test_sales_flows.py`. Cases: `test_price_list_explicit_workflow_choice_wins`, `test_price_list_customer_default_used_when_no_explicit`, `test_price_list_settings_default_used_when_no_customer_default_and_no_explicit`, `test_price_list_misconfigured_surfaces_rate_lookup_error` (use a Price List with no `Item Price` for the coupon item; assert the error message contains the Price List's name so the Administrator can find it), `test_no_price_list_resolvable_raises_configure_error` (clear all three sources; assert P7 error is raised with the contract-specified message).

### Implementation for User Story 4

- [X] T026 [US4] Confirm the dialog in `cx_purisol/public/js/purisol_coupon_booklet_list.js` (from T018) exposes the optional `Price List` field with the placeholder `__("Leave blank to use Customer default or Settings default.")` and wires it through to the `frappe.call`. If T018 already implemented this exactly, no diff. Otherwise, adjust only the dialog definition.
- [X] T027 [US4] No server-side code changes expected — `_resolve_price_list` (T014) and the `price_list=None` default in the API signature (T015) already implement the three-tier resolution. If T025 tests reveal a defect, fix it in `cx_purisol/cx_purisol/api/sell_booklets.py` (single locus).

**Checkpoint**: All four user stories are independently functional and covered by tests. Quickstart §6 cases A–D all pass.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Localisation, audit-trail cross-checks, quickstart validation, and any cleanup. No new behaviour.

- [X] T028 [P] Add Arabic translations for every Phase-3 user-facing string to `cx_purisol/translations/ar.csv` (create the file if it doesn't exist from Phase 1/2). Entries must cover: dialog title and field labels (`"Sell Selected to Customer"`, `"Customer"`, `"Price List"`, `"Leave blank to use..."`), every `frappe.throw` message in `sell_booklets.py`, `sales_invoice_hooks.py`, and the booklet controller's widened guard. Use named placeholders `{0}`, `{1}` unchanged so word order works correctly (constitution IX).
- [X] T029 Run the quickstart walkthrough from `specs/003-sales-integration/quickstart.md` §§1–6 end-to-end on a dev bench site, verifying every expected value in §8 checklist. Fix any mismatch between the quickstart and the implementation — the quickstart is the user-facing contract.
- [X] T030 [P] Run the full Phase-3 test suite: `bench --site <site> run-tests --app cx_purisol --module cx_purisol.cx_purisol.tests.test_sales_flows` and `--module cx_purisol.cx_purisol.doctype.purisol_coupon_booklet.test_purisol_coupon_booklet` and `--module cx_purisol.cx_purisol.api.test_sell_booklets`. All tests green; no warnings about deprecated Frappe APIs.
- [X] T031 [P] `ruff check cx_purisol/` (fix any import ordering, unused imports, line length in the new files) and a Frappe-style JS lint pass on `cx_purisol/public/js/purisol_coupon_booklet_list.js` (standard eslint-frappe config if configured, otherwise manual pass for no console.logs and `const`/`let` usage).
- [X] T032 Cross-story audit-trail check: pick one booklet that has been (a) sold, then (b) safe-cancelled, then (c) sold again in a fresh invoice — confirm the booklet's timeline in the desk shows three distinct `Comment` entries in the right order (`Sold via INV-A`, `Sale reversed — invoice INV-A cancelled.`, `Sold via INV-B`), and three matching `Version` entries. Matches SC-010.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. **BLOCKS all user stories.** T004–T010 can partially parallelize as noted below.
- **User Story 1 (Phase 3)**: Depends on Foundational. MVP increment.
- **User Story 2 (Phase 4)**: Depends on Foundational + US1 (reuses US1's API and hooks; adds no new server code, only tests and a verification task).
- **User Story 3 (Phase 5)**: Depends on Foundational only — does **not** depend on US2. Adds `on_cancel` and `on_trash` logic, which are independent of the multi-vs-single distinction.
- **User Story 4 (Phase 6)**: Depends on Foundational + US1 (the helper and API signature come from US1). Does **not** depend on US2 or US3.
- **Polish (Phase 7)**: Depends on all four stories landing.

### Within Foundational (Phase 2)

- T004, T007 can run in parallel (different files).
- T005 must land **after** T004 (fixture must exist before `hooks.fixtures` references it; otherwise `bench migrate` fails).
- T006 is independent of T004/T005 (different file).
- T009 depends on T001 (directory exists) but is independent of T004–T008.
- T008 must land **after** T007 (patch module must exist before `patches.txt` references it).
- T010 is independent — different file.

### Within Each User Story

- Tests (T011–T013 for US1, T019 for US2, T021–T022 for US3, T025 for US4) MUST be written and run (failing) before their implementation tasks land. This is the TDD gate per constitution X and plan.md.
- Within US1: T014 is independent of T016–T018 (different files). T015 depends on T014 (same file, `_resolve_price_list` is imported). T016, T017 are same-file but different functions — sequence them in order. T018 is independent of T014–T017 (different file, client-side).

### Parallel Opportunities

Within a checkpoint, the following tasks can run in parallel on different machines or developers:

- **Setup**: T001, T002, T003 (three independent directories).
- **Foundational**: T004 ‖ T006 ‖ T007 ‖ T009 ‖ T010 (five independent files).
- **US1 tests**: T011 ‖ T012 ‖ T013 (three independent test files).
- **US1 implementation**: T014 ‖ T018 (helper and JS are in different files); T015 depends on T014.
- **Polish**: T028 ‖ T030 ‖ T031 (translations, tests, lint — independent).

---

## Parallel Example: User Story 1

```bash
# Phase 2 foundational tasks — launch in parallel:
Task: "Author Custom Field fixture in cx_purisol/cx_purisol/fixtures/custom_field.json"      # T004
Task: "Widen booklet controller in .../purisol_coupon_booklet.py"                           # T006
Task: "Create patch stub in cx_purisol/patches/v0_3_0/widen_booklet_validate_for_sale.py"   # T007
Task: "Create sales_invoice_hooks.py skeleton"                                              # T009
Task: "Extend tests/fixtures.py"                                                            # T010

# Then T005 (hooks.py wiring), T008 (patches.txt) sequentially.

# Phase 3 US1 tests — launch in parallel (all three test files are disjoint):
Task: "Widen booklet transition unit tests in test_purisol_coupon_booklet.py"               # T011
Task: "Workflow API unit tests in api/test_sell_booklets.py"                                # T012
Task: "Single-booklet integration tests in tests/test_sales_flows.py"                       # T013

# Phase 3 US1 implementation:
Task: "Implement _resolve_price_list in api/sell_booklets.py"                               # T014
# Then T015 (same file, depends on T014).
Task: "Implement validate_booklet_lines in sales_invoice/sales_invoice_hooks.py"            # T016
# Then T017 in same file.
Task: "Implement list-view JS in public/js/purisol_coupon_booklet_list.js"                  # T018 (parallel with T014–T017)
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 → Phase 2 (Foundational) — nothing is demoable yet but everything compiles and migrates.
2. Phase 3 — write T011–T013 tests first (all red), then T014–T018 until green.
3. **STOP and VALIDATE**: Run quickstart §3 manually and T013 suite in CI.
4. Demo: a single-booklet sale end-to-end. MVP shipped.

### Incremental Delivery

1. **MVP**: Setup + Foundational + US1 → deploy, demo, collect feedback.
2. **Multi-booklet**: US2 → deploy, demo (quickstart §4).
3. **Cancellation**: US3 → deploy, demo (quickstart §5). The most safety-critical story; land it only after US1/US2 are trusted.
4. **Price-list override**: US4 → deploy, demo (quickstart §6). Smallest increment; mostly tests.
5. **Polish**: translations, audit-trail crosscheck, full quickstart rerun.

### Parallel Team Strategy

After Foundational lands:

- Developer A: US1 (MVP-critical path — do not split).
- Developer B: US3 (independent of US1/US2; reuse US1's foundational artefacts but write its own code).
- Developer C: US4 tests early (against a stubbed `_resolve_price_list` from T014).
- US2 tasks wait for US1 implementation to land (reuse of API), then a single developer runs them — almost entirely test authorship.

---

## Notes

- [P] tasks = different files, no incomplete dependencies.
- `[Story]` label maps each task back to its acceptance scenarios in `spec.md`.
- Every test uses `frappe.tests.utils.FrappeTestCase` and lives in the file specified; no ad-hoc test runners.
- Verify tests fail before implementing each story's code (TDD gate).
- Commit after each task or logical group; keep PRs aligned to phase boundaries where possible.
- Avoid: pre-emptively merging hook logic into the Phase-1 booklet controller; smuggling consumption logic into `on_cancel` (Phase 4 concern); introducing any new DocType (constitution II violation).
