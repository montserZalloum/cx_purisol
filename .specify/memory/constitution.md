<!--
Sync Impact Report
==================
Version change: (initial) → 1.0.0
Rationale: Initial ratification — establishing the full set of non-negotiable
principles for the Purisol Water Coupon Management System (ERPNext custom
Frappe app).

Modified principles:
  - (none — initial adoption)

Added sections:
  - Core Principles (10 principles: Naming Convention, Leverage ERPNext
    Primitives, State Machine Enforcement, Audit Trail by Default, Error
    Handling Semantics, Role Model, Notification Channel, Background Jobs for
    Long Operations, Localization, Testing Discipline)
  - Additional Constraints & Platform Standards
  - Development Workflow & Quality Gates
  - Governance

Removed sections:
  - (none — initial adoption)

Templates requiring updates:
  - ✅ .specify/memory/constitution.md (created)
  - ⚠ .specify/templates/plan-template.md — "Constitution Check" section
    (line 30-34) is still a placeholder. It SHOULD be updated by the next
    plan-template maintainer to enumerate the 10 gates below. No change made
    in this commit to avoid scope creep; flagged as follow-up.
  - ✅ .specify/templates/spec-template.md — no change required; spec-level
    concerns (user stories, FRs, success criteria) remain orthogonal to
    constitutional gates which are enforced at plan/implement time.
  - ✅ .specify/templates/tasks-template.md — no change required; the
    tests-optional clause is compatible with Principle X (tests are mandatory
    for this project and will be explicitly requested in every spec).
  - ✅ .specify/templates/checklist-template.md — no change required.
  - ✅ .specify/templates/agent-file-template.md — no change required.

Follow-up TODOs:
  - TODO(plan-template): add explicit Constitution Check gates enumerating
    the 10 principles, so /speckit.plan validates each one.
-->

# Purisol Water Coupon Management System Constitution

## Core Principles

### I. Naming Convention

Every custom DocType created by this app MUST be named with the prefix
`"Purisol "` (capital P, lowercase remainder, followed by a single trailing
space) before the descriptive name. Example: `"Purisol Coupon Booklet"`,
`"Purisol Custody Entry"`, `"Purisol Discrepancy"`.

**Rationale**: Prevents name collisions with ERPNext core DocTypes, makes
custom records immediately recognizable in the UI (list views, link fields,
reports), and gives the app a consistent visual identity. A Purisol-prefixed
DocType that does not follow this convention is a constitutional violation
and MUST be renamed before release.

### II. Leverage ERPNext Primitives (Do Not Reinvent)

The app MUST NOT create a custom DocType that duplicates an ERPNext core
concept. Specifically:

- Customers → `Customer` (never a `Purisol Customer`).
- Delivery men → `Employee` (never a `Purisol Delivery Man`).
- Sale of a booklet → `Sales Invoice` (never a custom sale DocType).
- Financial consequences of discrepancies → `Journal Entry` or
  `Payment Entry` (never custom ledgers).
- Pricing → `Price List` + `Pricing Rule` (never a custom price field on
  a Purisol DocType).

Custom Purisol DocTypes are only justified when they represent concepts
ERPNext does not model (coupons, booklets, custody transfers, consumption,
discrepancies). Any new custom DocType MUST include a one-sentence written
justification explaining why no ERPNext primitive fits.

**Rationale**: Duplicating ERPNext concepts fragments reporting, breaks
accounting integration, and doubles the maintenance burden. Leveraging
primitives keeps the app upgrade-safe.

### III. State Machine Enforcement

Every stateful DocType MUST:

1. Document its allowed states and the allowed transitions between them
   (in a module-level comment or a dedicated state-transition table).
2. Reject disallowed transitions by raising `frappe.ValidationError` —
   never by silently ignoring the change or coercing the value.
3. Treat terminal states (e.g. `Depleted`, `Cancelled`, `Closed`) as
   strictly terminal. Once entered, the DocType MUST NOT transition out,
   even by a System Manager. Reopening requires a new record.

**Rationale**: Silent state drift is the single highest source of audit
failures in coupon and custody systems. Explicit rejection + terminal
finality makes the ledger defensible.

### IV. Audit Trail by Default

Every custom Purisol DocType MUST have `track_changes = 1`.

Every state-changing action on domain objects (booklet custody, coupon
consumption, discrepancy resolution) MUST be represented by a submittable
(`is_submittable = 1`) record — e.g. `Purisol Custody Entry`, `Purisol
Consumption Entry`, `Purisol Discrepancy`. A field on the parent MUST
NOT be updated silently to reflect a state change; the submittable record
is the source of truth and the field is a cache derived from it.

Individual coupon records MUST persist consumption metadata on the coupon
itself: `consumed_on`, `consumed_by` (Employee link), and
`consumption_entry` (link to the submittable), even when aggregate counts
on the booklet drift from reality.

**Rationale**: Aggregates lie; per-coupon metadata does not. The
submittable pattern gives every state change a timestamp, an actor, and
a cancellation path that preserves history.

### V. Error Handling Semantics

Errors MUST be classified into exactly two categories:

- **Blocking errors** — raised via `frappe.ValidationError` (or
  `frappe.throw`) when data is logically impossible: duplicate coupon
  serial, already-consumed coupon, invalid state transition, negative
  count, etc. These MUST prevent save/submit.
- **Warning discrepancies** — raised when data suggests wrongdoing but
  has plausible innocent explanations: missing coupons in a sequence,
  unassigned booklet turned in, count mismatch on settlement. These
  MUST allow the submit to proceed AND MUST create a
  `Purisol Discrepancy` record for human investigation.

A third category (silent success, log-and-continue) is FORBIDDEN for
domain rules.

**Rationale**: Hard-failing on ambiguous evidence punishes honest
mistakes; allowing ambiguous evidence through silently enables fraud.
The two-tier model gives auditors a clean signal.

### VI. Role Model (MVP Scope)

MVP defines exactly one custom role: `Purisol Administrator`. Delivery
men (Employees) MUST have no system access in MVP. Every operation
performed "on behalf of" a delivery man — receiving a booklet, handing
in consumed coupons, settling cash — MUST be performed by a user
holding the `Purisol Administrator` role, with the Employee recorded
as the subject of the operation.

Adding additional roles (e.g. `Purisol Delivery`) requires a
constitution amendment.

**Rationale**: Minimizing the MVP role surface removes an entire class
of permission/ACL bugs and matches the real-world workflow (delivery
staff report to an administrator who records on their behalf).

### VII. Notification Channel

MVP notifications MUST use ERPNext bell notifications (the built-in
`Notification` DocType / `frappe.publish_realtime` path) only.

Notification-triggering code MUST be structured so that additional
channels (email, WhatsApp, SMS) can be added by registering a new
channel handler — NOT by editing the trigger logic. Concretely: triggers
emit an abstract notification event; a dispatcher routes the event to
registered channels. In MVP only the bell-notification channel is
registered.

**Rationale**: Channel diversity is a near-certain post-MVP requirement
in the Saudi/Arabic market. Designing the seam now costs little;
retrofitting it later is expensive.

### VIII. Background Jobs for Long Operations

Any operation that creates, updates, or deletes more than 100 records in
a single logical unit MUST run via `frappe.enqueue` rather than
synchronously in the request thread. The canonical example: generating
20 booklets (400+ coupon records) MUST be a background job.

Synchronous long operations are FORBIDDEN because they block the Frappe
web worker, cause gateway timeouts, and produce partial writes on
failure. The enqueued job MUST report progress via `frappe.publish_realtime`
and MUST be idempotent (safe to retry).

**Rationale**: Frappe's default gunicorn timeout is 120s; a single
long-running request can saturate workers. Enqueued jobs also give us
a natural retry and observability surface.

### IX. Localization

All user-facing strings (labels, messages, error text, print formats,
email templates, notification bodies) MUST be wrapped in `frappe._()` so
they can be translated.

Arabic (`ar`) and English (`en`) MUST both render correctly. Code MUST
NOT make hardcoded left-to-right assumptions: no LTR-only string
concatenation for user display, no hardcoded text alignment in print
formats, no assumptions about name ordering. Numeric and date formatting
MUST use Frappe's locale-aware helpers.

**Rationale**: The deployment market is bilingual; retrofitting
translation wrappers across a finished codebase is painful and
error-prone. The cost is trivial if done from day one.

### X. Testing Discipline

Every phase (every shipped slice of functionality) MUST include:

- **Unit tests** for DocType validations, state-transition rules, and
  error classification (blocking vs. warning).
- **Integration tests** for end-to-end domain flows — at minimum
  `generate booklets → assign to delivery employee → sell to customer
  via Sales Invoice → consume coupons → settle`.

All tests MUST use the Frappe test framework
(`frappe.tests.utils.FrappeTestCase`). A phase is not "done" until its
tests pass on a clean database. Pull requests that reduce test coverage
on touched code require explicit written justification.

**Rationale**: Coupon/custody systems have a long tail of edge cases
(split booklets, cancelled custody, partial consumption, cancelled sales
invoices). A robust test suite is the only defensible way to refactor
such a system over time.

## Additional Constraints & Platform Standards

- **Platform**: ERPNext (Frappe framework). Custom app name: `cx_purisol`.
- **Language**: Python (Frappe server-side), JavaScript (Frappe client
  scripts), Jinja (print formats).
- **Data**: All persistent state lives in Frappe DocTypes. No
  shadow tables, no direct SQL writes outside `frappe.db` helpers.
- **Accounting integration**: Financial side effects flow through
  ERPNext's standard accounting DocTypes (`Sales Invoice`,
  `Journal Entry`, `Payment Entry`). The app MUST NOT maintain a
  parallel ledger.
- **Migrations**: Schema changes ship as Frappe fixtures and/or
  `patches.txt` entries — never as manual production-DB edits.
- **Security**: Role-based permissions are defined on each DocType via
  Permission Rules; permission logic MUST NOT be duplicated in Python
  except for row-level restrictions that the permission model cannot
  express.

## Development Workflow & Quality Gates

- **Spec → Plan → Tasks → Implement**: Every feature follows the
  speckit flow. No implementation PR is opened without a merged spec
  and plan.
- **Constitution Check (plan phase)**: Each `/speckit.plan` run MUST
  evaluate the 10 principles above and document either conformance or
  a justified exception in the plan's Complexity Tracking table.
  Unjustified violations are blocking.
- **Code review**: Every PR is reviewed against this constitution.
  Reviewers MUST cite the principle number when raising constitutional
  objections (e.g. "Principle IV: this updates a count field without
  creating a Consumption Entry").
- **Testing gate**: CI MUST run `bench --site <test-site> run-tests
  --app cx_purisol` on every PR. Failing tests block merge.
- **Migration safety**: Any PR that adds, renames, or removes a
  DocType field MUST include the corresponding `patches.txt` entry
  and MUST be tested against a snapshot of production-shaped data.

## Governance

This constitution supersedes informal conventions, prior verbal
agreements, and individual preferences. In any conflict between this
document and other documentation (READMEs, comments, chat decisions),
this document wins until it is amended.

**Amendment procedure**:

1. Proposer opens a PR that modifies `.specify/memory/constitution.md`
   and includes an updated Sync Impact Report at the top.
2. The PR description MUST state the version bump (MAJOR / MINOR /
   PATCH) and the rationale.
3. The PR MUST identify every downstream artifact affected (plan
   template, spec template, tasks template, agent guidance files,
   quickstart docs) and either update them in the same PR or list them
   as follow-up TODOs.
4. Merge requires approval from the project owner.

**Versioning policy** (semantic):

- **MAJOR**: Backward-incompatible governance or principle removal/
  redefinition (e.g. removing a principle, reversing its meaning).
- **MINOR**: New principle or section added; materially expanded
  guidance that changes what code must do.
- **PATCH**: Clarifications, wording fixes, typo corrections, rationale
  expansion — no change to what code must do.

**Compliance review**: At the end of each major phase (MVP, Phase 2,
etc.), the project owner performs a constitution compliance audit:
sample 3–5 recently-merged PRs and verify each of the 10 principles
holds. Violations discovered after merge are tracked as remediation
tasks, not retroactively reverted.

**Version**: 1.0.0 | **Ratified**: 2026-04-18 | **Last Amended**: 2026-04-18
