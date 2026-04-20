# Feature Specification: Reports

**Feature Branch**: `007-reports`
**Created**: 2026-04-19
**Status**: Draft
**Input**: User description: "Phase 7 — Reports from '/home/corex/aurevia-bench/apps/cx_purisol/docs/plan.md', for full context check '/home/corex/aurevia-bench/apps/cx_purisol/docs/prd.md'"

## User Scenarios & Testing *(mandatory)*

The Purisol Administrator is the sole user of these reports. They use them daily to run operations, weekly to oversee finances and delivery-man behaviour, and monthly to plan future booklet generation and customer outreach. Reports are grouped into three independently shippable bundles by purpose. Within each bundle the individual reports share the same data sources, filter conventions, and export behaviour, so they are best built as a single increment — but the bundles themselves can be shipped in any order.

### User Story 1 - Operational Reports for Daily Running of the Business (Priority: P1)

The Administrator opens the system each morning and at end of day to answer "what happened today, who has what, and where do my coupons stand?". They need four reports that surface coupon-flow, custody-state, and consumption activity at a glance, filterable by date, delivery man, customer, and booklet.

**Why this priority**: These reports are used every working day. Without them the Administrator cannot reconcile end-of-day deliveries, cannot tell which delivery man holds which booklet, and cannot answer customer inquiries like "how many coupons do I have left?". They unlock the routine operational value of every prior phase.

**Independent Test**: Seed a small dataset (a handful of customers, delivery men, booklets, custody movements, and consumption entries spanning two days), open each of the four operational reports with realistic filter combinations, and verify every row, column, and filter behaves as documented. Bundle is shippable on its own — the financial and analytical bundles are not required for day-to-day operations.

**Acceptance Scenarios**:

1. **Given** a delivery man submitted three consumption entries today covering eight coupons across two booklets, with one entry creating a discrepancy worth a non-zero amount, **When** the Administrator opens the Daily Delivery Man Summary filtered to today and that delivery man, **Then** the report shows one row with coupons-submitted = 8, booklets-touched = 2, discrepancies-count = 1, and a discrepancy total matching the discrepancy's estimated amount.
2. **Given** a customer owns three Sold booklets — one with 20/20 consumed (now Depleted), one with 12/20 consumed, and one with 0/20 consumed, **When** the Administrator opens Active Booklets per Customer filtered to that customer, **Then** the report lists all three booklets with their correct status, consumed/remaining counts, sold-on date, and a days-since-sale value derived from today.
3. **Given** delivery man A holds two booklets in custody (one assigned 5 days ago, one transferred from delivery man B 1 day ago) and delivery man B holds zero, **When** the Administrator opens Current Custody by Delivery Man, **Then** delivery man A appears with both booklets listed and correct days-in-custody (5 and 1), and delivery man B does not appear.
4. **Given** a date range spanning a week with twelve consumption entries totalling forty coupons across three customers and four delivery men, **When** the Administrator opens the Coupon Consumption Log filtered to that range, **Then** the report returns exactly forty rows — one per consumed coupon — with correct date, coupon number, booklet, customer, delivery man, and a click-through reference to the originating consumption entry.
5. **Given** any of the four operational reports has been run, **When** the Administrator clicks "Export to Excel" or "Export to PDF", **Then** the file downloads with the same rows and columns currently displayed and respects the active filter values.

---

### User Story 2 - Financial & Oversight Reports for Weekly Review (Priority: P2)

The Administrator periodically reviews delivery-man behaviour and the cash position arising from discrepancies. They need four reports that aggregate discrepancy events, the running liability balance per delivery man, all booklet-driven sales, and a rate metric that surfaces problem performers.

**Why this priority**: These reports are essential for financial control and accountability but are consulted less frequently than operational reports — typically weekly or whenever a specific concern arises. The business can run for short periods without them, but would lose money over time without the liability and discrepancy-rate views.

**Independent Test**: Seed a dataset with at least two delivery men, several discrepancies in different resolution states (Open, Admin Error, Liable, Paid), the corresponding Journal Entries and Payment Entries against the configured liability account, and a handful of Sales Invoices for booklets at different price points. Open each financial/oversight report with appropriate filters and verify totals tie back to the seed.

**Acceptance Scenarios**:

1. **Given** delivery man A has three open discrepancies (two Missing Coupons totalling a known amount, one Unassigned Booklet) and delivery man B has one resolved-Paid discrepancy, **When** the Administrator opens Delivery Man Discrepancies for the date range that covers both, **Then** all four discrepancies appear with correct ID, opened-on date, type, booklet, coupons count, amount, status, and resolution path.
2. **Given** delivery man A has accumulated liability through two resolved-Liable discrepancies (totals known) and has made one cash payment that partially offset that liability, **When** the Administrator opens Delivery Man Liability Balance filtered to delivery man A, **Then** the report shows total-owed equal to the sum of the liability journal entries, total-paid equal to the payment, and an open-balance equal to owed minus paid — with figures sourced from the general ledger of the configured liability account.
3. **Given** seven Sales Invoices were submitted in a date range covering three customers across two price lists, **When** the Administrator opens the Booklet Sales Report for that date range filtered to one of those price lists, **Then** only the matching invoices appear with sale date, booklet, customer, invoice reference, amount, and invoice status.
4. **Given** delivery man A submitted 100 coupons in a month with 4 discrepancies and delivery man B submitted 50 coupons with 0 discrepancies, **When** the Administrator opens Discrepancy Rate by Delivery Man for that month, **Then** A appears with rate 4% and a non-zero total discrepancy value, B appears with rate 0% and zero discrepancy value, and both rows show the underlying counts that produced the rate.
5. **Given** any financial report is open, **When** the Administrator changes a filter value (e.g. delivery man) and re-runs the report, **Then** the visible rows and any totals update to reflect the new filter without requiring a full page reload.

---

### User Story 3 - Analytical Reports for Planning & Forecasting (Priority: P3)

The Administrator wants to predict when each customer will need a new booklet and to size future generation batches based on how long booklets actually take to flow through the system. Two analytical reports surface these averages.

**Why this priority**: These reports inform planning rather than daily operation. Their absence does not prevent the business from functioning, but their presence reduces stockouts at customers and avoids over- or under-generating booklets at the warehouse.

**Independent Test**: Seed a deterministic dataset where multiple booklets have completed their full lifecycle (generated → custody → sold → fully consumed) at known dates so each duration is calculable by hand. Open both analytical reports and verify the averages match the expected hand-calculated values.

**Acceptance Scenarios**:

1. **Given** customer C1 has three Depleted booklets where the days from purchase to depletion were 30, 45, and 60, and customer C2 has two Depleted booklets where the days were 10 and 20, **When** the Administrator opens Customer Consumption Rate, **Then** C1 appears with an average of 45 days and C2 appears with an average of 15 days, and customers with no Depleted booklets do not appear (or appear with no average value).
2. **Given** a set of booklets whose generation, sale, and depletion timestamps are known, **When** the Administrator opens Booklet Lifecycle Duration, **Then** the report shows the average days from generation to first sale, average days from sale to depletion, and average full lifetime — each computed only over booklets that have reached the relevant terminal milestone.
3. **Given** the analytical reports are open, **When** the Administrator exports them to Excel or PDF, **Then** the export contains the same averages and any per-row breakdowns shown on screen.

---

### Edge Cases

- **Empty result set**: When a filter combination matches no records (e.g. a delivery man on a date they did not work), reports return zero rows with no error and a clear "no data" indicator.
- **Cancelled or amended source documents**: Sales Invoices, Consumption Entries, and Discrepancies that have been cancelled or amended must be excluded from totals and counts (only submitted, non-cancelled records contribute), so a cancelled invoice does not double-count an amended one.
- **Disabled employees and customers**: Historical records linked to a now-disabled delivery man or customer continue to appear in reports; the disabled status does not erase the audit trail.
- **Booklets with mid-lifecycle states**: Analytical reports compute averages only over booklets that have reached the relevant milestone (e.g. Booklet Lifecycle Duration's "sale to depletion" excludes booklets still in Sold status). In-flight booklets do not skew averages.
- **Discrepancies with no liable party assigned**: Open or Admin-Error discrepancies (no liable_delivery_man) appear in the discrepancy list but contribute zero to liability balances and to the per-delivery-man discrepancy rate.
- **Time-zone and "today" semantics**: Date filters interpret "today" using the server's configured time zone consistently across all reports.
- **Coupons consumed without a current custody assignment** (e.g. coupons handed in after the booklet was already Sold to a customer): the consumption log shows them with the correct delivery man on the consumption entry; custody-based reports do not falsely attribute custody.
- **Price-list filter on Booklet Sales Report when the invoice line was created via a custom override price**: the invoice's actual selling_price_list is the source of truth for the filter, not the customer's default.
- **Concurrent submissions during report run**: A consumption entry submitted while a report is rendering may or may not appear in that render; the next run reflects the latest data. Reports do not need to guarantee within-render consistency beyond standard database-snapshot semantics.
- **Liability ledger with zero-amount journal entries**: A discrepancy resolved with estimated_amount = 0 contributes zero to the liability balance but still appears in the discrepancies count.

## Requirements *(mandatory)*

### Functional Requirements

#### Discoverability & Common Behaviours

- **FR-001**: System MUST present all ten reports under a single "Purisol" group in the standard reports menu so the Administrator can locate them without navigating individual record types.
- **FR-002**: System MUST allow the Administrator to apply, change, and clear filters on each report and see results refresh accordingly.
- **FR-003**: System MUST allow each report's currently-displayed rows to be exported to both Excel and PDF using built-in actions, preserving column order, applied filter values, and row order.
- **FR-004**: System MUST restrict access to all ten reports to users holding the Purisol Administrator role; users without that role MUST NOT see the reports in the menu and MUST NOT be able to open them by direct URL.
- **FR-005**: System MUST exclude cancelled and superseded source documents (cancelled Sales Invoices, cancelled Consumption Entries, cancelled Discrepancies) from all counts, totals, and rate calculations across every report.
- **FR-006**: System MUST allow click-through from any row that references another record (booklet, customer, delivery man, consumption entry, sales invoice, discrepancy, journal entry, payment entry) to the underlying record's detail view.

#### Operational Reports (Bundle 1)

- **FR-010**: System MUST provide a Daily Delivery Man Summary report filterable by date and delivery man, with one row per (date, delivery man) showing coupons submitted, distinct booklets touched, discrepancies opened, and the sum of discrepancy estimated amounts attributable to that delivery man on that date.
- **FR-011**: System MUST provide an Active Booklets per Customer report filterable by customer, with one row per (customer, booklet) showing booklet number, status, consumed count, remaining count, sold-on date, and days since sale (computed against today).
- **FR-012**: System MUST provide a Current Custody by Delivery Man report filterable by delivery man, with one row per booklet currently in custody showing delivery man, booklet number, days in custody (computed from the latest custody movement), and the customer if the booklet is also Sold (otherwise blank).
- **FR-013**: System MUST provide a Coupon Consumption Log report filterable by date range, delivery man, customer, and booklet, with one row per consumed coupon showing the consumption date, coupon number, booklet, customer, delivery man, and a reference to the originating consumption entry.

#### Financial & Oversight Reports (Bundle 2)

- **FR-020**: System MUST provide a Delivery Man Discrepancies report filterable by date range, delivery man, and discrepancy status, with one row per discrepancy showing discrepancy ID, opened-on date, type, affected booklet, count of affected coupons, estimated amount, status, and resolution action.
- **FR-021**: System MUST provide a Delivery Man Liability Balance report filterable by delivery man, with one row per delivery man showing total owed (sum of liability journal entries against the configured employee-liability account, party = that delivery man), total paid (sum of payment entries that offset that liability), and open balance (owed minus paid). Figures MUST be sourced from the general ledger of the configured liability account, not from the discrepancy records directly.
- **FR-022**: System MUST provide a Booklet Sales Report filterable by date range, customer, and price list (the price list filter MUST match the actual price list recorded on the invoice), with one row per booklet line on a Sales Invoice showing sale date, booklet, customer, invoice reference, amount, and invoice status.
- **FR-023**: System MUST provide a Discrepancy Rate by Delivery Man report filterable by date range, with one row per delivery man showing coupons submitted in range, discrepancies count in range, discrepancy rate as a percentage (discrepancies count divided by coupons submitted, displayed as 0% if no coupons submitted), and total discrepancy estimated amount in range.

#### Analytical Reports (Bundle 3)

- **FR-030**: System MUST provide a Customer Consumption Rate report with one row per customer showing the average number of days between booklet purchase (sold-on) and full depletion (depleted-on), computed only over that customer's Depleted booklets. Customers with no Depleted booklets MUST either be omitted or shown with no average value (chosen consistently across rows).
- **FR-031**: System MUST provide a Booklet Lifecycle Duration report showing the average number of days from booklet generation to first sale (over all Sold or later booklets), from sale to depletion (over all Depleted booklets), and total lifetime from generation to depletion (over all Depleted booklets).

#### Data Integrity

- **FR-040**: Reports MUST use only the data already produced by Phases 1–6 (booklets, coupons, custody entries, sales invoices, consumption entries, discrepancies, journal entries, payment entries, and the existing settings); no new persistent data store is created for reporting.
- **FR-041**: Reports MUST update on each open/refresh to reflect the latest committed data; no manual rebuild step is required.

### Key Entities *(include if feature involves data)*

- **Coupon Booklet**: Source for status counts, customer attribution, sold-on / depleted-on timestamps, and consumed/remaining aggregates. Already established in prior phases.
- **Coupon**: Source for consumed-on, consumed-by-delivery-man, and originating-consumption-entry references used by the Coupon Consumption Log.
- **Custody Entry**: Source for days-in-custody calculations on the Current Custody report (the "latest custody movement" for a booklet).
- **Sales Invoice (and Sales Invoice Item)**: Source for the Booklet Sales Report; the line-level link from invoice item to booklet (established in Phase 3) is the join key. The invoice's recorded price list is the source of truth for the price-list filter.
- **Consumption Entry**: Source for daily summaries and consumption-volume metrics; supplies the per-day, per-delivery-man counts.
- **Discrepancy (and its child tables)**: Source for discrepancy counts, statuses, types, resolution paths, and per-discrepancy estimated amounts. The link from discrepancy to a liable delivery man is the join key for liability attribution.
- **General Ledger entries against the configured employee-liability account**: Source for the Delivery Man Liability Balance report. Owed = debits with party = delivery man; paid = credits / payments offsetting those debits. Sourcing from the GL (not the discrepancy records) ensures alignment with standard financial reports.
- **Customer**: Reference data for grouping/filtering; appears as a column or filter on multiple reports.
- **Employee (delivery man)**: Reference data for grouping/filtering; appears as a column or filter on multiple reports.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An Administrator can open any of the ten reports from the menu and see results within 3 seconds against a dataset of up to 10,000 coupons, 500 booklets, 50 delivery men, and 200 customers.
- **SC-002**: 100% of seeded test scenarios across the three bundles produce the expected rows, columns, totals, and rates exactly as documented in the acceptance scenarios.
- **SC-003**: Every figure on the Delivery Man Liability Balance report matches the corresponding standard general-ledger report for the configured liability account, with zero discrepancy across all delivery men, on the same dataset.
- **SC-004**: An Administrator can answer each of the following questions in under 30 seconds using the appropriate report: "What did delivery man X do today?", "How many coupons does customer Y have left?", "Who currently holds booklet Z?", "What does delivery man X owe me?".
- **SC-005**: All ten reports correctly exclude cancelled source documents — verified by cancelling a representative document of each type (Sales Invoice, Consumption Entry, Discrepancy) and confirming the affected report row(s) and totals adjust accordingly within one refresh.
- **SC-006**: Excel and PDF exports of any open report produce a file whose row count, column order, and visible filter values match what is on screen at the moment of export, across all ten reports.
- **SC-007**: Each of the three bundles (Operational, Financial, Analytical) can be released independently to users without depending on the other two bundles being present.

## Assumptions

- The Administrator role and its assignment to users already exists from earlier phases; no new role is introduced here.
- The "Purisol" reports menu group either already exists or will be created in this phase; no other apps need to coordinate naming.
- The existing settings already record the employee-liability account, the discrepancy offset account, and the default cash account from prior phases — these are the accounts the liability balance and discrepancy reports use.
- "Days since sale", "days in custody", "days from generation to first sale", and similar duration fields are computed in whole days from timestamps in the server's configured time zone. Sub-day precision is not required.
- "Days in custody" is measured from the latest custody movement that placed the booklet with its current holder, not from the original first assignment.
- The "discrepancy total value" attributed to a delivery man on the Daily Delivery Man Summary uses the discrepancy's estimated amount and counts the discrepancy against the delivery man whose consumption entry triggered it (not necessarily against any later-assigned liable_delivery_man, which may not yet exist when the report is run).
- The Discrepancy Rate by Delivery Man uses coupons submitted by that delivery man in the period (denominator) and discrepancies opened by that delivery man's consumption entries in the period (numerator). A delivery man with zero coupons submitted in the period appears with rate 0% rather than producing a divide-by-zero.
- Reports run live against the operational database at each open/refresh; no separate reporting warehouse, materialised view, or scheduled cache is introduced in this phase.
- The Excel and PDF export capability is provided by the standard reports framework already used by the host platform; no custom export pipeline is required.
- Notifications (Phase 6) are not a prerequisite for any report's logic; they are helpful context but the reports operate independently.
- The dashboard view (Phase 8) is out of scope for this phase; it will consume some of these reports later but is not delivered here.
- Mobile-specific report layouts are out of scope; reports use the standard responsive list/report views provided by the host platform.
- Historical edits to source documents (e.g. amending a submitted Sales Invoice via the standard amendment flow) are handled by relying on the platform's standard "submitted, non-cancelled" filter — the amended replacement is the version reflected in reports, the cancelled original is excluded.
