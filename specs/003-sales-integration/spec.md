# Feature Specification: Sales Integration

**Feature Branch**: `003-sales-integration`
**Created**: 2026-04-18
**Status**: Draft
**Input**: User description: "Phase 3 — Sales Integration: sell coupon booklets to customers using a real ERPNext Sales Invoice as the single source of truth for revenue. The Administrator picks a customer, selects one or more booklets currently `In Stock` or `In Custody`, optionally chooses a Price List, and creates a Sales Invoice with one line per booklet. On invoice submit, each linked booklet transitions to `Sold` with `customer`, `sold_on`, and `sales_invoice` populated and `current_delivery_man` cleared (custody ends at sale). On invoice cancel, the sale is reversed only if no coupons from the booklet have been consumed. Selling an already-`Sold` or `Depleted` booklet is rejected. Consumption and discrepancy logic are out of scope."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Sell a Single Booklet to a Customer (Priority: P1)

The Purisol Administrator records the sale of one booklet to a customer. They open the "Sell Booklets to Customer" workflow, pick the customer, select a single booklet that is currently `In Stock` (sitting in the shop) or `In Custody` (carried by a delivery man), and create a Sales Invoice. The invoice opens as a draft for review — pricing, taxes, terms — and is then submitted through the standard ERPNext flow. On submit, the booklet flips to `Sold`, its `customer`, `sold_on` (the invoice's posting datetime), and `sales_invoice` link are populated, and any `current_delivery_man` is cleared because custody ends at the moment of sale. From this point forward, the booklet's revenue lives in the standard ERPNext General Ledger; the booklet record is the operational handle, but the invoice is the financial source of truth.

**Why this priority**: A single-booklet sale is the smallest end-to-end revenue event the business can record and is by far the most common case. Until this works, the system cannot recognise revenue at all — every later capability (consumption, discrepancies, customer low-stock notifications, sales reports) depends on a booklet having a `customer` and a `sales_invoice`. This single slice delivers the entire phase's core value: a real Sales Invoice exists, the booklet's lifecycle moves forward, and the GL is correct.

**Independent Test**: Can be fully tested by seeding one Customer, one Employee (delivery man), one `In Stock` booklet (Phase 1 output), and a configured `coupon_item` and `default_price_list` in Purisol Settings. Open the Sell Booklets workflow, pick the customer, add the booklet, create and submit the invoice. Verify the invoice exists with one line item at the configured rate and the correct customer, and that the booklet is now `Sold` with `customer`, `sold_on`, `sales_invoice` populated and `current_delivery_man` empty.

**Acceptance Scenarios**:

1. **Given** booklet `WP-00001` is `In Stock`, customer "Acme Co." exists, and Purisol Settings has `coupon_item` and `default_price_list` configured with a non-zero rate, **When** the Administrator runs the Sell Booklets workflow for Acme Co. with `WP-00001` and submits the resulting Sales Invoice, **Then** the booklet transitions to `Sold` with `customer = Acme Co.`, `sold_on` equal to the invoice's posting datetime, `sales_invoice` linking to the new invoice, and `current_delivery_man` empty.
2. **Given** booklet `WP-00002` is `In Custody` with `current_delivery_man = Ali`, **When** the Administrator sells it to a customer and submits the invoice, **Then** the booklet transitions to `Sold` and `current_delivery_man` is cleared (custody ends at sale); the past custody history remains intact and reconstructible.
3. **Given** the Sell Booklets workflow has been run for a customer and the resulting Sales Invoice is still in draft, **When** the Administrator opens the draft, **Then** they see one invoice line per selected booklet with `item_code` equal to the configured `coupon_item`, quantity 1, and rate sourced from the chosen Price List; nothing about the booklet's status has changed yet (status changes only on invoice submit).
4. **Given** an Administrator selects a booklet whose status is `Sold` or `Depleted`, **When** they try to add it to the Sell Booklets workflow or submit an invoice that references it, **Then** the system rejects the action with a clear error naming the booklet and its actual status; no invoice is created (in the workflow) or submit is blocked (when validating an existing draft).
5. **Given** the customer has no Customer-level default Price List configured, **When** the Administrator runs the Sell Booklets workflow without explicitly choosing one, **Then** Purisol Settings' `default_price_list` is used for line-item pricing.

---

### User Story 2 - Sell Multiple Booklets to a Customer in One Invoice (Priority: P2)

A single customer often buys several booklets at once (a household or small reseller stocking up). The Administrator runs the same workflow, picks the customer, multi-selects several booklets — possibly mixing booklets that are `In Stock` and booklets that are currently `In Custody` of one or more delivery men — and creates one Sales Invoice with one line per booklet. On submit, every listed booklet transitions to `Sold` with the same `sold_on` and the same `sales_invoice`, and any held by delivery men have `current_delivery_man` cleared. The invoice total reflects the sum of per-booklet rates from the chosen Price List, and the invoice references each booklet so any later inspection can trace booklet → invoice → customer in one hop.

**Why this priority**: Multi-booklet sale is essential for realistic operation but is naturally an extension of Story 1 — once the single-booklet case is proven, the multi-case is a small generalisation. Bundling several booklets into one invoice (instead of forcing one invoice per booklet) keeps the GL clean, matches accounting practice, and reduces clerical effort.

**Independent Test**: Can be fully tested after Story 1 by seeding one customer, three booklets (mix of `In Stock` and `In Custody`), and selling all three to the same customer in one invoice. Verify the invoice has three line items at the correct rates, the invoice total equals the sum of those rates plus any standard ERPNext taxes, and after submit every booklet is `Sold` with the same `sales_invoice` reference and the appropriate `current_delivery_man` cleared where it was set.

**Acceptance Scenarios**:

1. **Given** booklets `WP-00010`, `WP-00011` are `In Stock` and `WP-00012` is `In Custody` of Sami, **When** the Administrator sells all three to one customer in a single Sell Booklets workflow run and submits the invoice, **Then** the invoice contains three lines each referencing the corresponding booklet, all three booklets become `Sold` with the same `sales_invoice` and `sold_on`, and `WP-00012`'s `current_delivery_man` is cleared.
2. **Given** a multi-booklet draft Sales Invoice references three booklets and one of them was sold separately by another action while the draft was open, **When** the Administrator submits this draft, **Then** the submit is rejected with a clear error identifying the now-`Sold` booklet, and none of the other booklets in the draft are modified — partial completion is not allowed.
3. **Given** a multi-booklet sale draft references the same booklet twice (whether by user error or list-import mistake), **When** the Administrator tries to submit, **Then** the submit is rejected with a clear error identifying the duplicate; a single booklet cannot be sold twice in the same invoice.
4. **Given** a multi-booklet sale draft is created and the Administrator changes the Price List on the draft before submit, **When** the invoice is submitted, **Then** every booklet line uses the rate from the newly chosen Price List; the booklet status changes still happen on submit and reference this final invoice.

---

### User Story 3 - Cancel a Sales Invoice and Reverse the Sale Where Safe (Priority: P3)

A sale can be cancelled — wrong customer, wrong booklets, or a same-day refund before any coupon has been used. The Administrator cancels the Sales Invoice through the standard ERPNext flow. For each booklet on the invoice, if no coupon from that booklet has been consumed yet (i.e., the booklet is still `Sold` with full `remaining_count`), the system reverses the sale: status goes back to `In Stock`, and `customer`, `sold_on`, `sales_invoice` are cleared. If any coupon has already been consumed, the cancellation is rejected with a clear error explaining why — once consumption has begun, the only correction path is a financial adjustment (handled outside this phase), not a silent reversal.

**Why this priority**: Cancellation is needed for normal corrections but is much rarer than sales themselves. It is also strictly safer to ship after Stories 1 and 2 have proved out the forward path. The "reverse only when no coupon consumed" rule is the system's main guarantee that revenue and inventory cannot be quietly undone after a customer has begun using coupons; getting it right matters for trust in the GL and for delivery-man accountability.

**Independent Test**: Can be fully tested by completing a sale (Story 1), then cancelling the invoice and verifying the booklet is restored to `In Stock` with `customer`, `sold_on`, `sales_invoice` cleared. Then complete a second sale and (using fixtures from Phase 4 or a direct test setup) mark one of the booklet's coupons `Consumed`; cancel the invoice and verify the cancellation is rejected with a clear error message and the booklet remains `Sold`.

**Acceptance Scenarios**:

1. **Given** booklet `WP-00020` is `Sold` via invoice `INV-001` and no coupon from that booklet has been consumed, **When** the Administrator cancels `INV-001`, **Then** `WP-00020` returns to `In Stock` with `customer`, `sold_on`, and `sales_invoice` cleared; `current_delivery_man` remains empty (cancellation does not restore prior custody — that requires an explicit Custody Entry).
2. **Given** booklet `WP-00021` is `Sold` via invoice `INV-002` and at least one coupon from that booklet has been consumed (status `Consumed`), **When** the Administrator tries to cancel `INV-002`, **Then** the cancellation is rejected with a clear error naming the booklet and stating that coupons from it have been consumed; the booklet remains `Sold` and the invoice remains submitted.
3. **Given** a multi-booklet invoice `INV-003` covers booklets `A`, `B`, `C`, where `A` and `B` have no consumption but `C` has a consumed coupon, **When** the Administrator cancels `INV-003`, **Then** the cancellation is rejected with an error identifying `C`; no booklet on the invoice is modified — cancellation is all-or-nothing across the invoice.
4. **Given** an invoice has been cancelled successfully and its booklets are back to `In Stock`, **When** the Administrator opens any reversed booklet, **Then** the booklet's change log shows the sale and the reversal as distinct events, and the booklet can be sold again in a fresh invoice.

---

### User Story 4 - Choose a Price List Per Sale (Retail vs Wholesale) (Priority: P3)

Different customers buy at different rates. The Administrator can override the default Price List on a per-sale basis — for example, a wholesale customer gets the wholesale rate even when the per-customer default is not set. The Sell Booklets workflow exposes Price List as an optional input. The resolution order is explicit: (1) any Price List the Administrator chooses on the workflow, otherwise (2) the customer's own default Price List, otherwise (3) Purisol Settings' `default_price_list`. Once chosen, that Price List drives the rate on every booklet line on the invoice.

**Why this priority**: Pricing variation is a real business need but the underlying mechanism is standard ERPNext (Price List + Pricing Rules) and works out of the box. The Phase 3 contribution is small: surface the choice in the workflow, document the resolution order, and ensure the invoice carries it through. This story is P3 because Stories 1 and 2 already produce valid invoices using the default — Story 4 just makes the per-sale choice convenient and predictable.

**Independent Test**: Can be fully tested by seeding two Price Lists ("Retail" and "Wholesale") with different rates for the configured `coupon_item`, plus one customer with no per-customer default Price List. Run the Sell Booklets workflow once leaving Price List blank (verify the line uses Purisol Settings `default_price_list`), once choosing "Retail" (verify the line uses retail rate), and once choosing "Wholesale" (verify the line uses wholesale rate).

**Acceptance Scenarios**:

1. **Given** Purisol Settings' `default_price_list` is "Standard Selling" with rate 100, the customer has no per-customer Price List, and the Administrator does not pick a Price List in the workflow, **When** an invoice is created and submitted for one booklet, **Then** the line rate is 100.
2. **Given** the customer's default Price List is "Wholesale" with rate 80 and the Administrator does not pick a Price List in the workflow, **When** an invoice is created and submitted, **Then** the line rate is 80, not the Settings default.
3. **Given** the Administrator explicitly picks "Retail" with rate 120 on the workflow, regardless of customer or Settings defaults, **When** an invoice is created and submitted, **Then** every booklet line is priced at 120.
4. **Given** the chosen Price List has no entry for the configured `coupon_item` (misconfiguration), **When** the Administrator tries to create the invoice, **Then** the system surfaces a clear error from the underlying invoice creation that names the missing Price List entry, so the Administrator can fix the configuration without guessing.

---

### Edge Cases

- **Empty booklet selection**: A Sell Booklets workflow run with zero booklets is rejected with a clear error — a sale with no items is meaningless.
- **Customer not selected**: The workflow rejects creation when no customer is chosen; an invoice without a customer cannot be created in ERPNext anyway, but the error must surface at the workflow step, not deep inside the invoice form.
- **Stale draft, booklet sold elsewhere**: A draft Sales Invoice can sit unsubmitted for hours. If, in the meantime, one of its booklets is sold by a different invoice, submitting the stale draft is rejected at the on-submit validation step; the Administrator must rebuild the draft.
- **Stale draft, booklet returned to stock**: A draft was created when a booklet was `In Custody`; the delivery man has since returned the booklet via a Custody Entry. The booklet is now `In Stock` — still a valid source state — and the submit succeeds normally.
- **Stale draft, booklet transferred between delivery men**: Same as above — `In Custody` is `In Custody`, regardless of holder. Submit succeeds; the new holder's `current_delivery_man` is cleared on submit.
- **Configuration missing**: If `coupon_item` is not set in Purisol Settings, the Sell Booklets workflow refuses to start and points the Administrator to Settings to configure it. The same applies to `default_price_list` when no other Price List is resolved.
- **Booklet referenced by a draft that is never submitted**: A draft that is never submitted leaves the booklet's status untouched (no premature reservation). If the booklet is sold via a different submitted invoice in the meantime, the original draft simply becomes invalid and will be rejected on submit.
- **Cancellation of a draft (not yet submitted)**: Cancelling or deleting an unsubmitted draft has no booklet side-effects to reverse.
- **Concurrent submit of two invoices for the same booklet**: Exactly one invoice succeeds; the other is rejected at the on-submit validation step with a clear error identifying the now-`Sold` booklet.
- **Amendment of a submitted invoice**: When an Administrator amends a submitted Sales Invoice (cancel + new), the new invoice goes through the same validations; the original cancellation must respect the consumption-based reversal rule (Story 3) before the amendment can proceed.
- **Non-Administrator attempts**: Users without the `Purisol Administrator` role must be unable to launch the Sell Booklets workflow or to create or submit invoices that link booklets via the booklet reference.
- **Invoice line without a booklet reference**: Standard Sales Invoices in ERPNext may include unrelated items. Only invoice lines that reference the configured `coupon_item` AND carry a booklet reference are subject to Phase 3 logic; other lines are left alone, so Sales Invoices remain usable for general selling.
- **Booklet reference points to a non-existent booklet**: The on-submit validation rejects the invoice with a clear error; this is a data-integrity failure, not a state-machine failure.

## Requirements *(mandatory)*

### Functional Requirements

#### Configuration & Setup

- **FR-001**: Purisol Settings MUST expose a `coupon_item` field that links to an ERPNext Item. This field is required for any sales operation. Setup documentation MUST describe how to create the Item with UOM `Booklet` and a non-stock flag (so booklets are tracked by Purisol records, not by ERPNext inventory).
- **FR-002**: Purisol Settings MUST expose a `default_price_list` field that links to an ERPNext Price List. This field is the final fallback when no other Price List is resolved for a sale.
- **FR-003**: The Sell Booklets workflow MUST refuse to start if `coupon_item` is unset, with a clear error directing the Administrator to Purisol Settings.

#### Sell Booklets Workflow (UI)

- **FR-010**: The system MUST provide a "Sell Booklets to Customer" entry point reachable both from the Coupon Booklet list view (as a prominent action) and from a dedicated workflow form, so the Administrator can start a sale from either context.
- **FR-011**: The workflow MUST require the Administrator to choose a Customer (Link to Customer, required).
- **FR-012**: The workflow MUST allow the Administrator to multi-select one or more booklets, with the selection list filtered to booklets currently `In Stock` or `In Custody`. Booklets in any other status MUST NOT be selectable.
- **FR-013**: The workflow MUST allow the Administrator to optionally choose a Price List. When the Administrator does not choose one, the system MUST resolve the Price List in this order: (1) the customer's own default Price List, if set; otherwise (2) `Purisol Settings.default_price_list`.
- **FR-014**: On execution, the workflow MUST create exactly one ERPNext Sales Invoice with one line per selected booklet. Each line MUST reference the configured `coupon_item`, set quantity to 1, and source its rate from the resolved Price List. Each line MUST also carry a reference back to the specific booklet it sells (so the on-submit hook can update the right record).
- **FR-015**: After creating the draft invoice, the workflow MUST navigate the Administrator to the draft for review (pricing, taxes, terms, payment) and MUST NOT submit the invoice automatically — submit is an explicit user action.
- **FR-016**: The workflow MUST refuse to create an invoice with zero selected booklets and MUST refuse to create an invoice with the same booklet selected more than once, returning a clear error in each case.

#### Sales Invoice Submit Behaviour

- **FR-020**: On Sales Invoice submit, the system MUST iterate every line whose `item_code` equals the configured `coupon_item` AND that carries a booklet reference. Lines without a booklet reference (or with a different `item_code`) MUST be ignored by Phase 3 logic.
- **FR-021**: For each such line, the system MUST validate that the referenced booklet exists AND is in `In Stock` or `In Custody`. If any referenced booklet is in any other status (notably `Sold` or `Depleted`), the submit MUST be rejected with a clear error naming the booklet and its actual status.
- **FR-022**: If the same booklet is referenced by two or more lines on the same invoice, the submit MUST be rejected with a clear error identifying the duplicate.
- **FR-023**: If a referenced booklet does not exist (broken link), the submit MUST be rejected with a clear data-integrity error naming the missing reference.
- **FR-024**: When all referenced booklets pass validation, the system MUST update each one in a single transaction with: status `Sold`, `customer = invoice.customer`, `sold_on = invoice.posting_datetime`, `sales_invoice = invoice.name`, and `current_delivery_man = empty`. A failure partway through MUST leave no partial state visible.
- **FR-025**: Booklet updates triggered by an invoice submit MUST be auditable: each affected booklet's change log MUST attribute the status change to the submitted Sales Invoice (so any later viewer can answer "why did this booklet become Sold?" without external context).

#### Sales Invoice Cancel Behaviour

- **FR-030**: On Sales Invoice cancel, the system MUST iterate the same set of lines (`item_code = coupon_item` AND booklet reference present). For each referenced booklet, the system MUST check whether any coupon from that booklet has status `Consumed`.
- **FR-031**: If any referenced booklet has at least one consumed coupon, the cancellation MUST be rejected with a clear error naming the booklet(s) and stating that consumption has begun. No booklet on the invoice is modified — cancellation is all-or-nothing across the invoice.
- **FR-032**: If no referenced booklet has any consumed coupon, the cancellation MUST proceed and, in a single transaction, MUST revert each referenced booklet to: status `In Stock`, `customer = empty`, `sold_on = empty`, `sales_invoice = empty`. `current_delivery_man` MUST remain empty (cancellation does not reconstruct any prior custody — restoring custody to a delivery man requires an explicit Custody Entry).
- **FR-033**: A successful cancellation MUST also leave a clear audit trail: each affected booklet's change log MUST attribute the reversal to the cancelled Sales Invoice.

#### Pricing & Price List Resolution

- **FR-040**: The line-item rate on each booklet line MUST come from the Price List resolved in FR-013. Standard ERPNext Pricing Rules MUST continue to apply on top, without custom intervention.
- **FR-041**: If the resolved Price List has no entry for the configured `coupon_item`, the system MUST surface a clear error (from standard ERPNext invoice creation), naming the Price List, so the Administrator can fix the configuration.

#### Permissions & Scope

- **FR-050**: Only users with the `Purisol Administrator` role MUST be able to launch the Sell Booklets workflow. Standard ERPNext sales permissions continue to apply on the Sales Invoice itself.
- **FR-051**: Phase 3 MUST NOT implement any consumption logic or any discrepancy detection. Coupons inside sold booklets remain `Available` until acted on by a later phase. A booklet's `consumed_count` and `remaining_count` are not modified by sale or cancellation.
- **FR-052**: Phase 3 MUST NOT introduce partial-booklet refunds, partial returns, or sale-of-individual-coupons flows. The unit of sale is a whole booklet.

#### Integration Boundaries

- **FR-060**: The Sales Invoice produced by Phase 3 MUST be a standard ERPNext Sales Invoice, fully visible in standard sales reports, AR, and tax processing — no parallel custom invoice DocType is created.
- **FR-061**: The link between a booklet and its sale MUST be bidirectional: from the booklet, the Administrator MUST be able to navigate to the source Sales Invoice; from the Sales Invoice, each line MUST identify the specific booklet it sold.

### Key Entities *(include if feature involves data)*

- **Purisol Settings (existing, extended)**: A singleton already created in Phase 1. Phase 3 activates two fields that must be populated for sales: `coupon_item` (link to the ERPNext Item that represents a coupon booklet for sales purposes) and `default_price_list` (the fallback Price List used when no more specific one is resolved).
- **Purisol Coupon Booklet (existing, from Phase 1)**: Receives status transition `In Stock` / `In Custody` → `Sold` on invoice submit, and the inverse on safe invoice cancel. Phase 3 populates `customer`, `sold_on`, and `sales_invoice` on submit and clears them on cancel; clears `current_delivery_man` on submit. No schema changes — those fields already exist from Phase 1.
- **Purisol Coupon (existing, from Phase 1)**: Phase 3 reads `status` per coupon to decide whether a sale can be reversed (consumption-blocks-cancellation rule). Phase 3 does not change any coupon record.
- **Sales Invoice (ERPNext standard, leveraged)**: One Sales Invoice per sale, with one line per sold booklet. Each booklet-bearing line references the configured `coupon_item` and carries a reference to its specific booklet. The invoice is the financial source of truth for all booklet revenue; the booklet record is the operational handle.
- **Item (ERPNext standard, leveraged)**: One Item, configured in Purisol Settings as `coupon_item`. UOM is `Booklet`; the Item is non-stock so that ERPNext inventory does not double-count what Purisol already tracks.
- **Price List (ERPNext standard, leveraged)**: Drives the per-line rate on the Sales Invoice. Resolution order on a given sale is: workflow choice, then customer default, then Purisol Settings default. Phase 3 does not introduce new Price Lists; it consumes whatever the business has configured.
- **Customer (ERPNext standard, leveraged)**: The buyer on every sale. Read for Price List default and stamped onto the booklet on sale. Not modified by this feature.
- **Employee (ERPNext standard, leveraged)**: Read indirectly: a booklet's `current_delivery_man` (set in Phase 2) is cleared on sale. Not modified by this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The Administrator can complete a single-booklet sale (open workflow → pick customer → pick booklet → submit invoice) end-to-end in under 60 seconds, ending with a submitted Sales Invoice and a `Sold` booklet correctly stamped with `customer`, `sold_on`, `sales_invoice`.
- **SC-002**: After any successful Sales Invoice submit, 100% of booklet-bearing lines on that invoice produce a booklet update with the correct `customer`, `sold_on`, `sales_invoice`, status `Sold`, and `current_delivery_man = empty` — verifiable by inspecting any affected booklet record immediately.
- **SC-003**: A multi-booklet sale of up to 10 booklets in a single invoice completes (workflow → submit) in under 90 seconds and produces exactly one Sales Invoice with one line per booklet, all carrying the same `posting_datetime` on each booklet's `sold_on`.
- **SC-004**: 100% of attempts to sell a booklet whose status is not `In Stock` or `In Custody` are rejected — either at workflow selection time (the booklet is not in the picklist) or at invoice-submit validation time (the line is rejected with a clear error). No `Sold` or `Depleted` booklet can re-enter the sales path.
- **SC-005**: 100% of Sales Invoice submits with at least one invalid booklet line (wrong status, duplicate, broken link) are rejected before any booklet is modified — the system never leaves a partial-update visible to any user.
- **SC-006**: Cancellation of a Sales Invoice succeeds when no coupon from any referenced booklet has been consumed, and is rejected (with a clear error naming the offending booklet) in 100% of cases where any referenced booklet has at least one consumed coupon. Reversed booklets return to `In Stock` with `customer`, `sold_on`, `sales_invoice` cleared.
- **SC-007**: For any sold booklet, the Administrator can navigate from the booklet to its source Sales Invoice in one click, and from any line of the invoice back to the specific booklet sold; the link is bidirectional and never broken by normal operation.
- **SC-008**: Price List resolution follows the documented order (workflow choice → customer default → Settings default) with zero ambiguity: the line rate on the resulting invoice always matches what the chosen Price List specifies for `coupon_item`. Verified by exercising all three resolution paths.
- **SC-009**: Validation error messages for every rejection path (booklet wrong status, duplicate booklet on invoice, missing customer, missing booklets, broken booklet reference, cancellation blocked by consumption, missing Price List entry, missing `coupon_item` configuration) allow a first-time Administrator to identify and correct the problem without consulting external documentation — verified by having a non-author tester resolve each error path on first read.
- **SC-010**: Every booklet that becomes `Sold` (or reverts on safe cancel) carries an audit-trail entry attributing the change to the submitted (or cancelled) Sales Invoice, so any later viewer can answer "why did this booklet's status change?" from the booklet record alone.

## Assumptions

- **Phase 1 and Phase 2 are in place**: `Purisol Coupon Booklet`, `Purisol Coupon`, and `Purisol Settings` already exist with their full schemas. Booklets can be `In Stock` or `In Custody` and have `customer`, `sold_on`, `sales_invoice`, `current_delivery_man` fields ready to populate. No schema changes to those DocTypes are required by Phase 3 beyond activating the `coupon_item` and `default_price_list` fields on Settings.
- **The configured `coupon_item` exists before any sale**: Setup documentation describes creating the ERPNext Item with UOM `Booklet` and the non-stock flag, and assigning it in Purisol Settings. Phase 3 does not auto-create the Item; it only refuses to operate when it is missing.
- **At least one Price List with the `coupon_item` priced exists**: The shop has configured at least one Price List with a rate for `coupon_item`. Phase 3 surfaces clear errors when Price List entries are missing but does not fabricate prices.
- **Customer and Employee records exist outside this feature**: Customers and delivery men (Employees) are created via standard ERPNext flows. Phase 3 reads them and references them but never creates or edits them.
- **Custody ends at sale**: The constitution and PRD agree that once a booklet is sold, no `current_delivery_man` is recorded. Coupons consumed from sold booklets are recorded against whichever delivery man hands them in (Phase 4), independent of who carried the booklet at the moment of sale. The custody history up to the moment of sale remains in the Custody Entry chain (Phase 2).
- **No partial returns or refunds in MVP**: Once a booklet is sold and any coupon from it is consumed, the booklet runs to depletion. The only "undo" path Phase 3 provides is full invoice cancellation prior to any consumption.
- **Standard ERPNext invoice mechanics**: Tax, AR, payment, and amend behaviour are all standard ERPNext. Phase 3 piggybacks on them and does not introduce parallel financial logic.
- **Notifications deferred**: Phase 3 does not raise warehouse-low-stock or any other notification on invoice submit; the notification layer is a later phase. The submit and cancel flows are designed so a future notification layer can plug in without changes to Phase 3 code.
- **Consumption and discrepancies deferred**: Phase 3 does not record any coupon consumption and does not detect any discrepancy. It only reads coupon `status` to enforce the consumption-blocks-cancellation rule.
- **Bulk operations**: A single sale is expected to cover up to ~10 booklets in realistic operation. The transactional-atomicity requirements (FR-024, FR-031, FR-032) hold at that scale without needing a background job. Larger bulk sales are not a target for this phase.
- **Single-shop, single-currency**: One shop, one base currency. Multi-branch and multi-currency are explicit non-goals for the MVP.
