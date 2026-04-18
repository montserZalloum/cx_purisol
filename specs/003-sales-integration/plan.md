# Implementation Plan: Sales Integration

**Branch**: `003-sales-integration` | **Date**: 2026-04-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-sales-integration/spec.md`

## Summary

Sell one or more `In Stock` / `In Custody` `Purisol Coupon Booklet` records to a `Customer` through a standard ERPNext `Sales Invoice` — with no parallel sale DocType, no custom ledger, and no consumption/discrepancy logic. The Administrator launches a "Sell Booklets to Customer" workflow, picks the customer, multi-selects booklets, optionally picks a `Price List`, and the system drafts a Sales Invoice with one line per booklet (each line links the configured `coupon_item` AND a booklet reference via a custom field on `Sales Invoice Item`). On invoice submit, each referenced booklet transitions `In Stock|In Custody → Sold` in a single transaction, with `customer`, `sold_on`, `sales_invoice` populated and `current_delivery_man` cleared. On invoice cancel, if no coupon from any referenced booklet has been `Consumed`, the sale is reversed (booklets return to `In Stock`); if any consumption has occurred on any referenced booklet, the entire cancel is rejected (all-or-nothing). Price List resolution follows a fixed order: workflow choice → customer default → `Purisol Settings.default_price_list`.

**Technical approach** (summarised from research.md):

- **Custom field on `Sales Invoice Item`** (`purisol_booklet`, Link → `Purisol Coupon Booklet`) authored as a Frappe fixture (`Custom Field` DocType, `dt = "Sales Invoice Item"`). This is the single integration point that lets a standard Sales Invoice carry the booklet→line mapping without introducing a parallel DocType. Only lines whose `item_code == Purisol Settings.coupon_item` AND whose `purisol_booklet` is set are treated as booklet lines; all other lines are ignored by Phase 3 logic (spec FR-020, edge case "Invoice line without a booklet reference"). The field is `read_only_depends_on` when the parent is submitted; see data-model.md.
- **Document Events wired via `hooks.py`** for `Sales Invoice`:
  - `validate`: invoice-level pre-submit checks (only active when at least one line has `purisol_booklet` set) — existence of referenced booklets, current status in `{In Stock, In Custody}`, no duplicate booklet on the same invoice, no unknown booklet link. Raises `frappe.ValidationError` on any failure so the entire save/submit is blocked before any side effect.
  - `on_submit`: performs the transactional booklet updates (status → `Sold`, populate `customer`, `sold_on = invoice.posting_date + posting_time`, `sales_invoice = invoice.name`, clear `current_delivery_man`). All updates run inside the request transaction; a failure anywhere raises and Frappe rolls the submit back atomically.
  - `on_cancel`: inspects `Purisol Coupon` child records of each referenced booklet; if any `status == "Consumed"` on any referenced booklet, raises `frappe.ValidationError` naming the offending booklet(s). Otherwise reverts every booklet's `status → In Stock` and clears `customer`, `sold_on`, `sales_invoice` in one transaction. `current_delivery_man` is **not** restored — reversal is strictly financial, not custodial (spec FR-032).
  - `on_trash` (defence-in-depth): refuse to delete a submitted invoice whose lines carry booklet references if any referenced booklet is currently `Sold` against this invoice — this is normally unreachable through the UI (submitted docs are not deletable) but the hook prevents backdoor deletes from bypassing the consumption check.
- **Booklet controller widening (`purisol_coupon_booklet.py`)**: the Phase-2 validate guard currently allows only `{In Stock, In Custody}` and the transitions `In Stock ↔ In Custody`. Phase 3 widens `_ALLOWED_STATUSES` to `{In Stock, In Custody, Sold}` and extends `_ALLOWED_TRANSITIONS` with `(In Stock, Sold)`, `(In Custody, Sold)`, `(Sold, In Stock)`. `Depleted` remains blocked (deferred to Phase 4). Direct form edits of `status`, `customer`, `sold_on`, `sales_invoice`, and `current_delivery_man` continue to be rejected via `read_only` in the JSON and via the existing controller guard; writes happen only through the Sales Invoice hooks using `db_set(..., notify=True)` (audit-friendly) or `frappe.get_doc(...).save(ignore_permissions=True)` when multiple fields must change atomically.
- **"Sell Booklets to Customer" workflow (UI)** — delivered as a whitelisted Python entry point `cx_purisol.api.sell_booklets.purisol_create_sales_invoice_for_booklets(customer, booklets, price_list=None)` plus a small JS helper that:
  - Adds a list-view action on `Purisol Coupon Booklet` ("Sell Selected to Customer") visible only to `Purisol Administrator`, enabled only when every selected row's `status ∈ {In Stock, In Custody}`.
  - Opens a `frappe.prompt` dialog (Customer required, optional Price List picker, read-only summary of selected booklet names) and calls the whitelisted function.
  - Redirects the desk to the created draft invoice (`frappe.set_route("Form", "Sales Invoice", name)`), matching spec FR-015 (no auto-submit).
- **Price List resolution** is centralised in a single helper `_resolve_price_list(customer, explicit)` used by the workflow entry point: returns `explicit` if given (non-empty); else `frappe.db.get_value("Customer", customer, "default_price_list")` if set; else `Purisol Settings.default_price_list`. Errors (none resolvable) short-circuit to `frappe.throw(_("Configure a default_price_list in Purisol Settings or pick one on this sale."))`. Line rates are populated by standard ERPNext — after setting `selling_price_list` on the draft, the controller calls `doc.set_missing_values()` / `doc.calculate_taxes_and_totals()` so the rate lookup is exactly the same code path as any normal invoice (no custom rate math).
- **Concurrency safety**: Two simultaneous submits that reference the same booklet are serialized by the booklet's optimistic lock (`modified` timestamp) — the second submit fails with `frappe.TimestampMismatchError`, which surfaces to the Administrator as a clear error and leaves the first submit's state intact. No explicit `FOR UPDATE` is needed because the validate+on_submit pair happens in the request transaction and the `modified`-based check is sufficient for the ≤10-booklet scale of a single sale.
- **Tests**: unit tests on the new booklet transition rules and on `_resolve_price_list`; integration tests for each user story (single-booklet sale, multi-booklet mixed-source sale, cancellation with no consumption, cancellation blocked by consumption, price-list resolution via all three paths, duplicate booklet on invoice, stale-draft rejection, and non-Administrator refusal).

## Technical Context

**Language/Version**: Python 3.10+ (Frappe server), JavaScript (Frappe client scripts).
**Primary Dependencies**: Frappe Framework 15.x, ERPNext 15.x (`Sales Invoice`, `Sales Invoice Item`, `Customer`, `Item`, `Price List`, `Employee`). No new third-party libraries.
**Storage**: Frappe DocTypes on MariaDB via `frappe.db` / `frappe.get_doc`; no raw SQL writes. The custom field on `Sales Invoice Item` is managed as a `Custom Field` fixture — no core ERPNext schema edits.
**Testing**: Frappe test framework (`frappe.tests.utils.FrappeTestCase`), invoked via `bench --site <test-site> run-tests --app cx_purisol`. ERPNext test fixtures (default Company, Cost Center, Income Account) are required; the test `setUp` seeds these via the existing Phase-1 `tests/fixtures.py` module (extended in this phase).
**Target Platform**: Linux server running Frappe Bench (gunicorn + RQ workers + MariaDB + Redis).
**Project Type**: Frappe custom app (`cx_purisol`) — extending the Phase 2 module with one custom field, one whitelisted API entry point, three Sales Invoice document-event hooks, and one widening of the existing booklet controller.
**Performance Goals**:
- Single-booklet sale end-to-end (workflow open → pick customer/booklet → submit invoice) in under 60 s total (spec SC-001, UI-dominated).
- Multi-booklet sale of up to 10 booklets in under 90 s total (spec SC-003).
- Server-side submit hook (validate + on_submit) for up to 10 booklets completes well under 2 s (≈ 20 field writes across status, customer, sold_on, sales_invoice, current_delivery_man); far below the 100-record enqueue threshold.
- Cancel hook (on_cancel) reads up to 10 × 20 = 200 coupon records for the consumption check and issues up to 10 × 4 = 40 field writes on reversal — still under 2 s and under the enqueue threshold.

**Constraints**:
- Frappe default gunicorn worker timeout is 120 s; the submit/cancel paths are well within.
- Atomic all-or-nothing submit and cancel (spec FR-024, FR-031, FR-032); no partial visibility of booklet state.
- Booklet status transitions permitted by this phase: `In Stock|In Custody → Sold` (submit) and `Sold → In Stock` (cancel when no coupon consumed). `Sold → Depleted` and direct `Sold → Sold` are blocked; `Depleted` remains untouched (Phase 4).
- Every user-facing string wrapped in `frappe._()` (constitution IX); error messages use named placeholders so Arabic translation is unambiguous.
- Only users with the `Purisol Administrator` role can launch the Sell Booklets workflow (spec FR-050). Standard ERPNext `Sales Manager` / `Accounts User` permissions govern the `Sales Invoice` itself.
- Financial side effects flow exclusively through the standard `Sales Invoice` (constitution II); no parallel ledger, no custom journal entries introduced.

**Scale/Scope**: Single shop, single administrator. Typical sale: 1–3 booklets; worst realistic case: 10 booklets. Expected steady-state: a few sales per day; a few hundred active booklets at any time. Multi-branch / multi-currency is out of scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution version: **1.0.0** (10 principles). The template has no pre-populated gates (known TODO in the Sync Impact Report, carried from Phase 1). The 10 principles below are evaluated explicitly for this phase.

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Naming Convention | **PASS** | No new custom DocTypes are introduced in this phase (intentional — see Principle II). The single schema artefact — a `Custom Field` on `Sales Invoice Item` named `purisol_booklet` — is not a DocType; the constitution's naming rule applies to `DocType.name`, not to field names. Field name is prefixed `purisol_` by convention to make the integration point visible in the Sales Invoice UI and in exports. |
| II | Leverage ERPNext Primitives | **PASS** | The sale itself is a plain `Sales Invoice`; pricing is a plain `Price List`; the buyer is a plain `Customer`; the sold good is a plain `Item` (non-stock, UOM `Booklet`). No `Purisol Sale`, no custom ledger, no custom price field. The only new schema element is one `Custom Field` on `Sales Invoice Item` that stores a link back to the booklet — justification: ERPNext's standard line reference fields (`item_code`, `serial_no`, `batch_no`) don't cleanly carry a link to a non-stock Purisol record, and using `remarks` would be a stringly-typed foreign key that breaks reports and navigation. |
| III | State Machine Enforcement | **PASS** | The booklet state machine is widened in-code (`_ALLOWED_STATUSES`, `_ALLOWED_TRANSITIONS`) to add exactly `In Stock → Sold`, `In Custody → Sold`, `Sold → In Stock`. Disallowed transitions (e.g. `Sold → In Custody`, `Sold → Sold`, any edit away from `Depleted`) raise `frappe.ValidationError` in `validate`. `Depleted` remains strictly terminal. Cancellation rejects with `frappe.ValidationError` when any referenced booklet has a consumed coupon — no silent overwrite of a `Sold` → `In Stock` reversal that would erase consumption context. |
| IV | Audit Trail by Default | **PASS** | `track_changes = 1` already set on `Purisol Coupon Booklet` (Phase 1). Every booklet field change triggered by an invoice submit/cancel writes to `tabVersion` with the current user and timestamp. The submittable record of truth for a sale is the **`Sales Invoice` itself** (which is `is_submittable = 1` by ERPNext core) — so the "submittable record per state change" rule is satisfied by ERPNext's core behaviour, without a parallel Purisol sale DocType. Per-coupon consumption metadata (`consumed_on`, `consumed_by_delivery_man`, `consumption_entry`) remains untouched by this phase — Phase 3 reads `Purisol Coupon.status` but never writes to coupons. |
| V | Error Handling Semantics | **PASS** | All rejections (missing coupon_item config, missing price list, missing customer, empty booklet list, duplicate booklet, broken booklet link, wrong-status booklet, cancel blocked by consumption, non-Administrator launch) use `frappe.throw(_(...))` — blocking errors only. Phase 3 produces **no** warning discrepancies — sales rules are unambiguous; any ambiguity belongs to Phase 4/5. Silent success is impossible: every branch either persists the atomic state change or throws. |
| VI | Role Model | **PASS** | Only `Purisol Administrator` can invoke the whitelisted `purisol_create_sales_invoice_for_booklets` entry point — enforced by `@frappe.whitelist()` + `frappe.only_for("Purisol Administrator")` inside the function. The list-view action is hidden for users without the role (`frappe.user.has_role` guard in JS). Standard ERPNext roles (`Sales Manager`, `Accounts User`, etc.) continue to govern the Sales Invoice itself; no new custom role is introduced. |
| VII | Notification Channel | **PASS** | Phase 3 emits **no** notifications. Customer low-stock alerts, warehouse low-stock alerts, and any other event-driven messaging are deferred to a later phase. The submit/cancel hooks do **not** call any notification code directly, preserving the dispatcher seam for Phase 5/6: the future notification layer can subscribe to `Sales Invoice` events (or a Purisol-internal event after the booklet update commits) without rewriting Phase 3 code. |
| VIII | Background Jobs | **PASS** | A single sale updates at most 10 booklets (≈ 40 field writes) and reads at most 200 coupon records for the cancel-consumption check — both well below the 100-record synchronous threshold. Synchronous processing keeps atomicity simple and matches the user's expectation (they are reviewing a draft invoice). If a future phase introduces bulk-import sales > ~25 booklets per invoice, the on_submit/on_cancel hooks can be re-entered as an enqueued job without changing validation/state-transition logic. |
| IX | Localization | **PASS** | Every form label, dialog caption, workflow title, validation message, and dashboard / list-view action string is wrapped in `frappe._()`. Error messages use named placeholders (e.g., `_("Booklet {0} cannot be sold — current status: {1}").format(name, status)`) so Arabic word order is preserved. The `Custom Field` fixture includes the `label` as the translation key; Arabic translations land in `cx_purisol/translations/ar.csv` (existing file from Phase 1). |
| X | Testing Discipline | **PASS** | Unit tests for the widened booklet validate, price-list resolution, and the list-view action's enablement logic live under `cx_purisol/cx_purisol/cx_purisol/doctype/purisol_coupon_booklet/test_purisol_coupon_booklet.py` (widened) and a new `cx_purisol/cx_purisol/cx_purisol/api/test_sell_booklets.py`. Integration tests — one per user story plus each edge case — live under `cx_purisol/cx_purisol/cx_purisol/tests/test_sales_flows.py`. Every test uses `FrappeTestCase`; ERPNext fixtures (Company, warehouse, tax templates, default Item) are seeded via `tests/fixtures.py`. |

**No violations.** Complexity Tracking table is empty.

## Project Structure

### Documentation (this feature)

```text
specs/003-sales-integration/
├── plan.md              # This file (/speckit.plan command output)
├── spec.md              # Feature specification (already written)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/
│   └── sales-integration.md # Phase 1: behavioural contract for workflow + submit/cancel hooks
├── checklists/
│   └── requirements.md  # Spec-quality checklist (already written)
└── tasks.md             # Phase 2 output (/speckit.tasks command — NOT created here)
```

### Source Code (repository root)

```text
cx_purisol/                                         # Git repo root; Frappe app package
├── cx_purisol/                                     # Python package root
│   ├── hooks.py                                    # *** MODIFIED *** — register Sales Invoice doc_events + Custom Field fixture
│   ├── modules.txt                                 # Unchanged
│   ├── patches.txt                                 # *** MODIFIED *** — one-time Phase-3 validate widening
│   ├── patches/
│   │   └── v0_3_0/
│   │       ├── __init__.py
│   │       └── widen_booklet_validate_for_sale.py  # *** NEW *** — no-op patch on fresh installs
│   └── cx_purisol/                                 # Module folder ("Cx Purisol")
│       ├── doctype/
│       │   ├── purisol_coupon_booklet/             # *** MODIFIED ***
│       │   │   ├── purisol_coupon_booklet.py       # Widen: permit In Stock|In Custody → Sold, Sold → In Stock
│       │   │   └── test_purisol_coupon_booklet.py  # New: Phase-3 transition tests
│       │   └── (existing Phase 1 & 2 DocTypes unchanged)
│       ├── api/
│       │   ├── __init__.py
│       │   ├── sell_booklets.py                    # *** NEW *** — whitelisted purisol_create_sales_invoice_for_booklets
│       │   ├── test_sell_booklets.py               # *** NEW *** — unit tests (price list resolution, validation)
│       │   └── (existing Phase 1 booklet_generation.py unchanged)
│       ├── sales_invoice/                          # *** NEW *** — Phase 3 hook module
│       │   ├── __init__.py
│       │   └── sales_invoice_hooks.py              # validate, on_submit, on_cancel, on_trash
│       ├── public/js/
│       │   └── purisol_coupon_booklet_list.js      # *** NEW *** — list-view "Sell Selected" action
│       ├── report/                                 # From Phase 2 — unchanged in this phase
│       ├── tests/
│       │   ├── fixtures.py                         # *** MODIFIED *** — seed coupon Item, price lists, customer
│       │   ├── test_sales_flows.py                 # *** NEW *** — integration tests (Stories 1–4 + edge cases)
│       │   └── (existing Phase 1 & 2 tests unchanged)
│       └── fixtures/
│           ├── custom_field.json                   # *** NEW *** — Sales Invoice Item.purisol_booklet
│           └── (existing role.json, etc. unchanged)
└── specs/003-sales-integration/                    # This plan
```

**Structure Decision**: Standard Frappe custom-app layout, consistent with Phases 1 and 2. No new DocType is added in this phase — the spec explicitly forbids a parallel sale DocType (constitution II) and the existing `Purisol Coupon Booklet` already has every field Phase 3 needs (`customer`, `sold_on`, `sales_invoice`, `current_delivery_man`). The single schema artefact is a `Custom Field` fixture, which sits under `fixtures/` because that's where Frappe expects `Custom Field` fixtures registered via `hooks.fixtures`. Sales-Invoice document-event hooks live in a dedicated `sales_invoice/` sub-package so the booklet-specific integration logic is discoverable without cluttering the booklet's own controller — this mirrors the Phase 2 `report/` sub-package pattern. The whitelisted API entry point joins the existing `api/` sub-package (consistent with Phase 1's `booklet_generation.py`). Tests split the existing convention: DocType-local tests in `doctype/.../test_*.py`, API-local tests co-located with the API module, integration tests in `tests/test_sales_flows.py`. The patches file gains one entry for the booklet controller widening — a no-op on fresh installs, required only on upgraded sites to clear any cached validation state (exactly the pattern used in Phase 2).

## Complexity Tracking

> No constitutional violations; table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
