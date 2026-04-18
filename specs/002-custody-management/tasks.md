---
description: "Task list for Phase 2 — Custody Management"
---

# Tasks: Custody Management

**Input**: Design documents from `/specs/002-custody-management/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/custody-entry.md, quickstart.md

**Tests**: Test tasks are included because the feature specification and constitution X explicitly require them (unit + integration test files are named in research.md §10).

**Organization**: Tasks are grouped by user story (US1–US4) so each can be implemented and verified independently after the Foundational phase is complete.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1 = Assign, US2 = Return, US3 = Transfer, US4 = Current Custody view)
- Paths are relative to the git-repo root `/home/corex/aurevia-bench/apps/cx_purisol/`; the Frappe Python package root is `cx_purisol/` (i.e. `cx_purisol/cx_purisol/...` holds DocTypes).

## Path Conventions

- Frappe custom-app layout: `cx_purisol/cx_purisol/doctype/<doctype_slug>/` and `cx_purisol/cx_purisol/report/<report_slug>/`.
- Shared/integration tests live under `cx_purisol/cx_purisol/tests/`.
- Fixtures under `cx_purisol/cx_purisol/fixtures/`; app-level patches under `cx_purisol/patches.txt` + `cx_purisol/patches/v0_2_0/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create empty package directories and patch scaffolding so later phases can write files into known locations without churn.

- [x] T001 [P] Create package directory `cx_purisol/cx_purisol/doctype/purisol_custody_entry/` with an empty `cx_purisol/cx_purisol/doctype/purisol_custody_entry/__init__.py`
- [x] T002 [P] Create package directory `cx_purisol/cx_purisol/doctype/purisol_custody_entry_booklet/` with an empty `cx_purisol/cx_purisol/doctype/purisol_custody_entry_booklet/__init__.py`
- [x] T003 [P] Create report package `cx_purisol/cx_purisol/report/__init__.py` and subpackage `cx_purisol/cx_purisol/report/current_custody_by_delivery_man/__init__.py`
- [x] T004 [P] Create patch package `cx_purisol/patches/__init__.py` and `cx_purisol/patches/v0_2_0/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Land the shared scaffolding that every user story depends on — Phase-1 booklet widening, the new DocType JSONs, the controller skeleton with uniform (non-type-specific) logic, permissions, and the patch entry.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete. Each story adds its own entry-type branch to controllers/client-script and its own test cases; the dispatch shape and cross-cutting concerns belong here.

- [x] T005 Widen `Purisol Coupon Booklet.validate` to allow statuses `{In Stock, In Custody}`, reject `{Sold, Depleted}` with `frappe.ValidationError`, and forbid any transition other than `In Stock ↔ In Custody` via `self.get_doc_before_save()` comparison, in `cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/purisol_coupon_booklet.py`
- [x] T006 [P] Add client script that sets `status` and `current_delivery_man` read-only on the booklet form at `refresh`, in `cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/purisol_coupon_booklet.js`
- [x] T007 [P] Create child-table DocType JSON with `istable = 1`, `track_changes = 1`, and fields `booklet` (Link → Purisol Coupon Booklet, required), `booklet_status_at_entry` (Data, read-only), `delivery_man_at_entry` (Link → Employee, read-only), in `cx_purisol/cx_purisol/doctype/purisol_custody_entry_booklet/purisol_custody_entry_booklet.json`
- [x] T008 [P] Create minimal child-table Python controller (class stub only) in `cx_purisol/cx_purisol/doctype/purisol_custody_entry_booklet/purisol_custody_entry_booklet.py`
- [x] T009 Create parent DocType JSON `Purisol Custody Entry` with `is_submittable = 1`, `track_changes = 1`, `autoname = "PCE-.YYYY.-.#####"`, fields `entry_type` (Select: `Assign\nTransfer\nReturn`), `from_delivery_man` (Link → Employee), `to_delivery_man` (Link → Employee), `entry_datetime` (Datetime, default `now`), `notes` (Small Text), `created_by` (Link → User, read-only), `booklets` (Table → Purisol Custody Entry Booklet), plus `mandatory_depends_on` rules per entry_type, and permission block for `Purisol Administrator` (`read/write/create/submit/cancel = 1`, `amend/delete = 0`), in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.json`
- [x] T010 Create parent controller skeleton with `before_insert` (set `created_by = frappe.session.user`), `validate` with common checks (non-empty child table, no duplicate booklets) and an `entry_type` dispatch to per-type hooks that will be filled per user story, `before_submit` that batch-snapshots every child row's `booklet_status_at_entry` and `delivery_man_at_entry` from live booklet state, and empty `on_submit` / `on_cancel` dispatchers that branch on `entry_type`, in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.py`
- [x] T011 [P] Create parent client-script skeleton that on `refresh` and on `entry_type` change calls a `_apply_entry_type_ux(frm)` helper (placeholder — each story fills in its own branch), in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.js`
- [x] T012 [P] Extend role fixture to grant `Purisol Administrator` the `read/write/create/submit/cancel` perms on `Purisol Custody Entry`, in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.json` (permissions embedded in DocType JSON)
- [x] T013 [P] Add `cx_purisol.patches.v0_2_0.widen_booklet_validate_allowed_states` to `cx_purisol/patches.txt` and create the no-op patch module that clears cached DocType metadata after widening, in `cx_purisol/patches/v0_2_0/widen_booklet_validate_allowed_states.py`
- [x] T014 [P] Create shared test helpers (`make_employee`, `make_booklet_in_stock`, `submit_assign`, etc.) used by all Phase 2 tests, in `cx_purisol/cx_purisol/tests/fixtures.py`

**Checkpoint**: Foundation ready — `bench migrate` installs both new DocTypes, Phase-1 booklet accepts `In Custody`, permissions are in place, and all later phases can fill in their per-type branches without touching scaffolding.

---

## Phase 3: User Story 1 — Assign Booklets from Shop to a Delivery Man (Priority: P1) 🎯 MVP

**Goal**: Administrator creates a submittable `Purisol Custody Entry` of type `Assign` listing `In Stock` booklets and a `to_delivery_man`; on submit every listed booklet becomes `In Custody` with `current_delivery_man` set to the chosen employee. Rejects invalid source states, missing fields, and partial updates.

**Independent Test**: Seed 2–3 `In Stock` booklets (Phase-1 output) and 1 Employee; insert + submit a `Purisol Custody Entry` of type `Assign` listing those booklets and that employee; assert booklets are `In Custody` with `current_delivery_man = <employee>`, entry is `docstatus = 1`, and `tabPurisol Custody Entry Booklet.booklet_status_at_entry` is `In Stock` for each row. Then cancel the entry and assert reversal.

### Implementation for User Story 1

- [x] T015 [US1] Implement the `Assign` branch of `validate`: require `to_delivery_man`, reject `from_delivery_man`, and for every child-row booklet assert `status == "In Stock"` (collect all mismatches and throw with a single translated message naming each booklet + its actual status), in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.py`
- [x] T016 [US1] Implement the `Assign` branch of `on_submit`: for each child row, `booklet = frappe.get_doc("Purisol Coupon Booklet", row.booklet)`, set `status = "In Custody"` and `current_delivery_man = self.to_delivery_man`, then `booklet.save(ignore_permissions=True)`, in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.py`
- [x] T017 [US1] Implement the `Assign` branch of `on_cancel`: expected current state `status = "In Custody"`, `current_delivery_man = self.to_delivery_man`; on mismatch collect and throw `_("Cannot cancel: booklet {0} has since moved …")`; on match, revert each booklet to `(row.booklet_status_at_entry, row.delivery_man_at_entry)` via `booklet.save(ignore_permissions=True)`, in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.py`
- [x] T018 [US1] Add the `Assign` branch to the client-script `_apply_entry_type_ux` helper: hide `from_delivery_man`, show + mark required `to_delivery_man`, and apply booklet-link filter `status = "In Stock"` to the child table, in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.js`

### Tests for User Story 1

- [x] T019 [P] [US1] Unit tests `test_assign_requires_to_delivery_man`, `test_assign_forbids_from_delivery_man`, `test_rejects_empty_child_table`, `test_rejects_duplicate_booklet_in_entry`, `test_assign_rejects_booklet_not_in_stock`, `test_snapshot_filled_before_submit`, in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/test_purisol_custody_entry.py`
- [x] T020 [P] [US1] Integration tests `test_assign_end_to_end` (booklets `In Stock → In Custody` with correct `current_delivery_man`) and `test_cancel_reverses_assign` (cancel an Assign entry; booklet returns to `In Stock`, `current_delivery_man` cleared), in `cx_purisol/cx_purisol/tests/test_custody_flows.py`

**Checkpoint**: User Story 1 is independently shippable. `bench run-tests --app cx_purisol` is green for Phase 1 + the US1 subset; quickstart.md §3 (and §7.1/7.5 rejection paths) can be executed against a dev site.

---

## Phase 4: User Story 2 — Return Booklets from a Delivery Man to the Shop (Priority: P2)

**Goal**: Administrator records a `Return` entry selecting `from_delivery_man` and the returned booklets; on submit each listed booklet transitions from `In Custody` back to `In Stock` with `current_delivery_man` cleared.

**Independent Test**: After seeding the US1 end-state (a booklet `In Custody` held by `Ali`), submit a `Return` entry with `from_delivery_man = Ali` listing that booklet; assert the booklet is now `In Stock` with `current_delivery_man = None`; assert any other booklet still held by Ali is unchanged. Then cancel the Return entry and assert reversal to the `In Custody/Ali` snapshot.

### Implementation for User Story 2

- [x] T021 [US2] Implement the `Return` branch of `validate`: require `from_delivery_man`, reject `to_delivery_man`, and for every child-row booklet assert `status == "In Custody"` AND `current_delivery_man == self.from_delivery_man` (collect mismatches into a single translated throw that names the booklet and — where relevant — its actual holder), in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.py`
- [x] T022 [US2] Implement the `Return` branch of `on_submit`: set each listed booklet's `status = "In Stock"` and `current_delivery_man = None` via `booklet.save(ignore_permissions=True)`, in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.py`
- [x] T023 [US2] Implement the `Return` branch of `on_cancel`: expected current state `status = "In Stock"`, `current_delivery_man = None`; on match revert to snapshot (`row.booklet_status_at_entry == "In Custody"`, `row.delivery_man_at_entry == self.from_delivery_man`), in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.py`
- [x] T024 [US2] Add the `Return` branch to the client-script helper: show + mark required `from_delivery_man`, hide `to_delivery_man`, apply booklet-link filter `status = "In Custody"` AND `current_delivery_man = from_delivery_man`, in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.js`

### Tests for User Story 2

- [x] T025 [P] [US2] Unit tests `test_return_requires_from_delivery_man`, `test_return_forbids_to_delivery_man`, `test_return_rejects_booklet_held_by_other`, `test_return_rejects_booklet_not_in_custody`, in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/test_purisol_custody_entry.py`
- [x] T026 [P] [US2] Integration tests `test_return_end_to_end` (booklets `In Custody → In Stock`, `current_delivery_man` cleared; sibling booklet of same delivery man unchanged) and `test_cancel_reverses_return` (cancel a Return; booklet goes back to `In Custody` with original holder), in `cx_purisol/cx_purisol/tests/test_custody_flows.py`

**Checkpoint**: US1 + US2 are both independently functional; quickstart.md §5 executes against a dev site.

---

## Phase 5: User Story 3 — Transfer Booklets Between Delivery Men, Including Partial Transfers (Priority: P2)

**Goal**: Administrator records a `Transfer` entry with `from_delivery_man` and `to_delivery_man` set and lists an arbitrary subset of booklets currently held by `from_delivery_man`; on submit only those booklets change hands — `current_delivery_man` updates while `status` stays `In Custody`. Self-transfer and mixed-holder entries are rejected.

**Independent Test**: Seed 2 booklets `In Custody` with Ali and 2 with Sami; submit a single `Transfer` from Ali to Sami listing only one of Ali's booklets; assert exactly that booklet now has `current_delivery_man = Sami`, Ali still holds one booklet, Sami holds three, all four remain `In Custody`, and exactly one `Purisol Custody Entry` record exists for the handoff (SC-007). Additional scenarios: reject self-transfer, reject transfer with one booklet held by a third party (entire entry rolls back), cancel-reverses-transfer, cancel-rejected-if-booklet-subsequently-moved, and custody history reconstruction across Assign → Transfer → Return.

### Implementation for User Story 3

- [x] T027 [US3] Implement the `Transfer` branch of `validate`: require both `from_delivery_man` and `to_delivery_man`, reject `from == to` with `_("A Transfer from a delivery man to themselves is not meaningful.")`, and for every child-row booklet assert `status == "In Custody"` AND `current_delivery_man == self.from_delivery_man` (collect mismatches into a single translated throw), in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.py`
- [x] T028 [US3] Implement the `Transfer` branch of `on_submit`: for each listed booklet, set `current_delivery_man = self.to_delivery_man` while leaving `status` unchanged at `In Custody`, via `booklet.save(ignore_permissions=True)`, in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.py`
- [x] T029 [US3] Implement the `Transfer` branch of `on_cancel`: expected current state `status = "In Custody"`, `current_delivery_man = self.to_delivery_man`; on match revert to snapshot (`row.delivery_man_at_entry == self.from_delivery_man`), in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.py`
- [x] T030 [US3] Add the `Transfer` branch to the client-script helper: show + mark required both `from_delivery_man` and `to_delivery_man`, apply booklet-link filter `status = "In Custody"` AND `current_delivery_man = from_delivery_man`, in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.js`

### Tests for User Story 3

- [x] T031 [P] [US3] Unit tests `test_transfer_requires_both`, `test_transfer_rejects_self`, `test_transfer_rejects_booklet_held_by_other`, `test_transfer_rejects_booklet_not_in_custody`, in `cx_purisol/cx_purisol/doctype/purisol_custody_entry/test_purisol_custody_entry.py`
- [x] T032 [P] [US3] Integration tests `test_partial_transfer` (subset moves, rest stays, one entry record), `test_atomic_rollback_on_invalid_booklet` (one of three booklets invalid — no booklet changes state), `test_cancel_reverses_transfer` (cancel returns booklet to `from_delivery_man`), `test_cancel_rejected_if_booklet_subsequently_moved` (Assign → Transfer; cancelling the Assign fails with the "has since moved" message), and `test_custody_history_reconstructible` (Assign → Transfer → Return on a single booklet; query `Purisol Custody Entry Booklet` by `booklet` and assert all three parents are returned in chronological order), in `cx_purisol/cx_purisol/tests/test_custody_flows.py`

**Checkpoint**: US1 + US2 + US3 all independently functional. Quickstart.md §4 and §7.2 / §7.3 / §8.2 execute cleanly; SC-007 (one record per handoff) is verified.

---

## Phase 6: User Story 4 — Observe Current Custody by Delivery Man (Priority: P3)

**Goal**: Ship the Query Report `Current Custody by Delivery Man` listing exactly the booklets currently `In Custody`, with columns `current_delivery_man`, `booklet`, `days_in_custody`, `customer` (null in Phase 2, present for forward-compat), and `batch_id`; groupable by `current_delivery_man`; filterable by `delivery_man` and `batch_id`.

**Independent Test**: After exercising US1–US3 to produce 2 delivery men and 5 booklets with a known mix (some `In Stock`, some `In Custody`), open the report; assert only `In Custody` booklets appear, grouping by `current_delivery_man` yields the expected groups, `days_in_custody` reflects the most-recent Custody Entry (not the first), and the `delivery_man` filter narrows correctly. Load time ≤ 2 s for up to 1,000 `In Custody` booklets (SC-005).

### Implementation for User Story 4

- [x] T033 [US4] Create the Query Report JSON `Current Custody by Delivery Man` with `report_type = "Query Report"`, reference doctype `Purisol Coupon Booklet`, filter definitions for `delivery_man` (Link → Employee) and `batch_id` (Data), column definitions (`current_delivery_man`, `booklet`, `days_in_custody`, `customer`, `batch_id`) each wrapped in `frappe._()` labels, and a SQL query that selects from `tabPurisol Coupon Booklet` filtered `status = 'In Custody'` with LEFT JOIN onto `tabPurisol Custody Entry Booklet` + `tabPurisol Custody Entry` (docstatus = 1) to compute `DATEDIFF(NOW(), MAX(entry_datetime)) AS days_in_custody`, plus roles block granting `Purisol Administrator` read, in `cx_purisol/cx_purisol/report/current_custody_by_delivery_man/current_custody_by_delivery_man.json`
- [x] T034 [US4] Add the report's Python stub (kept minimal — returns `(columns, data)` only if the Query Report JSON delegates; otherwise an empty stub to keep Frappe's auto-discovery happy and to host any future server-side post-processing), in `cx_purisol/cx_purisol/report/current_custody_by_delivery_man/current_custody_by_delivery_man.py`
- [x] T035 [US4] If the role-permission path requires a separate `Has Role` entry beyond the JSON roles block, extend `cx_purisol/cx_purisol/fixtures/role.json` (or the sibling `custom_docperm.json` if present) to grant `Purisol Administrator` read on the new report

### Tests for User Story 4

- [x] T036 [P] [US4] Integration tests `test_report_lists_only_in_custody` (seed mix of statuses; report returns only `In Custody` rows, none of the `In Stock` ones), `test_report_grouping_by_delivery_man` (two delivery men + four booklets across two groups), `test_report_days_in_custody_matches_latest_entry` (seed an `Assign` then a `Transfer` for the same booklet; assert `days_in_custody` is computed from the Transfer's `entry_datetime`, not the Assign's), in `cx_purisol/cx_purisol/report/current_custody_by_delivery_man/test_current_custody_by_delivery_man.py`

**Checkpoint**: All four user stories are independently functional. Quickstart.md §6 executes; SC-001, SC-002, SC-003, SC-004, SC-005, SC-006, SC-007 are each verifiable.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Verification, localization sweep, and end-to-end validation before declaring the phase done.

- [x] T037 [P] Grep every Phase-2 source file for bare English strings passed to `frappe.throw` / `frappe.msgprint` / JSON `label` and wrap each in `frappe._()` with named placeholders (constitution IX), touching `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.py`, `cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/purisol_coupon_booklet.py`, `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.js`, and both report files
- [x] T038 [P] Confirm index hints on `Purisol Custody Entry Booklet.booklet` and `Purisol Coupon Booklet.current_delivery_man` (add `search_index` on the child-row JSON field and, if missing, on the booklet `current_delivery_man` field) to support the SC-005 load-time target, touching `cx_purisol/cx_purisol/doctype/purisol_custody_entry_booklet/purisol_custody_entry_booklet.json` and `cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/purisol_coupon_booklet.json`
- [ ] T039 Run the full test suite `bench --site <test-site> run-tests --app cx_purisol` and fix any regression introduced by the Phase-1 booklet widening; verify zero warnings in `bench console` when importing the new DocType modules (no path left from `cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.py`)
- [ ] T040 Execute `quickstart.md` §2 → §9 against a dev site (Assign → Transfer → Return → report → rejection cases → cancel happy-path and conflict-path); record any drift from the documented outputs and fix the underlying code, not the quickstart

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup. **BLOCKS every user story** because the DocType JSONs, controller skeleton, permissions, and patch scaffolding must exist first.
- **User Stories (Phase 3–6)**: All depend on Foundational. Once Foundational is complete, stories can proceed in priority order (recommended) or in parallel across developers — each story fills in its own type-branch in the same controller/client-script files, so parallel story work serializes on those two files; story-scoped tests (T019/T020, T025/T026, T031/T032, T036) are safe to write in parallel *within* a story because unit vs integration live in different files.
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### User Story Dependencies

- **US1 (Assign, P1)**: No dependencies on other stories.
- **US2 (Return, P2)**: Domain-independent of US1 (Return is validated directly against `In Custody`/`from_delivery_man`; it does not require US1 code to exist). However, a *realistic* integration test for Return needs an `In Custody` booklet, which is most easily produced by `submit_assign` — so the shared test helper from T014 is the bridge.
- **US3 (Transfer, P2)**: Same as US2 — validation is independent of US1/US2; integration tests reuse the shared helper to seed state.
- **US4 (Report, P3)**: Depends on US1+US3 data being producible (to seed "multiple delivery men with a mix of booklets") but does not depend on US2 for its logic. The report tests use the shared helper to seed state.

### Within Each User Story

1. Controller validate branch (T015 / T021 / T027) before
2. Controller `on_submit` branch (T016 / T022 / T028) before
3. Controller `on_cancel` branch (T017 / T023 / T029) before
4. Client-script branch (T018 / T024 / T030) — UX-only, can technically happen in parallel with 1–3 but is grouped here for coherence.
5. Unit + integration tests (T019+T020 / T025+T026 / T031+T032 / T036) — may be written in parallel with each other because they live in different files; the two tests within one story are [P].

### Parallel Opportunities

- **Phase 1**: All four setup tasks (T001–T004) touch different directories — fully parallel.
- **Phase 2**: T006 (booklet JS) ‖ T007 (child JSON) ‖ T008 (child controller) ‖ T011 (parent JS skeleton) ‖ T012 (role fixture) ‖ T013 (patches) ‖ T014 (test fixtures) all touch different files. T005 (booklet validate widening) and T009 (parent JSON) and T010 (parent controller skeleton) each touch one specific file and can interleave freely with the [P] set above.
- **Within each story's tests**: unit-test task [P] integration-test task.
- **Across stories (parallel developers)**: US1, US2, US3, US4 *implementation* tasks each touch the same three files (`purisol_custody_entry.py`, `purisol_custody_entry.js`, `test_purisol_custody_entry.py`, `test_custody_flows.py`) — so cross-story parallelism requires coordinated diffs, not truly independent branches. The safest parallel cut is: one developer per story for tests, and *serial* controller edits merged in story order.

---

## Parallel Example: Phase 2 Foundational

```bash
# After T005 / T009 / T010 are in, these can be developed in parallel:
Task: "Client script locking booklet form fields in cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/purisol_coupon_booklet.js"
Task: "Child table JSON in cx_purisol/cx_purisol/doctype/purisol_custody_entry_booklet/purisol_custody_entry_booklet.json"
Task: "Child table Python controller in cx_purisol/cx_purisol/doctype/purisol_custody_entry_booklet/purisol_custody_entry_booklet.py"
Task: "Parent client-script skeleton in cx_purisol/cx_purisol/doctype/purisol_custody_entry/purisol_custody_entry.js"
Task: "Role fixture update in cx_purisol/cx_purisol/fixtures/role.json"
Task: "patches.txt entry and patch module in cx_purisol/patches/v0_2_0/widen_booklet_validate_allowed_states.py"
Task: "Shared test helpers in cx_purisol/cx_purisol/tests/fixtures.py"
```

## Parallel Example: User Story 1 Tests

```bash
# Once T015–T018 are in, write both test files in parallel:
Task: "Unit tests in cx_purisol/cx_purisol/doctype/purisol_custody_entry/test_purisol_custody_entry.py"
Task: "Integration tests in cx_purisol/cx_purisol/tests/test_custody_flows.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational — including the Phase-1 booklet validate widening (T005), the two DocType JSONs (T007, T009), the controller skeleton with uniform snapshot + empty/duplicate checks (T010), permissions (T012), and the patch entry (T013).
3. Complete Phase 3: User Story 1 (Assign) — one type branch across validate/`on_submit`/`on_cancel` + client-script + tests.
4. **STOP and VALIDATE**: run `bench run-tests --app cx_purisol`, execute quickstart.md §3 + §7.1/7.5 + §8.1 on a dev site. The shop can now track who carries which booklet and revert mistaken assigns — a shippable slice.
5. Deploy/demo if desired.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. Add US1 (Assign) → independently testable via quickstart §3 → demo (MVP).
3. Add US2 (Return) → independently testable via quickstart §5 → demo.
4. Add US3 (Transfer, incl. partial) → independently testable via quickstart §4 + SC-007 → demo.
5. Add US4 (Report) → independently testable via quickstart §6 + SC-005 → demo.
6. Polish (Phase 7) → ship.

### Parallel Team Strategy

With multiple developers after Foundational lands:

- Dev A: US1 (Assign) — owns the first diff on `purisol_custody_entry.py` / `.js` / tests.
- Dev B: US2 (Return) — rebases on Dev A.
- Dev C: US3 (Transfer) — rebases on Dev A/B; owns the most integration-test surface.
- Dev D: US4 (Report) — owns `report/current_custody_by_delivery_man/` files entirely, no rebase on A/B/C; can proceed in parallel from the moment Foundational is in.

US4 is the cleanest parallel candidate because it touches an isolated file tree. US1/US2/US3 serialize on the two shared controller/client-script files.

---

## Notes

- `[P]` means different files, no unfinished dependency — safe to run in parallel.
- `[Story]` is mandatory for every task in Phases 3–6 and forbidden elsewhere.
- Tests are required for this phase (constitution X + research.md §10) — not optional.
- Every user-visible string added in this phase MUST be wrapped in `frappe._()` (Phase 7 T037 is the safety net, not an excuse to skip the wrap in the original task).
- Commit after each task or after a small logical group (the extensions.yml `after_tasks` hook is available).
- Stop at any checkpoint to validate the story independently before moving on.
