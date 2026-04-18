# Purisol — Spec-Kit Project Plan
## Spec-Driven Development Roadmap

**Companion to:** `Purisol_Coupon_Management_PRD.md`
**Methodology:** [GitHub Spec Kit](https://github.com/github/spec-kit)
**Total Phases:** 1 Constitution + 8 Feature Phases

---

## How This Plan Maps to Spec-Kit

Spec-Kit's workflow runs: `/constitution` → for each feature: `/specify` → `/clarify` → `/plan` → `/tasks` → `/analyze` → `/implement`.

This plan gives you:
1. **One constitution** (written once, referenced by all features)
2. **Eight feature phases** — each becomes its own `/specify` run on its own Git branch

**Why 8 phases instead of one big spec?** Spec-Kit performs best with narrowly scoped features. A 50-task spec loses focus; a 10-task spec stays sharp. Each phase below is sized to produce a coherent, testable increment.

**Dependency rule:** Phases 1–5 are strictly sequential (each depends on the previous). Phases 6–8 can run in parallel once Phase 5 is done, though shipping them in the listed order gives a better user experience.

---

## Phase 0 — Project Constitution

**Purpose:** Establish the non-negotiable rules that every subsequent spec, plan, and implementation must respect. Written once, referenced forever.

**Spec-Kit command:** `/constitution`

**What to feed into `/constitution` (copy-paste this):**

```
The Purisol Water Coupon Management System operates on ERPNext (custom Frappe app).
It must follow these non-negotiable principles:

1. NAMING CONVENTION
   - Every custom DocType name starts with "Purisol " (with a trailing space before
     the descriptive name). Example: "Purisol Coupon Booklet".
   - This prevents collisions with ERPNext core DocTypes and makes custom records
     visually distinct in the UI.

2. LEVERAGE ERPNEXT PRIMITIVES
   - Never create a custom parallel for an existing ERPNext concept.
   - Customers = ERPNext Customer. Delivery men = ERPNext Employee.
   - Sales of booklets = ERPNext Sales Invoice (not a custom sale DocType).
   - Financial consequences of discrepancies = ERPNext Journal Entry or Payment Entry.
   - Pricing = ERPNext Price List + Pricing Rules.

3. STATE MACHINE ENFORCEMENT
   - Every stateful DocType documents its allowed transitions.
   - Disallowed transitions raise ValidationError, never silently succeed.
   - Terminal states (e.g. Depleted) are truly terminal — no re-opening.

4. AUDIT TRAIL BY DEFAULT
   - Every Purisol DocType has Track Changes enabled.
   - Every state-changing action produces a submittable record (Custody Entry,
     Consumption Entry, Discrepancy) — never a silent field update.
   - Individual coupons store consumption metadata (when, who handed in, which entry)
     even if aggregate counts drift.

5. ERROR HANDLING SEMANTICS
   - Blocking errors: raised when data is logically impossible (duplicate coupon,
     already-consumed coupon, invalid state transition). Prevent submit.
   - Warning discrepancies: raised when data suggests wrongdoing but may have
     innocent explanation (missing coupons in sequence, unassigned booklet). Allow
     submit, create Discrepancy record for investigation.

6. ROLE MODEL
   - MVP has one custom role: "Purisol Administrator".
   - Delivery men have no system access in MVP. All operations on their behalf are
     performed by the Administrator.

7. NOTIFICATION CHANNEL
   - MVP uses ERPNext bell notifications only.
   - Code must be structured so email/WhatsApp/SMS channels can be added later
     without refactoring the trigger logic.

8. BACKGROUND JOBS FOR LONG OPERATIONS
   - Any operation that creates more than 100 records (e.g. generating 20+ booklets
     which means 400+ coupon records) must run via frappe.enqueue, not synchronously.

9. LOCALIZATION
   - All user-facing strings wrapped in frappe._() for translation.
   - Arabic and English must both render correctly; no hardcoded LTR assumptions.

10. TESTING DISCIPLINE
    - Every phase ships with unit tests for DocType validations and state transitions.
    - Integration tests cover end-to-end flows (generate → assign → sell → consume).
    - Tests use the Frappe test framework (frappe.tests.utils.FrappeTestCase).
```

**Output:** `constitution.md` at the project root. Every later `/specify` and `/plan` automatically respects these rules.

---

## Phase 1 — Core Data Model (Booklets & Coupons)

**Goal:** Establish the foundational entities. Everything else in the system references these.

**Prerequisites:** Constitution only.

**Scope (in):**
- `Purisol Settings` (singleton DocType with configuration)
- `Purisol Coupon Booklet` DocType (without custody or customer fields active yet — those belong to later phases; but the schema fields exist, just unused)
- `Purisol Coupon` DocType
- Booklet generation action: creates N booklets + N×20 coupons with correct sequential numbering
- Background job for generating batches > 20 booklets
- Sequential numbering logic (WP-00001 → WP-00002; CP-NNNNN continues across booklets)
- Unit tests for numbering logic and generation

**Scope (out):** Custody, sales, consumption, discrepancies, notifications, reports — all deferred.

**Key acceptance criteria:**
- Generating 50 booklets creates exactly 50 `Purisol Coupon Booklet` records and 1,000 `Purisol Coupon` records.
- Booklet `WP-00002` contains coupons `CP-00021` through `CP-00040`.
- All generated booklets have status `In Stock`; all coupons `Available`.
- Generation of > 20 booklets runs as a background job with progress feedback.

**Spec prompt for `/specify`:**

```
Implement the foundational data model for the Purisol water coupon system.

Create these DocTypes with the exact fields described in PRD sections 7.1, 7.2,
and 7.6:
- Purisol Coupon Booklet
- Purisol Coupon
- Purisol Settings

Implement a "Generate Booklets" action that:
- Accepts a quantity (int) and optional batch_id (string)
- Computes the next booklet number from the highest existing WP-#### name
- Creates the requested number of booklets, each with status "In Stock"
- For each booklet, creates 20 Purisol Coupon records with sequential CP-####
  numbers that continue across booklets (WP-00002's coupons are CP-00021 to CP-00040)
- Runs synchronously for quantity <= 20, and via frappe.enqueue for quantity > 20
- Returns a summary: first booklet name, last booklet name, total coupons created

Do NOT implement custody, sales, consumption, or discrepancy logic in this phase —
those are later features. Booklet status stays at "In Stock" in this phase; other
status values are defined in the schema but not reachable yet.

Include unit tests covering:
- Correct sequential numbering across multiple batches
- Correct coupon-to-booklet assignment (CP-00021 belongs to WP-00002, not WP-00001)
- Background job behavior for large batches
- Validation that Purisol Settings singleton cannot be duplicated
```

**Estimated complexity:** Medium. The numbering logic is the only non-obvious part.

---

## Phase 2 — Custody Management

**Goal:** Track which delivery man holds which booklet, with full history.

**Prerequisites:** Phase 1.

**Scope (in):**
- `Purisol Custody Entry` submittable DocType
- `Purisol Custody Entry Booklet` child table
- Three entry types: `Assign`, `Transfer`, `Return`
- State transitions: `In Stock` ↔ `In Custody` (with `current_delivery_man` field populated/cleared)
- Partial transfer support (a subset of a delivery man's booklets can move)
- Validation enforcing that source state matches expected (e.g. you can't `Assign` a booklet that's already `In Custody`)
- "Current Custody by Delivery Man" list view/report

**Scope (out):** Sales, consumption, discrepancies.

**Key acceptance criteria:**
- Assigning booklets from shop to delivery man works and is reflected on the booklet records.
- Transferring a subset of one delivery man's booklets to another works in a single Custody Entry.
- Returning booklets to shop clears `current_delivery_man` and restores `In Stock`.
- Attempting invalid transitions (e.g. transferring a `Sold` booklet) fails with a clear error.
- Custody history is fully reconstructible from Custody Entry records.

**Spec prompt for `/specify`:**

```
Implement custody tracking for Purisol Coupon Booklets.

Create the Purisol Custody Entry submittable DocType with fields per PRD section 7.3,
including the Purisol Custody Entry Booklet child table.

Implement the three entry types (Assign, Transfer, Return) with their validation
rules per PRD section 8.3:
- Assign: source booklets must be "In Stock", assigns to to_delivery_man.
- Transfer: source booklets must be "In Custody" with current_delivery_man ==
  from_delivery_man. Updates current_delivery_man to to_delivery_man.
- Return: source booklets must be "In Custody" with current_delivery_man ==
  from_delivery_man. Sets booklet back to "In Stock", clears current_delivery_man.

On Custody Entry submit, update each booklet's status and current_delivery_man
within a single database transaction.

Provide a standard ERPNext list view for "Current Custody by Delivery Man" showing
every booklet currently "In Custody" grouped by delivery man.

Do NOT implement sales, consumption, or discrepancy logic. Booklets in this phase
can only be "In Stock" or "In Custody".

Include tests covering:
- Each entry type with valid and invalid source states
- Partial transfer (moving a subset of booklets between delivery men)
- Audit trail: listing all custody changes for a given booklet
```

**Estimated complexity:** Medium. Main challenge is validation rigor.

---

## Phase 3 — Sales Integration

**Goal:** Sell a booklet to a customer through a real Sales Invoice, linking everything together.

**Prerequisites:** Phases 1 and 2.

**Scope (in):**
- Configuration: the coupon Item in Purisol Settings
- "Sell Booklet to Customer" action / wizard form (supports one or multiple booklets in a single sale)
- Sales Invoice generation with booklets as line items
- Booklet state transition: `In Custody` or `In Stock` → `Sold` on Sales Invoice submit
- Population of booklet fields: `customer`, `sold_on`, `sales_invoice`
- Clearing of `current_delivery_man` on sale (custody ends at sale per the constitution)
- Integration with ERPNext Price Lists (retail, wholesale)

**Scope (out):** Consumption, discrepancies. Partial returns / refunds are explicitly out of MVP.

**Key acceptance criteria:**
- Selling a booklet creates a proper Sales Invoice with the correct customer, item, and price from the selected Price List.
- On Sales Invoice submit, each booklet line transitions the booklet to `Sold` with correct metadata.
- Selling multiple booklets in one invoice works for both same-customer scenarios.
- Attempting to sell a `Sold` or `Depleted` booklet fails with a clear error.

**Spec prompt for `/specify`:**

```
Implement booklet-to-customer sales integration using ERPNext Sales Invoice.

Add to Purisol Settings a mandatory Link field "coupon_item" pointing to an
ERPNext Item. Create or document a setup step that creates this Item with UOM
"Booklet" and non-stock flag.

Implement a "Sell Booklets to Customer" UI (either a custom form or a prominent
action on the Coupon Booklet list view) that:
- Accepts a Customer (Link, required)
- Accepts a list of booklets (multi-select, filtered to "In Stock" or "In Custody")
- Optionally accepts a Price List (defaults to the customer's default Price List
  or to Purisol Settings.default_price_list)
- Creates an ERPNext Sales Invoice with one line per booklet, using the
  configured coupon_item and the selected Price List's rate
- Returns the user to the Sales Invoice draft for review before submit

Implement a Sales Invoice on_submit hook (via Frappe doc_events in hooks.py) that:
- For each line item whose item_code matches Purisol Settings.coupon_item and
  whose custom field "purisol_booklet" is set, updates the referenced booklet:
  - status = "Sold"
  - customer = invoice customer
  - sold_on = invoice posting_datetime
  - sales_invoice = invoice name
  - current_delivery_man = null (custody ends at sale)
- Raises ValidationError if any referenced booklet is not in a valid source state
  (In Stock or In Custody).

Implement a Sales Invoice on_cancel hook that reverses the booklet status change
(Sold -> In Stock, clears customer/sold_on/sales_invoice) ONLY if no coupons from
that booklet have been consumed yet. Otherwise raise ValidationError.

Do NOT implement consumption or discrepancy logic.

Include tests covering:
- Single-booklet sale end-to-end
- Multi-booklet single-invoice sale
- Selling from "In Custody" (delivery man field gets cleared)
- Selling from "In Stock"
- Rejection of selling an already-Sold booklet
- Price List selection (retail vs wholesale rates)
- Invoice cancellation behavior
```

**Estimated complexity:** Medium-high. The Sales Invoice integration has several edge cases (cancellation, amendment).

---

## Phase 4 — Consumption Recording (Without Discrepancy Detection)

**Goal:** Record coupons handed in by delivery men at end of day. Keep the logic simple; discrepancies come next phase.

**Prerequisites:** Phases 1, 2, 3.

**Scope (in):**
- `Purisol Coupon Consumption Entry` submittable DocType + child table
- Dual input UI: Mode A (pick from booklet checklist) and Mode B (enter coupon numbers directly)
- Blocking validations only (duplicate coupon, already consumed, non-existent)
- Coupon status transition: `Available` → `Consumed`
- Coupon metadata population: `consumed_on`, `consumed_by_delivery_man`, `consumption_entry`
- Booklet aggregates update: `consumed_count`, `remaining_count`
- Automatic booklet depletion: `Sold` → `Depleted` when all 20 consumed, plus `depleted_on` timestamp

**Scope (out):** Discrepancy detection (gap in sequence, unassigned booklet) — deferred to Phase 5. Notifications — deferred to Phase 6.

**Key acceptance criteria:**
- Both input modes work and produce the same underlying child-table rows.
- Submit marks all listed coupons as `Consumed` with correct metadata.
- Attempting to submit a duplicate or already-consumed coupon blocks the submit with a clear error.
- When the 20th coupon of a booklet is consumed, the booklet auto-transitions to `Depleted`.
- All updates happen in a single transaction: if any coupon fails validation, none are marked consumed.

**Spec prompt for `/specify`:**

```
Implement end-of-day coupon consumption recording.

Create the Purisol Coupon Consumption Entry submittable DocType with fields per
PRD section 7.4, including the Purisol Coupon Consumption Item child table.

Build the consumption entry form UI with dual input modes as described in PRD
section 12.1:
- Mode A (By Booklet): user enters a booklet number, system fetches all
  Available coupons in that booklet, user ticks which ones to record.
- Mode B (By Coupon Number): user enters coupon numbers directly; system
  auto-populates booklet and customer for each row.

Both modes write into the same child table.

On submit, implement BLOCKING validations only (no discrepancy detection in
this phase):
- Each listed coupon exists in the system.
- No coupon appears twice in the same entry.
- No coupon is already in status "Consumed".

If all validations pass, within a single transaction:
- Set each coupon's status to "Consumed".
- Set consumed_on = entry posting_datetime, consumed_by_delivery_man =
  entry delivery_man, consumption_entry = entry name.
- For each affected booklet, recompute consumed_count and remaining_count.
- If a booklet's consumed_count reaches 20, transition it to "Depleted" and set
  depleted_on = now().

Do NOT implement discrepancy detection (missing coupons, unassigned booklet) —
those are Phase 5. Do NOT implement notifications — those are Phase 6.

Include tests covering:
- Mode A end-to-end (enter booklet, pick coupons, submit)
- Mode B end-to-end (enter coupons directly, submit)
- Blocking on duplicate coupon in same entry
- Blocking on already-consumed coupon
- Booklet auto-depletion when all 20 consumed
- Transactional integrity: a failed validation rolls back all changes
```

**Estimated complexity:** High. The UI with dual modes is the main effort.

---

## Phase 5 — Discrepancy Detection & Resolution

**Goal:** Add the system's "intelligence" — detect anomalies in consumption entries and route them through a proper financial resolution flow.

**Prerequisites:** Phase 4.

**Scope (in):**
- `Purisol Coupon Discrepancy` submittable DocType + child tables
- Auto-detection logic hooked into Consumption Entry submit:
  - `Missing Coupons` (gap in booklet's consumption sequence)
  - `Unassigned Booklet` (coupon from a booklet whose status is not `Sold`)
- `related_delivery_men` auto-population
- Resolution workflow with three paths:
  - `Admin Error` → no financial consequence
  - `Delivery Man Liable` → auto-creates Journal Entry
  - `Paid` → auto-creates Payment Entry
- "Open Discrepancies" list view
- UI warning dialog on Consumption Entry submit when discrepancies are created

**Scope (out):** Notifications — still Phase 6. Reports — Phase 7.

**Key acceptance criteria:**
- Submitting consumed coupons 7, 8 when 3–6 are still Available creates a `Missing Coupons` discrepancy listing coupons 3, 4, 5, 6.
- Submitting a coupon from a booklet with status ≠ `Sold` creates an `Unassigned Booklet` discrepancy.
- Resolving `Delivery Man Liable` creates a valid Journal Entry visible in standard ERPNext financial reports.
- Resolving `Paid` creates a valid Payment Entry.
- Once resolved, the discrepancy record cannot be edited.

**Spec prompt for `/specify`:**

```
Add discrepancy detection and resolution to the Purisol consumption flow.

Create the Purisol Coupon Discrepancy submittable DocType with all fields and
child tables per PRD section 7.5.

Extend the Purisol Coupon Consumption Entry on_submit logic (from Phase 4) to
detect discrepancies as warnings (non-blocking):

1. UNASSIGNED BOOKLET: for each coupon whose parent booklet has status != "Sold",
   create a Purisol Coupon Discrepancy with discrepancy_type = "Unassigned Booklet",
   linked to that coupon and its booklet, status = "Open".

2. MISSING COUPONS: for each distinct booklet touched by the consumption entry,
   compute the union of (previously-consumed coupons) + (coupons being consumed
   now). If this set has any gap between its min and max (e.g. {1, 2, 7, 8}
   missing {3, 4, 5, 6} when those are still Available), create a Purisol Coupon
   Discrepancy with discrepancy_type = "Missing Coupons", listing the missing
   coupon numbers in the affected_coupons child table.

On each created discrepancy, auto-populate related_delivery_men with:
- The booklet's current_delivery_man (if still in custody) tagged as "Custody Holder"
- Every delivery man who submitted coupons from this booklet in the last 30 days,
  tagged as "Submitted Adjacent Coupons" with reference to their consumption entry

After consumption entry submit succeeds with warnings, set has_warnings = True,
populate the discrepancies_detected child table on the entry (linking to created
Discrepancy records), and display a modal dialog to the user summarizing the
discrepancies created.

Implement discrepancy resolution per PRD section 8.6:
- On Discrepancy submit with resolution_action = "None" (Admin Error): set
  status = "Resolved - Admin Error", set resolved_on. No financial entry.
- On Discrepancy submit with resolution_action = "Add to Liability Ledger":
  require liable_delivery_man set. Create a Journal Entry with:
    Debit: Purisol Settings.employee_liability_account,
           party_type = "Employee", party = liable_delivery_man
    Credit: Purisol Settings.discrepancy_offset_account
    Amount: estimated_amount
  Link the created JE back to the discrepancy. Set status = "Resolved - Delivery
  Man Liable", resolved_on.
- On Discrepancy submit with resolution_action = "Immediate Cash Payment":
  require liable_delivery_man set. Create a Payment Entry (receive type) with:
    Paid From: Purisol Settings.discrepancy_offset_account
    Paid To: Purisol Settings.default_cash_account
    Amount: estimated_amount
    Reference: the discrepancy
  Set status = "Resolved - Paid", resolved_on.

Once submitted, the discrepancy is locked per standard ERPNext submittable-doc
semantics.

Include tests covering:
- Missing coupons detection (gap in sequence across multiple entries)
- Unassigned booklet detection
- Both detections happening in a single consumption entry
- Each of the three resolution paths, verifying correct JE/PE creation
- Locked-after-submit behavior
```

**Estimated complexity:** High. The missing-coupons gap-detection logic across multiple entries is non-trivial.

---

## Phase 6 — Notifications

**Goal:** Proactive alerts to the Administrator.

**Prerequisites:** Phases 1–5.

**Scope (in):**
- Four notification triggers:
  1. Customer Low Stock (after Consumption Entry submit)
  2. New Discrepancy (after Discrepancy creation)
  3. Warehouse Low Stock (after Sales Invoice submit)
  4. Booklet Depleted (when status transitions to `Depleted`)
- Delivery via ERPNext Notification framework (bell icon)
- Configurable thresholds in Purisol Settings
- Abstraction layer so future channels (email, SMS) can plug in without rewriting triggers

**Scope (out):** Email, WhatsApp, SMS channels.

**Key acceptance criteria:**
- Each trigger fires exactly once per qualifying event.
- Thresholds are live-editable from Purisol Settings without code changes.
- Notifications appear in the bell icon dropdown with correct content and a link to the relevant record.

**Spec prompt for `/specify`:**

```
Implement in-system notifications for Purisol.

Create a small abstraction "Purisol Notify" utility (a Python module, not a
DocType) that exposes a single send() function. The function accepts:
- recipient (User or Role)
- subject (short string)
- message (formatted HTML or plain text)
- reference_doctype, reference_name (for click-through)

In this phase, send() creates an ERPNext Notification Log entry (bell icon).
The abstraction exists so a future phase can add email/SMS without changing
the trigger sites.

Implement four notification triggers per PRD section 10:

1. CUSTOMER LOW STOCK
   Trigger: Purisol Coupon Consumption Entry on_submit, after all coupons and
   booklets are updated.
   Condition: for each unique customer among affected booklets, compute total
   remaining_count across all their Sold (not Depleted) booklets. If total <=
   Purisol Settings.customer_low_stock_threshold, send notification.
   Message: "Customer {name} has {N} coupons remaining. Prepare a new booklet."
   Recipient: all users with "Purisol Administrator" role.

2. NEW DISCREPANCY OPENED
   Trigger: Purisol Coupon Discrepancy after_insert.
   Condition: always.
   Message: "Discrepancy {name} opened: {type} involving booklet {booklet} /
   delivery man {delivery_man}."
   Recipient: Administrator role.

3. WAREHOUSE LOW STOCK
   Trigger: Sales Invoice on_submit, after booklet status updates.
   Condition: count of Purisol Coupon Booklets with status "In Stock" <
   Purisol Settings.warehouse_low_stock_threshold. Deduplicate: only fire once
   per day regardless of how many invoices cross the threshold.
   Message: "Only {N} booklets remain in stock. Generate a new batch."
   Recipient: Administrator role.

4. BOOKLET DEPLETED
   Trigger: when a booklet transitions to "Depleted" (emitted from the
   consumption entry logic, not as a doc hook, to ensure we have context).
   Condition: always.
   Message: "Booklet {name} for customer {customer} is fully consumed. Follow
   up for resale."
   Recipient: Administrator role.

Include tests covering:
- Each trigger firing under the right conditions
- Each trigger NOT firing when conditions are not met
- Threshold changes in Purisol Settings taking effect immediately
- Warehouse low-stock deduplication within a single day
```

**Estimated complexity:** Low-medium. Triggers are straightforward; the dedup logic for warehouse low-stock needs care.

---

## Phase 7 — Reports

**Goal:** All reports listed in the PRD, delivered as standard ERPNext Report Builder / Query / Script reports.

**Prerequisites:** Phases 1–5 (notifications not strictly required, but helpful).

**Scope (in):**
- **Operational reports (4):** Daily Delivery Man Summary, Active Booklets per Customer, Current Custody by Delivery Man, Coupon Consumption Log
- **Financial/oversight reports (4):** Delivery Man Discrepancies, Delivery Man Liability Balance, Booklet Sales, Discrepancy Rate by Delivery Man
- **Analytical reports (2):** Customer Consumption Rate, Booklet Lifecycle Duration
- All reports support standard ERPNext filters, export to Excel/PDF

**Note on splitting this phase:** If you prefer smaller specs, you can split this into three sub-phases (Operational, Financial, Analytical) — each as its own `/specify` branch. They're independent of each other.

**Key acceptance criteria:**
- Each report returns accurate data verified against small manually-constructed test datasets.
- Filters work correctly (date ranges, delivery man, customer, etc.).
- Reports are accessible from the ERPNext menu under a "Purisol" section.

**Spec prompt for `/specify`:**

```
Implement all Purisol reports per PRD section 11 (10 reports total).

For each report listed below, create an ERPNext Script Report or Query Report
(use Query Report for simple SELECTs, Script Report when Python aggregation
is needed):

OPERATIONAL:
1. Daily Delivery Man Summary — filters: date, delivery_man. Columns: delivery
   man, coupons submitted count, booklets touched count, discrepancies count,
   discrepancy total value.
2. Active Booklets per Customer — filters: customer. Columns: customer, booklet
   number, status, consumed_count, remaining_count, sold_on, days since sale.
3. Current Custody by Delivery Man — filters: delivery_man. Columns: delivery
   man, booklet number, days in custody, customer (if sold, else blank).
4. Coupon Consumption Log — filters: date range, delivery_man, customer,
   booklet. Columns: consumed_on, coupon number, booklet, customer, delivery
   man, consumption entry ref.

FINANCIAL / OVERSIGHT:
5. Delivery Man Discrepancies — filters: date range, delivery_man, status.
   Columns: discrepancy ID, opened_on, type, booklet, coupons count, amount,
   status, resolution.
6. Delivery Man Liability Balance — filters: delivery_man. Columns: delivery
   man, total owed (sum of liability JEs), total paid (sum of Payment Entries
   against liability), open balance. Data source: ERPNext GL entries for the
   employee_liability_account.
7. Booklet Sales — filters: date range, customer, price list. Columns: sold_on,
   booklet, customer, sales invoice ref, amount, invoice status.
8. Discrepancy Rate by Delivery Man — filters: date range. Columns: delivery
   man, coupons submitted, discrepancies count, discrepancy rate %, total
   discrepancy value.

ANALYTICAL:
9. Customer Consumption Rate — no filters. Columns: customer, average days
   between booklet purchase and full depletion, based on all their Depleted
   booklets.
10. Booklet Lifecycle Duration — no filters. Columns: average days from
    generation to first sale, from sale to depletion, and full lifetime.

All reports must:
- Appear under a "Purisol" group in the ERPNext Reports menu.
- Support standard filters UI.
- Allow export to Excel and PDF via built-in Frappe actions.
- Include inline sanity tests: each report's query returns expected rows
  against a seeded test dataset.

Include automated tests that seed a small, deterministic dataset and assert
each report's output.
```

**Estimated complexity:** Medium. Volume of work, not conceptual difficulty.

---

## Phase 8 — Dashboard

**Goal:** A single landing view that surfaces what the Administrator needs to see every morning.

**Prerequisites:** Phases 1–7.

**Scope (in):**
- Purisol Dashboard (ERPNext Dashboard or custom Workspace) with the 8 widgets listed in PRD section 11.4
- Each widget links through to the relevant list view or report

**Scope (out):** Charts beyond what ERPNext dashboard widgets offer natively. Custom HTML dashboards are deferred.

**Key acceptance criteria:**
- All 8 widgets render with accurate live data.
- Each widget is clickable and routes to the correct list/report.
- Dashboard is set as the default landing page for the Purisol Administrator role.

**Spec prompt for `/specify`:**

```
Create the Purisol Dashboard as an ERPNext Workspace.

Add a new Workspace named "Purisol" with the following Dashboard Chart / Number
Card / Shortcut widgets per PRD section 11.4:

1. Number Card: Booklets In Stock — count of Coupon Booklets with status =
   "In Stock". Click-through to the filtered list.
2. Number Card: Booklets In Custody — count of Coupon Booklets with status =
   "In Custody". Include a secondary breakdown (dashboard chart) showing
   count per current_delivery_man.
3. Number Card: Active Sold Booklets — count with status = "Sold".
4. List widget: Customers Low on Coupons — top 10 customers whose total
   remaining across Sold booklets <= threshold.
5. Number Card + List: Open Discrepancies — count and top 5 by opened_on desc.
   Card uses color coding (red if > 0, green if 0).
6. Number Card: Outstanding Delivery Man Liabilities — total amount owed
   across all delivery men (from GL balance of liability account).
7. Dashboard Chart: Today's Consumption — bar chart of coupons recorded
   today grouped by delivery_man.
8. List: Recent Depleted Booklets — last 7 days, showing booklet, customer,
   depleted_on.

Set this Workspace as the default landing page for users with the Purisol
Administrator role.

Include tests that verify each widget's query returns correct data against a
seeded dataset.
```

**Estimated complexity:** Low-medium. Mostly configuration; the delivery-man-liability widget needs a real GL query.

---

## Cross-Phase Guidance

### Recommended order of work

1. **Phase 0** (Constitution) — half a day.
2. **Phases 1–5** — strictly sequential. Each phase ends with a working, tested system that delivers more capability.
3. **Phases 6, 7, 8** — can be done in any order; Phase 6 provides the most immediate user value, so recommended next.

### When to re-run `/clarify` vs `/specify`

If, during implementation of a phase, you discover a requirement you hadn't captured: prefer running `/clarify` on the existing spec to add the detail. Only run `/specify` again if you're introducing a genuinely new feature area.

### Handling the PRD as the source of requirements

The PRD is the long-form reference. When running `/specify` for a phase, keep the spec prompt focused on what that phase needs — don't paste the full PRD into the prompt. The constitution ensures cross-cutting concerns (naming, state machines, audit) are already enforced; the spec only needs to say what's unique to this phase.

### Using `/analyze` as a quality gate

After `/plan` and `/tasks` for each phase, run `/analyze` to check that:
- The plan respects the constitution.
- No tasks contradict prior-phase specs.
- Dependencies are declared correctly.

### Test data seeding

Phase 1 should include a `setup_test_data` helper that creates a deterministic seed (N customers, M delivery men, K booklets in known states). Later phases can reuse this seed — each phase's tests extend it rather than redefining it.

### What a finished MVP looks like

After all 8 phases ship, the shop owner can:
- Generate booklets in batches.
- Hand booklets to delivery men, move them between delivery men, take them back.
- Sell booklets with proper invoices and pricing.
- Record daily consumptions efficiently.
- See discrepancies flagged and resolve them with real financial consequences.
- Receive timely alerts when customers run low or discrepancies open.
- Open any of 10 reports for operational, financial, or analytical insights.
- Land on a dashboard every morning showing the health of the business at a glance.

---

## Appendix — Spec-Kit Command Cheat Sheet

For each phase (after the constitution is set):

```bash
# 1. Start the feature branch
/specify "<paste the spec prompt for the phase>"

# 2. Clarify any ambiguities the agent raises
/clarify

# 3. Produce the technical plan
/plan

# 4. Break into tasks
/tasks

# 5. Validate against constitution and prior specs
/analyze

# 6. Implement
/implement
```

Each phase runs this loop independently on its own branch. When the phase is done and merged, the next phase starts from the updated main branch.
