# Feature Specification: Custody Management

**Feature Branch**: `002-custody-management`
**Created**: 2026-04-18
**Status**: Draft
**Input**: User description: "Phase 2 — Custody Management: track which delivery man holds which booklet, with full history. Introduce the Purisol Custody Entry submittable DocType (with its child table) covering three entry types — Assign (shop → delivery man), Transfer (delivery man → delivery man, including partial subsets), and Return (delivery man → shop). Enforce state transitions between `In Stock` and `In Custody`, keep `current_delivery_man` on each booklet in sync, reject invalid source states with clear errors, and provide a Current Custody by Delivery Man list view. Sales, consumption, and discrepancies are deferred to later phases."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Assign Booklets from Shop to a Delivery Man (Priority: P1)

The Purisol Administrator picks a delivery man who is heading out on their route and a set of booklets currently sitting in the shop (status `In Stock`). They record a single Custody Entry of type `Assign` listing those booklets and the destination delivery man. On submit, each listed booklet transitions from `In Stock` to `In Custody`, and its `current_delivery_man` is set to the chosen delivery man. The shop always knows, from that moment onward, who carries each booklet.

**Why this priority**: Assignment is the starting point of every route: without handing booklets to a delivery man, none of the downstream flows (sale, consumption) can ever occur. It is also the single most frequent custody operation and is the logical precondition for Transfer and Return (both of which require booklets to already be `In Custody`). Shipping Assign alone is a complete, demonstrable slice of value: the shop can already track who carries what, even if no reverse flow exists yet.

**Independent Test**: Can be fully tested in isolation by seeding a few `In Stock` booklets (Phase 1 output) and one `Employee` record, opening a new Custody Entry of type `Assign`, selecting the delivery man, adding the booklets, and submitting. Verify that each booklet's status is now `In Custody` with the correct `current_delivery_man`, that the Custody Entry is locked (submitted), and that the audit history of each booklet shows this entry.

**Acceptance Scenarios**:

1. **Given** booklets `WP-00001` and `WP-00002` are both `In Stock` and delivery man Ali exists, **When** the Administrator submits a Custody Entry of type `Assign` to Ali listing those two booklets, **Then** both booklets move to status `In Custody` with `current_delivery_man = Ali`, and the Custody Entry is marked submitted and immutable.
2. **Given** a Custody Entry of type `Assign` includes a booklet that is currently `In Custody` (not `In Stock`), **When** the Administrator tries to submit, **Then** the submission is rejected with a clear error identifying the offending booklet and its actual status, and no booklet is modified.
3. **Given** a Custody Entry of type `Assign` is submitted with no `to_delivery_man` selected, **When** the Administrator tries to submit, **Then** the submission is rejected with a clear error naming the missing field.
4. **Given** a Custody Entry of type `Assign` lists multiple booklets and one of them is in an invalid source state, **When** submit is attempted, **Then** no booklet in the entry is modified — the update is all-or-nothing.
5. **Given** a Custody Entry is submitted successfully, **When** the Administrator opens the history of any listed booklet, **Then** the change is attributable to this Custody Entry (entry reference, timestamp, who created it).

---

### User Story 2 - Return Booklets from a Delivery Man to the Shop (Priority: P2)

At the end of a route, a delivery man returns to the shop carrying booklets that were not sold. The Administrator records a Custody Entry of type `Return`, selecting the delivery man (`from_delivery_man`) and the booklets being handed back. On submit, each listed booklet transitions from `In Custody` back to `In Stock` and its `current_delivery_man` is cleared. The booklets are then available for re-assignment.

**Why this priority**: Return is the direct inverse of Assign and is needed in day-to-day operation. Without it, unsold booklets can never leave a delivery man's name, blocking re-assignment and creating a stale view of custody. It is P2 because Assign must exist first (there must be something to return), and because in practice not every booklet returns every day — many get sold (future phase) or stay overnight with the delivery man.

**Independent Test**: Can be fully tested after Story 1 by taking one of the booklets assigned to Ali, creating a Custody Entry of type `Return` with Ali as `from_delivery_man` and that booklet in the list, and submitting. Verify the booklet is now `In Stock` with `current_delivery_man` empty, while the other booklet assigned to Ali remains `In Custody` unchanged.

**Acceptance Scenarios**:

1. **Given** booklet `WP-00001` is `In Custody` with `current_delivery_man = Ali`, **When** the Administrator submits a Custody Entry of type `Return` with `from_delivery_man = Ali` listing that booklet, **Then** the booklet moves to `In Stock` and `current_delivery_man` is cleared.
2. **Given** a booklet is currently in custody of Sami (not Ali), **When** a Return entry is submitted with `from_delivery_man = Ali` listing that booklet, **Then** the submission is rejected with a clear error identifying the booklet and its actual holder.
3. **Given** a Return entry is submitted successfully, **When** the Administrator later views the booklet, **Then** it appears in `In Stock` lists again and can be selected for a future Assign.
4. **Given** a Return entry is submitted with no `from_delivery_man` selected, **When** the Administrator tries to submit, **Then** the submission is rejected with a clear error naming the missing field.

---

### User Story 3 - Transfer Booklets Between Delivery Men, Including Partial Transfers (Priority: P2)

Two delivery men sometimes meet on the road: one runs low, another has extras. Rather than routing through the shop, booklets pass directly between them. The Administrator records a Custody Entry of type `Transfer` with `from_delivery_man` and `to_delivery_man` set, listing the subset of booklets being moved. On submit, only those listed booklets change hands; every other booklet each delivery man was carrying stays where it was. The booklet status remains `In Custody` throughout, but `current_delivery_man` updates.

**Why this priority**: Transfer is common enough to be P2 but less frequent than Assign/Return. The **partial** behaviour is important: the Administrator must be able to move any subset, not just "everything a delivery man is carrying." Without Transfer, the only way to reassign a booklet is Return-then-Assign, which misrepresents the real-world hand-off (the booklet never actually returned to the shop) and creates an inaccurate audit trail.

**Independent Test**: Can be fully tested by first assigning two booklets to Ali and two to Sami (Story 1), then submitting a single Custody Entry of type `Transfer` from Ali to Sami listing exactly one of Ali's two booklets. Verify that one booklet now shows `current_delivery_man = Sami`, Ali still holds one booklet, Sami holds three, and all four booklets remain `In Custody`.

**Acceptance Scenarios**:

1. **Given** booklets `WP-00001` and `WP-00002` are both in Ali's custody, **When** the Administrator submits a Transfer entry from Ali to Sami listing only `WP-00001`, **Then** `WP-00001` now has `current_delivery_man = Sami` and status `In Custody`, while `WP-00002` still has `current_delivery_man = Ali` and status `In Custody`.
2. **Given** a Transfer entry is submitted where one of the listed booklets is currently held by a third party (not `from_delivery_man`), **When** submit is attempted, **Then** the submission is rejected with a clear error, and no booklet is modified.
3. **Given** a Transfer entry is submitted with `from_delivery_man` and `to_delivery_man` equal, **When** submit is attempted, **Then** the submission is rejected with a clear error; a self-transfer is not meaningful.
4. **Given** a Transfer entry is submitted with either `from_delivery_man` or `to_delivery_man` missing, **When** submit is attempted, **Then** the submission is rejected with a clear error naming the missing field.
5. **Given** a Transfer entry includes a booklet whose current status is not `In Custody` (e.g., it is `In Stock`), **When** submit is attempted, **Then** the submission is rejected with a clear error, and no booklet is modified.

---

### User Story 4 - Observe Current Custody by Delivery Man (Priority: P3)

At any time, the Administrator needs a single view answering "who is currently holding what?" — a list of every booklet currently `In Custody`, grouped or filterable by delivery man. Opening any row exposes the full custody history of that booklet (the chain of Custody Entries that brought it there).

**Why this priority**: Observability of current custody is essential for day-to-day decisions (planning routes, locating specific booklets, investigating discrepancies in later phases). It is P3 because, strictly speaking, all the data it displays is derivable from records produced by Stories 1–3 — a standard list view over the booklet DocType filtered to `In Custody` already gives the answer. This story exists to make that view first-class, grouped, and discoverable, and to guarantee the history reconstructibility requirement.

**Independent Test**: Can be fully tested by exercising Stories 1–3 to produce a realistic state (a few delivery men, a mix of booklets in custody), then opening the "Current Custody by Delivery Man" list view, filtering by a specific delivery man, and confirming the listed booklets match exactly. Opening any listed booklet and viewing its custody history shows the chain of Custody Entries (Assign → possibly Transfer → etc.) in order.

**Acceptance Scenarios**:

1. **Given** Ali currently holds two booklets and Sami currently holds three, **When** the Administrator opens the Current Custody by Delivery Man view, **Then** both delivery men appear with their booklets, each booklet visible exactly once, and no booklet that is not currently `In Custody` appears.
2. **Given** a booklet has been through Assign → Transfer → Transfer, **When** the Administrator opens that booklet and views its custody history, **Then** all three Custody Entry records are listed in chronological order with the involved delivery men and timestamps, fully reconstructing the chain of custody.
3. **Given** the Administrator filters the view by a specific delivery man, **When** the view renders, **Then** only booklets currently in that delivery man's custody are displayed.
4. **Given** a booklet was returned to stock, **When** the Current Custody view is opened, **Then** that booklet does not appear anywhere in the view (it is no longer `In Custody`).

---

### Edge Cases

- **Empty booklet list**: A Custody Entry submitted with an empty child table (no booklets) must be rejected with a clear error — a custody change with no booklets is meaningless.
- **Duplicate booklet within one entry**: The same booklet listed twice in the same Custody Entry's child table must be rejected with a clear error, to prevent double-processing and ambiguous audit records.
- **Transactional atomicity**: If any booklet in the entry fails validation (wrong source state, wrong holder, etc.), no booklet in the entry is modified. The submit either updates all listed booklets or none.
- **Booklets in terminal or out-of-scope states**: Although Phase 2 only activates `In Stock` and `In Custody`, the schema already supports later states (`Sold`, `Depleted`). Custody entries must reject any booklet not in the valid source state for the chosen entry type, regardless of what the actual invalid state is, with an error message that names the real current state so the Administrator can diagnose it.
- **Cancellation of a submitted Custody Entry**: If a submitted Custody Entry is cancelled (per standard submittable-doc semantics), the booklet state changes it caused must be reversed in a single transaction, and the cancellation must be rejected if that reversal would conflict with the booklet's current state (e.g., the booklet has since been transferred elsewhere).
- **Concurrent custody changes**: If two Administrators try to submit conflicting Custody Entries for the same booklet simultaneously, exactly one succeeds and the other is rejected with a clear error; the booklet's state and audit trail must remain consistent.
- **Same delivery man on both sides of a Transfer**: Rejected — transferring from a delivery man to themselves is not a meaningful operation.
- **Mixed source holders in a single Transfer entry**: A single Transfer entry with `from_delivery_man = Ali` listing booklets that are currently split between Ali and Sami is rejected — the entire entry must be consistent with a single source holder.
- **`from_delivery_man` / `to_delivery_man` presence rules**: `Assign` requires only `to_delivery_man`; `Return` requires only `from_delivery_man`; `Transfer` requires both. Violations of these presence rules are rejected with a clear, field-specific error.
- **Non-Administrator attempts**: Users without the `Purisol Administrator` role must be unable to create, submit, or cancel any Custody Entry.

## Requirements *(mandatory)*

### Functional Requirements

#### Entity & Naming

- **FR-001**: The system MUST provide a `Purisol Custody Entry` record type that is submittable (draft → submitted → optionally cancelled) and has Track Changes enabled. Once submitted, the record is immutable except via the standard cancel mechanism.
- **FR-002**: Each `Purisol Custody Entry` MUST carry: an entry type (`Assign`, `Transfer`, or `Return`), an entry datetime defaulting to the current time, a free-text notes field, and a read-only reference to the user who created it.
- **FR-003**: The `Purisol Custody Entry` MUST include a `from_delivery_man` reference and a `to_delivery_man` reference, both pointing to Employee records. Which of the two is required depends on the entry type (see FR-010 / FR-011 / FR-012).
- **FR-004**: The system MUST provide a `Purisol Custody Entry Booklet` child table attached to each Custody Entry, listing the booklets involved. Each row references exactly one booklet and captures a read-only snapshot of that booklet's status at the time the entry was created (for audit traceability).
- **FR-005**: `Purisol Custody Entry` records MUST auto-number per the project naming convention (year-scoped, zero-padded) so every record has a unique, human-readable identifier visible in lists, forms, and the audit trail.
- **FR-006**: The child table MUST reject an empty list (a Custody Entry with zero booklets is invalid) and MUST reject the same booklet appearing more than once in the same entry.

#### Entry Type Semantics

- **FR-010**: `Assign` entries MUST require `to_delivery_man` and MUST have no `from_delivery_man`. Every listed booklet MUST currently be `In Stock`. On submit, each listed booklet transitions to `In Custody` with `current_delivery_man` set to `to_delivery_man`.
- **FR-011**: `Return` entries MUST require `from_delivery_man` and MUST have no `to_delivery_man`. Every listed booklet MUST currently be `In Custody` with `current_delivery_man == from_delivery_man`. On submit, each listed booklet transitions back to `In Stock` with `current_delivery_man` cleared.
- **FR-012**: `Transfer` entries MUST require both `from_delivery_man` and `to_delivery_man`, and the two MUST differ. Every listed booklet MUST currently be `In Custody` with `current_delivery_man == from_delivery_man`. On submit, each listed booklet remains `In Custody` but `current_delivery_man` updates to `to_delivery_man`. Transfers MAY include any subset of a delivery man's booklets — partial transfers are first-class, not a special case.

#### Validation & Error Semantics

- **FR-020**: On submit, the system MUST validate every listed booklet against the rules for the entry type before modifying anything. Any failure MUST block the submit and leave all booklets in their original state — updates are all-or-nothing within a single Custody Entry.
- **FR-021**: Error messages for invalid source states MUST name the specific booklet and its actual current status (and, where relevant, its actual current holder), so the Administrator can diagnose the problem without guessing.
- **FR-022**: The system MUST reject submission with a clear, field-specific error when required delivery-man fields for the entry type are missing (per FR-010, FR-011, FR-012), and when `from_delivery_man == to_delivery_man` on a Transfer.
- **FR-023**: The system MUST reject submission with a clear error when any booklet listed in a Transfer is not currently held by the stated `from_delivery_man` (detects mixed source holders or stale assumptions).
- **FR-024**: All booklet updates produced by a single Custody Entry submit MUST happen in a single transaction; a failure partway through MUST leave no partial state changes visible.

#### Cancellation & Reversal

- **FR-030**: A submitted Custody Entry MAY be cancelled per standard submittable-doc semantics. When cancelled, the system MUST revert each listed booklet's status and `current_delivery_man` back to what the child-table snapshot recorded at entry time.
- **FR-031**: Cancellation MUST be rejected with a clear error if the reversal would conflict with any booklet's current state — for example, if the booklet has since been moved by a subsequent Custody Entry and reverting would produce an inconsistent custody chain.

#### Observability & Audit

- **FR-040**: The system MUST provide a "Current Custody by Delivery Man" view listing every booklet currently `In Custody`, groupable and filterable by `current_delivery_man`, and excluding booklets in any other status.
- **FR-041**: From any booklet record, the Administrator MUST be able to retrieve the ordered list of Custody Entries that reference it, enabling full reconstruction of its custody history (who held it, when, through which entries).
- **FR-042**: Every field change on a Custody Entry (while in draft) and every submit/cancel event MUST be captured in the change log for the record.

#### Permissions & Scope

- **FR-050**: Only users with the `Purisol Administrator` role MUST be able to create, read, update, submit, or cancel `Purisol Custody Entry` records. Delivery men have no system access in this phase.
- **FR-051**: The only booklet states reachable via Phase 2 operations are `In Stock` and `In Custody`. Any transition to or from `Sold`, `Depleted`, or any other future state is explicitly out of scope for this phase and MUST NOT be producible by a Custody Entry.

### Key Entities *(include if feature involves data)*

- **Purisol Custody Entry**: A submittable record documenting a single custody event. Attributes: entry type (`Assign` / `Transfer` / `Return`), entry datetime, source delivery man (when applicable), destination delivery man (when applicable), notes, creating user, submit state, and a child list of affected booklets. Relationships: references Employee(s) for delivery man roles; references Booklets through the child table; is the authoritative cause of changes to each referenced booklet's `status` and `current_delivery_man`.
- **Purisol Custody Entry Booklet (child)**: One row per booklet in a Custody Entry. Attributes: the booklet reference and a read-only snapshot of the booklet's status at entry creation (used for validation and for reversal on cancel).
- **Purisol Coupon Booklet (existing, from Phase 1)**: Receives updates to `status` (`In Stock` ↔ `In Custody`) and `current_delivery_man` as a consequence of Custody Entry submits. No schema change in this phase; the fields already exist but were unused in Phase 1.
- **Employee (ERPNext standard, leveraged)**: Represents each delivery man. Referenced from `from_delivery_man`, `to_delivery_man`, and booklet `current_delivery_man`. Not modified by this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The Administrator can complete a routine custody operation (Assign, Transfer, or Return of up to 10 booklets) end-to-end in under 60 seconds from opening a new Custody Entry to viewing the resulting updated booklet states.
- **SC-002**: After any successful Custody Entry submit, 100% of listed booklets reflect the correct new status and correct `current_delivery_man` (including `current_delivery_man` cleared on `Return`), verifiable immediately in the booklet record.
- **SC-003**: 100% of Custody Entry submits with at least one invalid booklet (wrong state or wrong holder) are rejected before any booklet is modified — the system never leaves a partial-update visible to any user.
- **SC-004**: For any booklet that has been through one or more Custody Entries, the Administrator can reconstruct the complete chain of custody (every holder and every handoff, in order, with timestamps) from Custody Entry records alone, with no information gaps.
- **SC-005**: The "Current Custody by Delivery Man" view loads and matches reality within 2 seconds for a working set of up to 1,000 booklets currently `In Custody`, and the list contains zero booklets that are not actually `In Custody`.
- **SC-006**: Validation error messages for every rejection path (wrong source state, wrong holder, missing required field, duplicate booklet, empty list, self-transfer) allow a first-time Administrator to identify and correct the problem without consulting external documentation — verified by having a non-author tester resolve each error path on first read.
- **SC-007**: Partial transfers (moving any subset of one delivery man's booklets to another) complete in a single Custody Entry submit, producing exactly one audit record per handoff event — not one record per booklet.

## Assumptions

- **Phase 1 is in place**: `Purisol Coupon Booklet` and `Purisol Coupon` records exist with the fields required to represent custody (`status` and `current_delivery_man`). No schema changes to those DocTypes are required by this phase — the custody fields were already defined in Phase 1 but unused.
- **Employee records exist**: Each delivery man is represented by a standard ERPNext Employee record, created outside this feature (by standard HR onboarding). This feature does not create, edit, or validate Employee records themselves — it only references them.
- **Single-shop operation**: There is exactly one shop; "returning to the shop" and "stock" are unambiguous. Multi-branch and multi-warehouse scenarios are out of scope.
- **Delivery men have no system access**: All custody events are recorded by the Administrator on behalf of delivery men. There is no delivery-man-facing UI in this phase.
- **Notifications deferred**: Bell/email/SMS notifications triggered by custody events are not part of this phase; they are added later. Custody Entry submit may produce change-log entries but does not send notifications in Phase 2.
- **Sales and consumption are out of scope**: Booklets in this phase can only be `In Stock` or `In Custody`. Transitions to `Sold` or `Depleted`, and the behaviour of coupons within a booklet, are handled by later phases.
- **Retroactive backdating**: The Administrator may set `entry_datetime` in the past if a physical custody event occurred before being recorded. The system does not attempt to detect or correct such backdating beyond the standard audit trail.
- **Standard submittable-doc cancellation**: Cancellation semantics follow the framework's standard model (produces a cancelled record, locked for edit, reversible only through a fresh submit). No custom amend/correct mechanism is introduced in this phase.
- **Bulk operations**: A single Custody Entry is expected to contain up to ~50 booklets in realistic use; the transactional-atomicity requirement (FR-020, FR-024) holds at that scale without needing a background job. Batch sizes larger than that are not a target for this phase.
