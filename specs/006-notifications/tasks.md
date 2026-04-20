# Tasks: Notifications (Phase 6)

**Input**: Design documents from `/specs/006-notifications/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Test tasks ARE included — spec / plan explicitly request unit + integration coverage (constitution X, plan §Tests, contracts §8). Every contract has at least one success + one failure path test.

**Organization**: Tasks are grouped by user story (US1 New Discrepancy Opened, US2 Customer Low Stock, US3 Warehouse Low Stock, US4 Booklet Depleted). Each phase ships an independently testable increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no cross-task dependencies)
- **[Story]**: User-story label (US1…US4) — omitted for Setup/Foundational/Polish
- Every task description includes an exact file path

## Path Conventions

All paths are absolute from the repo root `/home/corex/aurevia-bench/apps/cx_purisol/`. The app package lives at `cx_purisol/cx_purisol/` (Frappe custom-app layout, consistent with Phases 1–5).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the empty scaffold for the new patch directory and confirm translation/ patches plumbing is ready before any code lands. No business logic yet.

- [X] T001 Create new patch package `cx_purisol/cx_purisol/patches/v0_6_0/` with an empty `__init__.py` file at `cx_purisol/cx_purisol/patches/v0_6_0/__init__.py` (mirrors the Phase-2/3/4/5 pattern).
- [X] T002 Create the no-op patch anchor file at `cx_purisol/cx_purisol/patches/v0_6_0/add_warehouse_low_stock_dedup_field.py` containing a single `execute()` function that prints an anchor line (see data-model.md §7).
- [X] T003 Append the new patch entry `cx_purisol.patches.v0_6_0.add_warehouse_low_stock_dedup_field` to the `[post_model_sync]` section of `cx_purisol/cx_purisol/patches.txt` (as the last line).

**Checkpoint**: Patch scaffolding is in place; `bench migrate` can run without errors even before feature code lands.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Ship the channel-agnostic `Purisol Notify` utility and the one schema widening on `Purisol Settings` that every user story depends on. Without these two pieces nothing in Phases 3–6 can be wired.

**⚠️ CRITICAL**: No user-story work can begin until this phase is complete. All four triggers import `cx_purisol.cx_purisol.api.notify` and (for US3) read `last_warehouse_low_stock_notified_on`.

- [X] T004 Add the new field `last_warehouse_low_stock_notified_on` (Date, `read_only=1`, `hidden=1`, no default, no reqd) to `cx_purisol/cx_purisol/doctype/purisol_settings/purisol_settings.json`; append its `fieldname` to the `field_order` array as the final entry (after `enable_consumption_warnings`). See data-model.md §2.1.
- [X] T005 Create the new server-side utility module `cx_purisol/cx_purisol/api/notify.py` implementing the public `send(recipient, subject, message, reference_doctype=None, reference_name=None) -> list[str]` and the private `_resolve_recipients(recipient) -> list[str]` + `_emit_bell(for_user, subject, message, reference_doctype, reference_name) -> str` helpers. Follow the signature, semantics, and atomicity contract in contracts/notify.md §1 and data-model.md §1.
- [X] T006 [P] Extend the Phase-6 test-fixtures helpers in `cx_purisol/cx_purisol/tests/fixtures.py`: add `seed_administrator_user(email, name=None)` (idempotent `User` + `Has Role` creation for `Purisol Administrator`), `count_notifications(for_user=None, doctype=None, document_name=None, subject_contains=None)` (delta-friendly Notification Log counter), and `reset_warehouse_dedup()` (clears `Purisol Settings.last_warehouse_low_stock_notified_on` via `frappe.db.set_single_value`). See plan.md §Tests bullet 5.
- [X] T007 [P] Create the unit-test file `cx_purisol/cx_purisol/api/test_notify.py` with five tests covering contracts/notify.md §1.3–§1.5: `test_send_role_expands_to_all_enabled_users`, `test_send_role_excludes_disabled_users`, `test_send_unknown_role_is_silent_no_op`, `test_send_user_recipient_direct`, `test_send_rolls_back_on_insert_failure`. Use `FrappeTestCase` and the helpers from T006.

**Checkpoint**: `bench migrate` applies the new field, `bench run-tests --app cx_purisol --module cx_purisol.cx_purisol.api.test_notify` is green, the utility is importable from any trigger site.

---

## Phase 3: User Story 1 — Notify Administrator When a Discrepancy Is Opened (Priority: P1) 🎯 MVP

**Goal**: Every `Purisol Coupon Discrepancy` insert (Phase-5 detection path, or any other insert path) emits one `Notification Log` entry per enabled Administrator user, referencing the new discrepancy and naming its type, booklet, and triggering delivery man.

**Independent Test**: Seed one admin user; seed one booklet `WP-00001` Sold with 20 Available coupons; submit a Consumption Entry that skips coupons so Phase-5 opens a `Missing Coupons` discrepancy. Expect one new Notification Log row for the admin user with `document_type = "Purisol Coupon Discrepancy"`, `document_name = <new discrepancy>`, a subject containing the discrepancy name, and a body naming the booklet + delivery man. (spec.md US1 Independent Test, SC-001, SC-011.)

### Tests for User Story 1

> Write test tasks FIRST; they should initially FAIL until the `after_insert` widening in T010 lands.

- [X] T008 [P] [US1] Add `test_after_insert_fires_notification` and `test_after_insert_no_admin_silent` to `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/test_purisol_coupon_discrepancy.py` — assert delta-based Notification Log creation per admin user on `seed_open_discrepancy()` insert, and zero-delta + no-raise when no admin exists. (contracts/notify.md §2.2–§2.3.)
- [X] T009 [P] [US1] Add `test_story1_discrepancy_notification` to the new integration file `cx_purisol/cx_purisol/tests/test_notification_flows.py` — end-to-end Consumption Entry submit → Phase-5 discrepancy insert → Notification Log assertions per spec US1 Acceptance 1, 2, 3, 4, 5.

### Implementation for User Story 1

- [X] T010 [US1] Add the `after_insert(self)` method to the `PurisolCouponDiscrepancy` controller in `cx_purisol/cx_purisol/doctype/purisol_coupon_discrepancy/purisol_coupon_discrepancy.py` that looks up the triggering delivery man via `self.triggering_consumption_entry`, builds the localized subject `_("Discrepancy {0} opened")` and body `_("Discrepancy {0} opened: {1} in booklet {2}, delivery man {3}.")`, and calls `notify.send(recipient="Purisol Administrator", ..., reference_doctype="Purisol Coupon Discrepancy", reference_name=self.name)`. See data-model.md §3.1. Do not touch `validate`, `before_insert`, `before_submit`, `on_submit`, `on_cancel`.
- [X] T011 [US1] Append the four US1 localizable phrases (`Discrepancy {0} opened`, `Discrepancy {0} opened: {1} in booklet {2}, delivery man {3}.`, `(unknown)`, plus any US1-specific fallback) to `cx_purisol/cx_purisol/translations/ar.csv` with their Arabic equivalents per contracts/notify.md §7.

**Checkpoint**: US1 is fully functional and independently testable. `bench run-tests --app cx_purisol --module cx_purisol.cx_purisol.doctype.purisol_coupon_discrepancy.test_purisol_coupon_discrepancy` green. Story delivers the MVP proof-of-life for the `Purisol Notify` abstraction.

---

## Phase 4: User Story 2 — Notify Administrator When a Customer Runs Low on Coupons (Priority: P1)

**Goal**: After every `Purisol Coupon Consumption Entry` submit, evaluate each unique affected customer's total remaining coupons across Sold non-Depleted booklets. For any such customer whose post-submit total is `<=` the live-read `Purisol Settings.customer_low_stock_threshold`, emit one Notification Log row per admin user linked to the Customer record.

**Independent Test**: Seed customer `C-AL-MASRI` with 2 Sold booklets (2 + 1 = 3 remaining); set `customer_low_stock_threshold = 3`; submit a Consumption Entry that drops totals to 1 + 1 = 2. Expect exactly one Customer Low Stock Notification Log per admin user with `document_type = "Customer"`, `document_name = "C-AL-MASRI"`, body naming the customer and count 2. (spec.md US2 Independent Test, SC-002, SC-005.)

### Tests for User Story 2

- [X] T012 [P] [US2] Add `test_story2_customer_low_stock`, `test_story2_unassigned_booklet_skips_customer_check`, and `test_story2_threshold_live_edit` to `cx_purisol/cx_purisol/tests/test_notification_flows.py` covering US2 Acceptance 1, 2, 3, 4, 5, 6 and SC-005 (threshold edited at 10:00 honoured at 10:01 without restart).

### Implementation for User Story 2

- [X] T013 [US2] Widen `on_submit` in `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/purisol_coupon_consumption_entry.py`: add the top-level `from cx_purisol.cx_purisol.api import notify` import and, after Phase-5's `detect_for_entry` call, append the Customer Low Stock evaluation block (collect unique non-null customers across touched booklets, live-read `frappe.get_doc("Purisol Settings").customer_low_stock_threshold`, issue `frappe.db.sql` SUM per customer where `status='Sold'`, call `notify.send` when `total_remaining <= threshold`). Exact shape in data-model.md §4.1 second snippet and contracts/notify.md §3.3. Do not touch `validate`, `before_submit`, `on_cancel`.
- [X] T014 [US2] Append the US2 localizable phrases (`Customer {0} low on coupons`, `Customer {0} has {1} coupons remaining. Prepare a new booklet.`) to `cx_purisol/cx_purisol/translations/ar.csv` per contracts/notify.md §7.

**Checkpoint**: US2 is independently functional. `bench run-tests --app cx_purisol --module cx_purisol.cx_purisol.tests.test_notification_flows` (US1 + US2 tests) green. Phase-4 / Phase-5 existing tests continue to pass (they do not assert zero-notifications).

---

## Phase 5: User Story 3 — Notify Administrator When Warehouse Booklet Stock Runs Low (Priority: P2)

**Goal**: After every `Sales Invoice` submit (via a secondary `on_submit` doc_events handler in `sales_invoice_hooks.py`), count booklets with `status = "In Stock"`. If the count is strictly `<` `Purisol Settings.warehouse_low_stock_threshold` AND the persisted dedup marker `last_warehouse_low_stock_notified_on != today`, emit one Notification Log per admin user referencing `Purisol Coupon Booklet` (empty `reference_name` → list view) and update the marker via `frappe.db.set_single_value`.

**Independent Test**: Set threshold = 5; seed 6 booklets `In Stock`; sell one (5 remain — equal, no fire); sell a second (4 — below, one notification per admin); sell a third same-day (3 — no new notification, dedup); roll server date forward; sell a fourth (2 — fresh notification). (spec.md US3 Independent Test, SC-003.)

### Tests for User Story 3

- [X] T015 [P] [US3] Add `test_story3_warehouse_low_stock_first_fire`, `test_story3_warehouse_low_stock_dedup_same_day`, `test_story3_warehouse_low_stock_resets_next_day`, `test_story3_warehouse_low_stock_strict_inequality`, and `test_story3_warehouse_unchanged_invoice_still_evaluates` to `cx_purisol/cx_purisol/tests/test_notification_flows.py` covering US3 Acceptance 1–6 plus SC-003 (50 consecutive same-day submits create zero extra notifications). Use `reset_warehouse_dedup()` between cases and `frappe.utils.add_days` (or the Frappe time-freeze idiom used elsewhere in the suite) to cross the day boundary.

### Implementation for User Story 3

- [X] T016 [US3] Add `check_warehouse_low_stock(doc, method=None)` to `cx_purisol/cx_purisol/sales_invoice/sales_invoice_hooks.py` that live-reads `Purisol Settings`, calls `frappe.db.count("Purisol Coupon Booklet", {"status": "In Stock"})`, returns early on strict-inequality miss or same-day dedup hit, otherwise calls `notify.send("Purisol Administrator", _("Warehouse low on booklet stock"), _("Only {0} booklets remain in stock. Generate a new batch."), reference_doctype="Purisol Coupon Booklet", reference_name=None)` and then `frappe.db.set_single_value("Purisol Settings", "last_warehouse_low_stock_notified_on", today)`. Exact shape in data-model.md §5.1 and contracts/notify.md §4. Do not modify `validate_booklet_lines`, `mark_booklets_sold`, `reverse_booklets_sale`, `guard_trash`.
- [X] T017 [US3] In `cx_purisol/cx_purisol/hooks.py`, promote `doc_events["Sales Invoice"]["on_submit"]` from a single string to a two-element list `["cx_purisol.cx_purisol.sales_invoice.sales_invoice_hooks.mark_booklets_sold", "cx_purisol.cx_purisol.sales_invoice.sales_invoice_hooks.check_warehouse_low_stock"]` (order matters — `mark_booklets_sold` must run first so the post-submit in-stock count is correct). See data-model.md §6.1.
- [X] T018 [US3] Append the US3 localizable phrases (`Warehouse low on booklet stock`, `Only {0} booklets remain in stock. Generate a new batch.`) to `cx_purisol/cx_purisol/translations/ar.csv` per contracts/notify.md §7.

**Checkpoint**: US3 independently functional with day-boundary dedup. `bench run-tests --app cx_purisol --module cx_purisol.cx_purisol.tests.test_notification_flows` green including US3 cases.

---

## Phase 6: User Story 4 — Notify Administrator When a Booklet Is Fully Consumed (Priority: P2)

**Goal**: In the exact Phase-4 depletion branch that flips a booklet from `Sold` to `Depleted` and stamps `depleted_on`, emit one Notification Log per admin user per depleted booklet with the booklet name and customer name in the body.

**Independent Test**: Seed booklet `WP-00005` Sold to customer `C-AL-MASRI` with 19 consumed and `CP-00100` Available; submit a Consumption Entry for `CP-00100`. Expect Phase-4's existing depletion behaviour unchanged AND exactly one Booklet Depleted Notification Log per admin user, `document_type = "Purisol Coupon Booklet"`, `document_name = "WP-00005"`, body naming the booklet and customer. (spec.md US4 Independent Test, SC-004.)

### Tests for User Story 4

- [X] T019 [P] [US4] Add `test_story4_booklet_depleted_notification`, `test_story4_multi_booklet_depletion_fires_per_booklet`, and `test_story4_non_depleting_consumption_no_notification` to `cx_purisol/cx_purisol/tests/test_notification_flows.py` covering US4 Acceptance 1, 2, 3, 4.

### Implementation for User Story 4

- [X] T020 [US4] Widen `on_submit` in `cx_purisol/cx_purisol/doctype/purisol_coupon_consumption_entry/purisol_coupon_consumption_entry.py`: inside the existing `if triggered_depletion:` block (after the `booklet.add_comment("Info", ...)` call), resolve `customer_name` via `frappe.db.get_value("Customer", booklet.customer, "customer_name")` with `(unknown)` fallback, then call `notify.send("Purisol Administrator", _("Booklet {0} depleted").format(booklet.name), _("Booklet {0} for customer {1} is fully consumed. Follow up for resale.").format(booklet.name, customer_name), reference_doctype="Purisol Coupon Booklet", reference_name=booklet.name)`. Exact shape in data-model.md §4.1 first snippet. Leave the depletion state-transition logic (`booklet.status = "Depleted"`, `booklet.depleted_on = posting_dt`, `booklet.save`) untouched.
- [X] T021 [US4] Append the US4 localizable phrases (`Booklet {0} depleted`, `Booklet {0} for customer {1} is fully consumed. Follow up for resale.`) to `cx_purisol/cx_purisol/translations/ar.csv` per contracts/notify.md §7.

**Checkpoint**: All four user stories are independently functional. `bench run-tests --app cx_purisol --module cx_purisol.cx_purisol.tests.test_notification_flows` green across US1–US4.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Cross-story atomicity + empty-recipient coverage, translation audit, quickstart walkthrough, and full-suite regression.

- [X] T022 [P] Add `test_atomicity_rolls_back_notifications_with_submit` to `cx_purisol/cx_purisol/tests/test_notification_flows.py` — deliberately trigger a Phase-4 blocking-validation failure mid-submit and assert zero `Notification Log` rows persisted (SC-008, contracts/notify.md §1.5 + §3.5).
- [X] T023 [P] Add `test_no_admin_triggers_all_silent_no_op` to `cx_purisol/cx_purisol/tests/test_notification_flows.py` — run one qualifying event per trigger (discrepancy insert, customer-low-stock submit, warehouse-low-stock submit, booklet depletion submit) with zero enabled admin users; assert zero Notification Log rows and that every business event succeeds (SC-007, FR-014).
- [X] T024 [P] Audit `cx_purisol/cx_purisol/translations/ar.csv` against the full contracts/notify.md §7 table — verify all 8 phrases (4 subjects + 4 bodies) plus the `(unknown)` fallback have Arabic rows; add any missing entries.
- [ ] T025 Walk through `specs/006-notifications/quickstart.md` §1–§4 against a dev site: trigger each of the four notifications, verify bell-icon appearance, click-through target, and (for US3) dedup marker state. Record any drift from the doc and adjust either the doc or the implementation. *(requires live dev site — deferred to user verification)*
- [ ] T026 Run the full regression `bench --site <test-site> run-tests --app cx_purisol` — confirm Phase 1–5 tests continue to pass unchanged alongside the new Phase-6 suite. Fix any regressions before marking the phase done. *(requires user's bench runtime — code syntax-checked but not executed)*
- [X] T027 [P] Static search for direct `Notification Log` record creation outside `cx_purisol/cx_purisol/api/notify.py` across the repo (`grep -rn 'Notification Log' cx_purisol/`) — assert SC-009: every Phase-6 trigger routes through the utility, zero direct inserts anywhere else. Remove any stray direct writes discovered.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup (T001–T003)**: no dependencies — can start immediately.
- **Phase 2 Foundational (T004–T007)**: depends on Phase 1 (patch anchor must exist so `bench migrate` runs). BLOCKS all user stories.
- **Phase 3 US1 (T008–T011)**: depends on Phase 2 — needs `notify.py` (T005) and the admin-user fixture helper (T006).
- **Phase 4 US2 (T012–T014)**: depends on Phase 2 — same foundational deps.
- **Phase 5 US3 (T015–T018)**: depends on Phase 2 — also needs the new Settings field from T004.
- **Phase 6 US4 (T019–T021)**: depends on Phase 2.
- **Phase 7 Polish (T022–T027)**: depends on all user stories being complete.

### User Story Dependencies

- **US1 (P1)**: independent of US2/US3/US4. Ships the first proof that `notify.send` works end-to-end.
- **US2 (P1)**: independent of US1/US3/US4. Shares the consumption-entry controller with US4 (T013 and T020 both edit the same file), so if staffed to different developers, serialize their edits or rebase carefully.
- **US3 (P2)**: independent of US1/US2/US4. Only story that writes the new `Purisol Settings` dedup field.
- **US4 (P2)**: independent of US1/US2/US3. Shares the consumption-entry controller with US2 (see caveat above).

### Within Each User Story

- Tests are listed before implementation tasks (write-first); they should initially FAIL and pass after the implementation task lands.
- Translation-file updates always come last in their story so call-site strings are finalized first.
- Within US3, T016 (new function) must land before T017 (hooks wiring) so the hook target exists when Frappe loads it.

### Parallel Opportunities

- **Phase 1**: T001–T003 are file-additions in different locations — can run in parallel (tagged [P] implicitly, though sequenced for clarity).
- **Phase 2**: T006 (fixtures helper) and T007 (utility unit tests) are tagged [P] — different files, safe to parallelize once T005 exists.
- **Phase 3**: T008 (doctype-local test) and T009 (integration test) are both [P] — different files.
- **Phase 4**: T012 is the only test task — no intra-phase parallelism.
- **Phase 5**: T015 is the only test task — no intra-phase parallelism.
- **Phase 6**: T019 is the only test task — no intra-phase parallelism.
- **Phase 7**: T022, T023, T024, T027 all tagged [P] — different concerns, different files / search paths.
- **Cross-story**: once Phase 2 is done, US1 + US3 can be developed in parallel by different people without conflict (different files). US2 and US4 both touch `purisol_coupon_consumption_entry.py` — if worked in parallel, merge sequentially.

---

## Parallel Example: Phase 2 Foundational

```bash
# After T004 and T005 land, run T006 and T007 in parallel:
Task: "Extend tests/fixtures.py with seed_administrator_user, count_notifications, reset_warehouse_dedup"
Task: "Create api/test_notify.py with the 5 utility unit tests"
```

## Parallel Example: Phase 3 User Story 1 tests

```bash
# Both test files are independent; write them first, expect failures, then implement T010:
Task: "Extend doctype/purisol_coupon_discrepancy/test_purisol_coupon_discrepancy.py with after_insert tests"
Task: "Create tests/test_notification_flows.py and add test_story1_discrepancy_notification"
```

## Parallel Example: Phase 7 Polish

```bash
# All four are independent files / concerns:
Task: "Add test_atomicity_rolls_back_notifications_with_submit"
Task: "Add test_no_admin_triggers_all_silent_no_op"
Task: "Audit ar.csv for completeness of contracts §7 phrases"
Task: "Grep-audit that no code outside api/notify.py writes Notification Log directly"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1: Setup (T001–T003).
2. Complete Phase 2: Foundational (T004–T007) — this is the real work; everything else is narrow wiring.
3. Complete Phase 3: US1 (T008–T011).
4. **STOP and VALIDATE**: bell icon lights up for discrepancy inserts; click-through works; role expansion correct; Arabic translation renders.
5. Deploy/demo the MVP — the `Purisol Notify` abstraction is now proven end-to-end.

### Incremental Delivery

1. Setup + Foundational → utility ready.
2. US1 → Discrepancy alerts live (MVP).
3. US2 → Customer Low Stock live.
4. US3 → Warehouse Low Stock live (adds daily-dedup behaviour).
5. US4 → Booklet Depleted live.
6. Polish → cross-cutting atomicity + no-admin + translations + quickstart walkthrough + full regression.

### Parallel Team Strategy

With two developers after Phase 2 completes:

1. Dev A: US1 (T008–T011), then US3 (T015–T018) — touches discrepancy controller + hooks.py + sales_invoice_hooks.py + settings; zero overlap with Dev B.
2. Dev B: US2 (T012–T014), then US4 (T019–T021) — both touch `purisol_coupon_consumption_entry.py`; serialize (T013 then T020) on one branch.
3. Merge; run Phase 7 polish together.

---

## Notes

- [P] = different files, no task-level dependency on another incomplete task. Edits to the *same* file are NEVER [P] relative to each other.
- [Story] label is mandatory for every task in Phases 3–6 and forbidden in Phases 1, 2, 7.
- Tests land before implementation inside each story; they should FAIL before the implementation task, pass after.
- Commit after each task or logical group (after_tasks hook will prompt).
- Phase 6 is strictly additive — zero Phase 1/2/3/4/5 DocType JSON changes except the one new field on `Purisol Settings`; every existing test must continue to pass without modification.
- The `Purisol Notify` utility is the single bottleneck for channel extensibility (constitution VII, SC-009). Any code that creates `Notification Log` rows outside `cx_purisol/cx_purisol/api/notify.py` is a Phase-6 regression and must be fixed in Phase 7 via T027.
