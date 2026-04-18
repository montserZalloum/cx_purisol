# Feature Specification: Core Data Model — Booklets & Coupons

**Feature Branch**: `001-core-data-model`
**Created**: 2026-04-18
**Status**: Draft
**Input**: User description: "Phase 1 — Core Data Model (Booklets & Coupons): establish foundational entities (Purisol Settings singleton, Purisol Coupon Booklet, Purisol Coupon), booklet generation action creating N booklets and N×20 coupons with strict sequential numbering, and a background job for batches larger than 20 booklets. Custody, sales, consumption, discrepancies, notifications, and reports are deferred."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generate a Batch of Booklets (Priority: P1)

The Purisol Administrator needs to populate the system with fresh booklet and coupon inventory before any downstream operation (custody, sale, consumption) can happen. They open a "Generate Booklets" action, enter a quantity (and an optional batch identifier), and the system produces that many booklets, each with its 20 coupons, all ready to be managed.

**Why this priority**: This is the foundational act of the entire system. Without booklet and coupon records, no other Purisol workflow can run. It delivers immediate demonstrable value: the Administrator can see the resulting inventory in the system and verify numbering correctness before any later phase is built.

**Independent Test**: Can be fully tested by invoking the Generate Booklets action with a small quantity (e.g., 5) and confirming that 5 booklet records exist (`WP-00001`…`WP-00005`) with 100 coupon records (`CP-00001`…`CP-00100`) correctly linked. Large batches (e.g., 50) verify the background-job path end-to-end.

**Acceptance Scenarios**:

1. **Given** an empty system, **When** the Administrator generates 1 booklet, **Then** exactly one booklet `WP-00001` is created with status `In Stock` and coupons `CP-00001` through `CP-00020` all linked to it with status `Available`.
2. **Given** the system already contains booklet `WP-00001` (with coupons `CP-00001`–`CP-00020`), **When** the Administrator generates 1 more booklet, **Then** booklet `WP-00002` is created and contains coupons `CP-00021` through `CP-00040`.
3. **Given** an empty system, **When** the Administrator generates 50 booklets in one action, **Then** exactly 50 booklet records and exactly 1,000 coupon records are created; booklet `WP-00002` contains `CP-00021`–`CP-00040`; booklet `WP-00050` contains `CP-00981`–`CP-01000`.
4. **Given** a batch identifier is supplied, **When** generation completes, **Then** every booklet produced in that run carries that batch identifier so it can be filtered in lists and reports.
5. **Given** a generation request exceeds 20 booklets, **When** the Administrator submits it, **Then** the action is handed off to a background job and the Administrator sees progress feedback until completion, rather than the UI hanging or timing out.

---

### User Story 2 - Configure System Settings (Priority: P2)

Before or during the first generation, the Administrator configures system-wide defaults (thresholds, default references) in a single Purisol Settings record. This record is a singleton — there is only ever one — and every future feature reads from it.

**Why this priority**: Settings are referenced by generation and by every later phase. They are P2 because a first generation can proceed with default values, but the record must exist and be editable from day one so later phases never have to introduce it retroactively.

**Independent Test**: Can be fully tested by opening the Purisol Settings page, confirming it behaves as a singleton (no "new" button, only one record ever), changing a default value, saving, and reopening to confirm the change persisted.

**Acceptance Scenarios**:

1. **Given** a fresh install, **When** the Administrator opens Purisol Settings, **Then** a single editable record exists with sensible defaults for every configuration field.
2. **Given** the Administrator changes a threshold value and saves, **When** they reopen the record, **Then** the new value is displayed.
3. **Given** a non-administrator attempts to access settings, **When** they navigate to the page, **Then** they are denied access.

---

### User Story 3 - Inspect Individual Booklet and Coupon Records (Priority: P3)

After generation, the Administrator can browse the list of booklets and the list of coupons, open any single record, and read its attributes: booklet number, status, first and last coupon, total/consumed/remaining counts, batch identifier, notes. For a coupon: coupon number, parent booklet, page number (1–20), and status.

**Why this priority**: This is read-only observability over the data produced by Story 1. It is P3 because it follows automatically from list-view/form-view conventions once the DocTypes exist, but it is listed explicitly so the spec enumerates the fields that must be user-visible and the immutable ones.

**Independent Test**: Can be fully tested by opening any generated booklet and confirming all listed fields render, read-only fields cannot be edited, and the coupon list filtered to that booklet shows exactly 20 coupons with page numbers 1–20.

**Acceptance Scenarios**:

1. **Given** booklet `WP-00003` exists, **When** the Administrator opens it, **Then** the form shows `first_coupon = CP-00041`, `last_coupon = CP-00060`, `total_coupons = 20`, `consumed_count = 0`, `remaining_count = 20`, and these computed fields are not user-editable.
2. **Given** a coupon record is opened, **When** the form loads, **Then** `coupon_number`, `booklet`, and `page_number` are read-only and correct (page number 1–20 based on position in the booklet).
3. **Given** several batches have been generated, **When** the Administrator filters the booklet list by a `batch_id`, **Then** only booklets from that batch are shown.

---

### Edge Cases

- **Quantity boundary — zero or negative**: The system must reject a request to generate 0 or a negative number of booklets with a clear message; no records are created.
- **Quantity boundary — upper limit**: A very large request (e.g., 1,000 booklets / 20,000 coupons) must still complete via the background job without the worker timing out, with progress visible throughout.
- **Concurrent generation**: If two generation requests are made in quick succession (e.g., the Administrator double-clicks, or two sessions trigger at once), the system must still produce strictly sequential, non-overlapping, non-duplicate booklet and coupon numbers across both runs.
- **Background job failure mid-run**: If a large batch fails partway through (e.g., database outage after 30 of 50 booklets), the system must not leave the numbering in an inconsistent state; on retry, numbering resumes from the correct next value with no gaps and no duplicates.
- **Schema fields reserved for later phases**: Custody and customer fields exist on the booklet schema from day one but are unused and unpopulated. Browsing a booklet in Phase 1 must not show these as required or malfunction because they are empty.
- **Settings record deletion**: The Purisol Settings singleton must not be deletable; only editable.
- **Modifying computed fields**: Any attempt (API or UI) to directly edit computed fields on a booklet (first/last coupon, total/consumed/remaining counts) or immutable fields on a coupon (page number, parent booklet) must be rejected.

## Requirements *(mandatory)*

### Functional Requirements

#### Settings

- **FR-001**: The system MUST provide a singleton `Purisol Settings` record — one record only, always present, never deletable, and never duplicable (any attempt to create a second `Purisol Settings` record MUST be rejected) — holding system-wide configuration values referenced by all future phases.
- **FR-002**: `Purisol Settings` MUST include, at minimum: a reference to the Item used for coupon-booklet sales, a default Price List, a customer low-stock threshold (default 3), a warehouse low-stock threshold (default 5), an employee-liability account, a discrepancy-offset account, a default cash account, and a toggle for consumption warnings. Fields relevant only to later phases MAY remain unset in Phase 1 but MUST exist in the schema.
- **FR-003**: Only users with the `Purisol Administrator` role MUST be able to read or edit `Purisol Settings`.

#### Booklet and Coupon Entities

- **FR-004**: The system MUST provide a `Purisol Coupon Booklet` record representing a single physical booklet of 20 coupons, with all fields required for the full MVP present in the schema from day one (including fields used only in later phases — custody holder, customer, sale references, depletion timestamp).
- **FR-005**: The system MUST provide a `Purisol Coupon` record representing a single coupon within a booklet, with all fields required for the full MVP present in the schema from day one (including fields used only in later phases — consumption timestamp, consuming delivery man, consumption entry reference).
- **FR-006**: Every booklet record MUST have a system-generated identifier of the form `WP-NNNNN`, strictly sequential and zero-padded to five digits, starting at `WP-00001`.
- **FR-007**: Every coupon record MUST have a system-generated identifier of the form `CP-NNNNN`, strictly sequential system-wide (not reset per booklet), zero-padded to five digits, starting at `CP-00001`.
- **FR-008**: For booklet `WP-N`, its 20 coupons MUST bear numbers `CP-((N-1)*20 + 1)` through `CP-(N*20)` inclusive. This invariant MUST hold across all booklets and all generations.
- **FR-009**: Each coupon MUST store its page number within the booklet (integer 1–20, corresponding to its position). Page number, parent booklet link, and coupon number MUST be immutable after creation.
- **FR-010**: Each booklet MUST expose computed, read-only fields for its first coupon number, last coupon number, total coupon count (always 20), consumed count, and remaining count. In Phase 1 consumed count is always 0 and remaining count is always 20; the fields MUST still be present and displayed.
- **FR-011**: Every newly generated booklet MUST have status `In Stock`; every newly generated coupon MUST have status `Available`.
- **FR-012**: Booklet status MUST be constrained to the set `In Stock`, `In Custody`, `Sold`, `Depleted`. Coupon status MUST be constrained to the set `Available`, `Consumed`. No other values are permitted. (Transitions beyond `In Stock`/`Available` are out of scope for Phase 1 but the value domain is fixed now.)
- **FR-013**: Both booklets and coupons MUST have change tracking enabled so every edit is captured in a per-record audit trail.

#### Booklet Generation

- **FR-014**: The system MUST expose a "Generate Booklets" action to users with the `Purisol Administrator` role, accepting a quantity (positive integer, required) and an optional batch identifier string.
- **FR-015**: The system MUST reject generation requests with a non-positive quantity (0 or negative) with a clear, user-facing error, and MUST create no records in that case.
- **FR-016**: On a valid generation of quantity `N`, the system MUST create exactly `N` booklet records and exactly `N × 20` coupon records, with numbering continuing from the highest existing booklet and coupon numbers (not from 1, if prior booklets exist).
- **FR-017**: The generation action MUST be atomic per logical batch: on failure mid-run, the system MUST NOT leave dangling booklets without their 20 coupons, and MUST NOT skip or duplicate numbers on a subsequent successful run.
- **FR-018**: When the requested quantity exceeds 20 booklets (i.e., more than 400 coupon records would be created), the generation MUST run as a background job rather than in the request thread, and the Administrator MUST receive progress feedback (updates as the job advances) and a final completion/failure outcome.
- **FR-019**: When the requested quantity is 20 or fewer, the generation MAY complete synchronously within the request.
- **FR-019a**: Every successful generation — whether synchronous or background — MUST produce the same summary on completion, containing at minimum: the first generated booklet's identifier, the last generated booklet's identifier, and the total count of coupons created.
- **FR-020**: When a batch identifier is provided, every booklet produced in that run MUST carry that identifier in its `batch_id` field so all booklets from the run are filterable as a group.
- **FR-021**: Concurrent generation requests MUST NOT produce duplicate or out-of-order booklet or coupon numbers; the numbering authority MUST be a single serialized source.

### Key Entities *(include if feature involves data)*

- **Purisol Settings**: Singleton configuration record. Holds references to the coupon Item, default Price List, thresholds (customer low-stock, warehouse low-stock), accounting references (employee-liability, discrepancy-offset, default cash), and feature toggles. Read/edit restricted to Purisol Administrator.
- **Purisol Coupon Booklet**: The master record for a single physical booklet of 20 coupons. Identified by `WP-NNNNN`. Holds status, computed first/last coupon numbers, total/consumed/remaining counts, optional batch identifier, optional free-text notes. Schema also includes custody, customer, sale, and depletion fields for later phases, which remain unpopulated in Phase 1.
- **Purisol Coupon**: A single coupon. Identified by `CP-NNNNN`. Holds parent booklet link, page number (1–20), and status. Schema also includes consumption metadata fields (timestamp, delivery man, consumption entry) for later phases, which remain unpopulated in Phase 1.

### Relationships

- A `Purisol Coupon Booklet` has exactly 20 `Purisol Coupon` records.
- Each `Purisol Coupon` belongs to exactly one `Purisol Coupon Booklet`.
- Coupon numbers are deterministic given the booklet number: `WP-N` ↔ `CP-((N-1)*20+1)` … `CP-(N*20)`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Generating 50 booklets produces exactly 50 booklet records and exactly 1,000 coupon records, with no missing, duplicate, or out-of-order numbers.
- **SC-002**: The numbering invariant holds across any generation history: for every booklet `WP-N` in the system, its coupons are exactly `CP-((N-1)*20+1)` through `CP-(N*20)`, verifiable by inspection of any booklet.
- **SC-003**: A generation request of 20 or fewer booklets completes and returns a summary to the Administrator in under 5 seconds under normal load.
- **SC-004**: A generation request exceeding 20 booklets does not hold the Administrator's UI thread — the request returns control within 2 seconds with progress updates visible until completion.
- **SC-005**: 100% of newly generated booklets start with status `In Stock` and 100% of newly generated coupons start with status `Available`, verifiable by post-generation query.
- **SC-006**: When a background generation is interrupted (simulated failure mid-run) and retried, the final numbering contains no gaps and no duplicates compared to a single successful run of the same total quantity.
- **SC-007**: Two generation requests issued within 1 second of each other produce contiguous, non-overlapping numbering (combined output equals a single request for the same total quantity).
- **SC-008**: The Purisol Settings singleton is accessible to the Administrator with every required field present and editable, and is not accessible to users without the `Purisol Administrator` role.

## Assumptions

- **Scope deferral**: Custody, sales, consumption, discrepancies, notifications, reports, and any delivery-man workflows are explicitly out of scope for this phase. Fields on booklets and coupons that relate to those phases exist in the schema (to avoid a later migration) but are unused and unvalidated in Phase 1.
- **Single-admin model**: Phase 1 assumes the MVP role model — one custom role, `Purisol Administrator`. No delivery-man or accountant roles are introduced in this phase.
- **Booklet size is fixed at 20**: Configurable booklet sizes are deferred to future phases. All Phase-1 logic treats "20 coupons per booklet" as a constant invariant.
- **Numbering never resets**: Neither booklet nor coupon numbering resets on a new year, a new batch, or any other boundary. The sequence is strictly monotonic for the lifetime of the installation.
- **Concurrency model**: A single serialized source (the database autoincrement / naming-series authority) is assumed to be the source of truth for "next number". The spec does not mandate a specific locking strategy — only that the observable numbering is contiguous and unique under concurrent use.
- **Background-job threshold**: The threshold "> 20 booklets" is taken directly from the PRD (Section 15.1 rationale: Frappe's default 120s worker timeout). This phase does not alter the threshold.
- **Progress feedback mechanism**: Progress feedback is assumed to be surfaced through the same in-app channel the rest of the MVP uses (bell notifications / real-time updates); no external notification channel is introduced here.
- **Settings defaults at install time**: Threshold defaults (`customer_low_stock_threshold = 3`, `warehouse_low_stock_threshold = 5`, `enable_consumption_warnings = true`) are assumed to be acceptable out-of-the-box so that a fresh install can proceed to generation without manual setup. Accounting-related settings may remain empty in Phase 1 since no accounting documents are created yet.
- **Unit-testing target**: "Unit tests for numbering logic and generation" in the user input is interpreted as: pure tests for the `WP-N` → coupon-range mapping, and tests that a generation of quantity N produces N and N×20 records with correct numbering under both synchronous and background-job paths.
