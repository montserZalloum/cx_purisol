# Feature Specification: Dashboard

**Feature Branch**: `008-dashboard`
**Created**: 2026-04-19
**Status**: Draft
**Input**: User description: "Phase 8 — Dashboard from '/home/corex/aurevia-bench/apps/cx_purisol/docs/plan.md', for full context check '/home/corex/aurevia-bench/apps/cx_purisol/docs/prd.md'"

## User Scenarios & Testing *(mandatory)*

The Purisol Administrator is the sole user of this dashboard. Every morning they log into the system and need a single landing view that answers, within a few seconds: "Is my supply chain healthy, is anyone putting my cash at risk, and which customers should I follow up with today?". The dashboard concentrates the answers into eight widgets, grouped by purpose, each one clickable through to the detailed list or report the Administrator would otherwise need to navigate to manually. The feature ships as three independently deliverable widget groups, each of which on its own improves the morning routine meaningfully.

### User Story 1 - Morning Operational Health View (Priority: P1)

The Administrator opens the system and lands automatically on the Purisol dashboard. Without any navigation, they see how many unsold booklets are on the shelf, how many are out with delivery men (and which delivery man holds how many), how many are actively with paying customers, and a visualisation of the coupons handed in so far today, broken down by delivery man. Each figure or bar is clickable to drill into the underlying records.

**Why this priority**: This is the daily morning ritual the dashboard exists to support. Without it, the Administrator must navigate through multiple list views and reports to reconstruct the current state of the business, which defeats the point of having a dashboard at all. Shipping this bundle alone — even before the risk and follow-up widgets — already replaces five to ten minutes of manual navigation with a single glance.

**Independent Test**: Seed a small dataset (a handful of booklets across the three active statuses, a few delivery men each holding some booklets, several consumption entries dated today from different delivery men), log in as a user holding the Purisol Administrator role, and verify the dashboard loads automatically, every operational widget reflects the seeded counts, the in-custody breakdown matches per-delivery-man ownership, and today's consumption bars sum to the total coupons recorded today. Bundle is shippable on its own — the financial and follow-up bundles are not required to deliver the morning-glance value.

**Acceptance Scenarios**:

1. **Given** a user holds the Purisol Administrator role and has not previously set a personal landing preference, **When** that user logs into the system, **Then** they land on the Purisol dashboard without any additional navigation.
2. **Given** 17 booklets are In Stock, 42 are In Custody across three delivery men (A=20, B=15, C=7), and 120 are Sold (not yet Depleted), **When** the Administrator views the dashboard, **Then** the three operational number widgets show exactly 17, 42, and 120 respectively, and the In-Custody breakdown visualisation shows three segments for A, B, and C with their correct counts.
3. **Given** four delivery men each submitted consumption entries today totalling 8, 12, 3, and 0 coupons respectively, **When** the Administrator views the dashboard, **Then** the "Today's Consumption" visualisation shows bars for the three delivery men with non-zero counts (8, 12, 3), and either omits the zero-count delivery man or shows a zero-length bar — but the sum of visualised bars equals the 23 coupons recorded today.
4. **Given** the Administrator is viewing the dashboard, **When** they click the "Booklets In Stock" widget, **Then** they are taken to the Coupon Booklet list filtered to status = "In Stock"; likewise "Booklets In Custody" filters to "In Custody", "Active Sold Booklets" filters to "Sold", and the "Today's Consumption" visualisation links through to today's consumption entries.
5. **Given** no booklets exist yet in the system and no consumption entries have been recorded today, **When** the Administrator views the dashboard, **Then** every operational widget renders without error, shows zero counts or an empty visualisation as appropriate, and no broken or missing widget is displayed.

---

### User Story 2 - Financial Risk Watchlist (Priority: P2)

The Administrator must see, at a glance, whether any discrepancy investigations are open and how much money is currently owed to the shop by delivery men. Two widgets surface this: an Open Discrepancies widget that shows the current count with colour-coded severity and a short list of the most recently opened items, and an Outstanding Delivery Man Liabilities widget that shows the total amount owed across all delivery men along with a per-delivery-man breakdown.

**Why this priority**: Discrepancies and unpaid liabilities are the principal financial exposures of the operation. Missing them costs real money over time. But the business can run for a day or two without this view — the underlying discrepancy list and liability report (from the prior reports phase) are still reachable manually. So this bundle is critical, but not blocking for the first-shippable version of the dashboard.

**Independent Test**: Seed a dataset with at least two open discrepancies of different types and opened dates, one resolved-Liable discrepancy that produced a known liability entry, and one resolved-Paid discrepancy that offset part of that liability. Open the dashboard, verify the Open Discrepancies widget shows a count of 2 with the correct colour and lists the two open items most-recent-first, and verify the Outstanding Liabilities widget shows a total equal to the unpaid portion and a per-delivery-man breakdown matching the ledger.

**Acceptance Scenarios**:

1. **Given** three discrepancies are currently in status "Open" (opened on three different dates) and one is resolved, **When** the Administrator views the dashboard, **Then** the Open Discrepancies widget shows count = 3, displays visual severity colouring that clearly distinguishes "there is work to do" from "nothing to do", and the accompanying short list shows up to the five most recently opened discrepancies ordered newest-first.
2. **Given** zero discrepancies are currently in status "Open", **When** the Administrator views the dashboard, **Then** the Open Discrepancies widget shows count = 0 with visual severity colouring that clearly indicates a healthy state, distinct from the count-greater-than-zero state.
3. **Given** delivery man A has accumulated liability of a known amount through resolved-Liable discrepancies and has paid back part of it, and delivery man B has accumulated a smaller liability with no payments, **When** the Administrator views the dashboard, **Then** the Outstanding Liabilities widget shows a total equal to A's unpaid portion plus B's full liability, and a per-delivery-man breakdown listing both A and B with their respective outstanding balances.
4. **Given** the Administrator is viewing the dashboard, **When** they click the Open Discrepancies widget (count, an item in the list, or the widget itself), **Then** they are taken to the discrepancies list filtered to status = "Open" (or to the specific discrepancy record when clicking one of the listed items), and likewise clicking Outstanding Liabilities or a per-delivery-man row takes them to the corresponding liability view for that scope.
5. **Given** no discrepancies have ever been created and no liability journal entries exist, **When** the Administrator views the dashboard, **Then** both widgets render with zero values, the Open Discrepancies widget shows the healthy-state colour, and no broken or missing widget is displayed.

---

### User Story 3 - Customer Follow-up Signals (Priority: P3)

The Administrator uses the dashboard to drive proactive customer outreach: spotting customers whose total remaining coupons have dropped near empty (so a new booklet can be sold before they run out), and reviewing booklets that have just been fully consumed (so the customer can be contacted about resale). Two list widgets surface these signals directly on the dashboard.

**Why this priority**: These signals sharpen the sales follow-up cadence but do not prevent operations from running. Both underlying data points are already available via the prior reports phase; the dashboard widgets exist so the Administrator does not have to open a separate report to notice them. The value is incremental — the business already functions without these widgets, but adding them measurably reduces missed resale opportunities.

**Independent Test**: Seed a dataset with several customers whose total remaining coupons (across all their Sold booklets) span above, at, and below the configured low-stock threshold, and several booklets that transitioned to Depleted on dates within and outside the last seven days. Open the dashboard and verify the low-stock widget lists up to ten customers whose totals are at or below threshold ordered lowest-first, and the depleted-booklets widget lists only booklets depleted within the last seven days with booklet, customer, and depletion date.

**Acceptance Scenarios**:

1. **Given** the configured customer low-stock threshold is three and five customers have totals of 0, 1, 2, 3, and 4 remaining coupons respectively across their Sold booklets, **When** the Administrator views the dashboard, **Then** the Customers Low on Coupons widget lists exactly four customers (those with totals 0, 1, 2, 3 — at or below the threshold), ordered with the lowest remaining first, and excludes the customer with 4 remaining.
2. **Given** more than ten customers are at or below the low-stock threshold, **When** the Administrator views the dashboard, **Then** the widget lists at most ten customers — the ten with the lowest remaining totals — and makes clear that additional qualifying customers exist beyond the displayed list.
3. **Given** three booklets transitioned to Depleted within the last seven days (on different dates and for different customers) and two transitioned to Depleted more than seven days ago, **When** the Administrator views the dashboard, **Then** the Recent Depleted Booklets widget lists exactly the three recent ones with their booklet number, customer name, and depletion date, and excludes the two older depletions.
4. **Given** the Administrator is viewing the dashboard, **When** they click a customer in the low-stock list, **Then** they are taken to that customer's record or filtered booklet list; and when they click a depleted-booklet row, they are taken to that specific booklet's detail view.
5. **Given** no customer is at or below the low-stock threshold and no booklet has been depleted in the last seven days, **When** the Administrator views the dashboard, **Then** both widgets render with an empty-state indicator (not an error), the rest of the dashboard continues to display its other widgets normally, and no broken or missing widget is displayed.

---

### Edge Cases

- **Empty system on first install**: The dashboard loads cleanly with every widget showing its zero or empty state; no widget fails to render because there are no records yet.
- **User without the Administrator role**: The dashboard is inaccessible — neither surfaced in menus nor reachable by direct URL — and the user's landing page is whatever the platform default is for their role.
- **User has manually set a personal home preference**: The dashboard is still reachable, but the user's own preference wins over the Administrator-role default landing.
- **Disabled delivery man still holding a booklet**: The custody breakdown continues to attribute the booklet to that (disabled) delivery man so the audit picture is accurate; the disabled flag does not remove them from the chart.
- **Delivery man with zero or negative outstanding balance**: Appears in the per-delivery-man liability breakdown only when their balance is greater than zero; the overall total ignores negative balances (e.g. from overpayment) for display purposes but the linked liability report shows the full ledger.
- **Customer with zero remaining coupons but no open booklets**: A customer whose only Sold booklet has just been Depleted has zero remaining and is either listed among the low-stock customers (with count = 0) or is instead covered by the Recent Depleted Booklets widget — the two widgets together surface the same customer for follow-up without both being required.
- **Today's consumption crossing midnight**: "Today" is evaluated against the server's configured time zone at the moment the dashboard renders; a consumption entry with posting-datetime just after midnight appears in "today" and one just before it does not.
- **Cancelled source documents**: Cancelled Sales Invoices, Consumption Entries, and Discrepancies are excluded from every widget's counts and totals, consistent with the reports phase.
- **Concurrent writes during render**: A record submitted while the dashboard is rendering may or may not be reflected in that render; the next refresh shows the latest state. The dashboard does not guarantee within-render consistency beyond the underlying platform's database snapshot semantics.
- **Large number of delivery men in the in-custody breakdown**: When many delivery men each hold at least one booklet, the breakdown remains legible — either by truncating to the top holders with an indication that more exist, or by using a compact presentation — rather than overflowing the widget.
- **Colour-coded severity and accessibility**: The Open Discrepancies widget's "work to do" versus "healthy" states are distinguishable not only by colour but by the count value itself, so users with colour-vision limitations can still read the state.
- **Click-through when the filtered list is empty**: Clicking a zero-count widget still navigates to the correctly filtered list view (which will show "no records"), not an error page.

## Requirements *(mandatory)*

### Functional Requirements

#### Dashboard Presence, Access, and Navigation

- **FR-001**: System MUST provide a single Purisol dashboard view that aggregates the eight widgets defined in this phase, reachable from the main menu without requiring manual construction of a custom view.
- **FR-002**: System MUST set the Purisol dashboard as the default landing page for users holding the Purisol Administrator role, unless the user has a personal landing preference, in which case the user preference takes precedence.
- **FR-003**: System MUST restrict access to the Purisol dashboard to users holding the Purisol Administrator role; users without that role MUST NOT see the dashboard in menus and MUST NOT be able to open it by direct URL.
- **FR-004**: System MUST refresh the dashboard's displayed data on each open and on explicit user refresh, reflecting the latest committed state of the source records.
- **FR-005**: System MUST make every widget clickable, navigating to the corresponding filtered list view or existing report for the records that widget summarises, so the Administrator can drill into any metric without leaving the dashboard context.

#### Operational Widgets (Bundle 1)

- **FR-010**: System MUST display a "Booklets In Stock" widget showing the count of Coupon Booklets currently in status "In Stock", with a click-through to the Coupon Booklet list filtered to that status.
- **FR-011**: System MUST display a "Booklets In Custody" widget showing the count of Coupon Booklets currently in status "In Custody" together with a secondary breakdown of that count grouped by each booklet's current delivery man, with a click-through to the Coupon Booklet list filtered to that status.
- **FR-012**: System MUST display an "Active Sold Booklets" widget showing the count of Coupon Booklets currently in status "Sold" (i.e. sold and not yet fully depleted), with a click-through to the Coupon Booklet list filtered to that status.
- **FR-013**: System MUST display a "Today's Consumption" widget visualising the number of coupons recorded today grouped by the delivery man who submitted them; "today" is evaluated against the server's configured time zone at render time. The widget MUST link through to today's consumption entries (or the corresponding log).

#### Financial Risk Widgets (Bundle 2)

- **FR-020**: System MUST display an "Open Discrepancies" widget showing (a) the count of discrepancies currently in status "Open", (b) a short list of up to the five most recently opened discrepancies ordered newest-first, and (c) a visual severity indicator that clearly distinguishes count > 0 (work to do) from count = 0 (healthy). The severity distinction MUST be perceptible without relying on colour alone. The widget MUST link through to the open-discrepancies list.
- **FR-021**: System MUST display an "Outstanding Delivery Man Liabilities" widget showing the total outstanding balance across all delivery men together with a per-delivery-man breakdown. The total and the per-delivery-man figures MUST be sourced from the general ledger of the configured employee-liability account, matching the values produced by the Delivery Man Liability Balance report. The widget MUST link through to that report or the corresponding liability view.

#### Customer Follow-up Widgets (Bundle 3)

- **FR-030**: System MUST display a "Customers Low on Coupons" widget listing up to ten customers whose total remaining coupons across all their currently-Sold (not Depleted) booklets is at or below the configured customer low-stock threshold, ordered lowest-remaining first. When more than ten customers qualify, the widget MUST make clear that additional qualifying customers exist. Each listed customer MUST be clickable through to that customer's records.
- **FR-031**: System MUST display a "Recent Depleted Booklets" widget listing every Coupon Booklet whose depletion timestamp falls within the last seven days (computed against the server's configured time zone at render time), showing booklet number, customer, and depletion date, with each row clickable through to that booklet's detail view.

#### Data Integrity and Reuse

- **FR-040**: Widgets MUST use only the data already produced by Phases 1–7 (booklets, coupons, custody entries, sales invoices, consumption entries, discrepancies, journal entries, payment entries, and the existing settings); no new persistent data store is created for the dashboard.
- **FR-041**: Widgets MUST exclude cancelled and superseded source documents (cancelled Sales Invoices, cancelled Consumption Entries, cancelled Discrepancies) from all counts, totals, and lists, consistent with the reports phase.
- **FR-042**: The low-stock threshold used by the Customers Low on Coupons widget MUST be the existing `customer_low_stock_threshold` from Purisol Settings — the same value used by the notifications phase — and changing it MUST take effect for subsequent dashboard refreshes without any code change.

### Key Entities *(include if feature involves data)*

- **Coupon Booklet**: Source for the status-based counts (In Stock, In Custody, Sold), the In-Custody per-delivery-man breakdown (via `current_delivery_man`), and the Recent Depleted Booklets list (via `depleted_on`, `customer`). Already established in prior phases.
- **Consumption Entry**: Source for today's consumption visualisation; the entry's posting date and delivery man drive the grouping and total.
- **Discrepancy**: Source for the Open Discrepancies count, the top-five-recent list (ordered by opened-on), and the severity indicator. Status = "Open" is the filter.
- **General Ledger entries against the configured employee-liability account**: Source for the Outstanding Liabilities total and per-delivery-man breakdown; the dashboard reads the same ledger the Delivery Man Liability Balance report uses, to guarantee the two views agree.
- **Customer**: Reference data for the Customers Low on Coupons widget; remaining-coupon totals per customer are aggregated from that customer's currently-Sold booklets.
- **Employee (delivery man)**: Reference data for grouping in the In-Custody breakdown, Today's Consumption bars, and the Outstanding Liabilities per-delivery-man breakdown.
- **Purisol Settings**: Supplies the low-stock threshold used by the Customers Low on Coupons widget and the configured liability account used by the Outstanding Liabilities widget.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The dashboard loads within 3 seconds against a dataset of up to 10,000 coupons, 500 booklets, 50 delivery men, and 200 customers, so the Administrator can use it as a morning landing view without perceptible delay.
- **SC-002**: An Administrator can answer each of the following questions in under 10 seconds from the moment the dashboard loads, without navigating away: "How many booklets are on the shelf?", "Who's holding my booklets and how many?", "How many customers are actively consuming?", "How much did we deliver today?", "Are there open discrepancies right now?", "How much cash am I owed?", "Which customers are about to run out?", "Which booklets just finished?".
- **SC-003**: 100% of the acceptance scenarios across the three bundles produce the stated widget contents and behaviours against a seeded dataset.
- **SC-004**: The total shown on the Outstanding Liabilities widget matches the figure produced by the Delivery Man Liability Balance report for the same moment in time, with zero discrepancy across all delivery men.
- **SC-005**: Every one of the eight widgets is clickable and navigates to a correctly scoped list view, report, or record detail — verified by clicking each on a seeded dataset and landing on the expected filtered destination.
- **SC-006**: Users holding the Purisol Administrator role land on the dashboard by default on login (absent a personal home preference), and users without that role cannot reach the dashboard by menu or direct URL — both verified explicitly.
- **SC-007**: Every widget reflects the latest committed data on the next refresh after a relevant change — verified by creating, submitting, or cancelling a representative record (booklet, consumption entry, discrepancy, liability journal entry) and confirming the corresponding widget updates on the following dashboard open.
- **SC-008**: The Open Discrepancies widget's visual severity state is unambiguous in both the count > 0 case and the count = 0 case, and is perceptible without relying on colour alone.
- **SC-009**: Each of the three bundles (Operational, Financial Risk, Customer Follow-up) can be released independently without depending on the other two bundles being present — each bundle's widgets function correctly and usefully when delivered alone.

## Assumptions

- The Purisol Administrator role and its assignment to users already exists from earlier phases; no new role is introduced here.
- The customer low-stock threshold, the employee-liability account, and any other settings referenced by widgets already exist on Purisol Settings from earlier phases and are populated in production deployments.
- "Today", "last 7 days", "days in custody", and any other duration or recency values are computed in whole days against the server's configured time zone at the moment the dashboard renders. Sub-day precision is not required, and the dashboard is not internationalised to viewer-local time zones.
- The Delivery Man Liability Balance report delivered in the prior phase is the authoritative source for the liability total; the dashboard's Outstanding Liabilities widget reads from the same underlying ledger so the two views agree by construction.
- "Top 5 open discrepancies" means the five most-recently-opened discrepancies in status "Open", ordered by opened-on descending.
- "Top 10 customers low on coupons" means the ten customers with the lowest total remaining (but still at or below the threshold), ordered lowest-first; ties are broken deterministically by customer identifier so the list is stable across refreshes.
- The In-Custody per-delivery-man breakdown includes every delivery man holding at least one In-Custody booklet; it is not pre-filtered to active employees, so disabled or historical holders continue to appear for audit accuracy.
- Widget data is live — fetched on each dashboard open or refresh; no scheduled cache, materialised view, or reporting warehouse is introduced in this phase. Platform-level short-lived query caching, if any, is acceptable as long as it does not violate SC-007.
- Click-through targets reuse existing list views and reports delivered in prior phases (booklet list, consumption entries, discrepancies list, Delivery Man Liability Balance report, customer record); no new navigation targets or custom landing pages are created for this dashboard.
- Widget labels, empty-state text, severity indicators, and any tooltips follow the existing bilingual (English / Arabic) conventions from earlier phases; no new strings are introduced that are not translatable.
- The dashboard is a single view; alternate per-role or per-user layouts are out of scope for this phase.
- Mobile-specific dashboard layouts are out of scope; the dashboard uses the standard responsive presentation provided by the host platform.
- Real-time "push" updates (live tile updates without a refresh) are out of scope; the dashboard updates on open and on explicit refresh only.
- Historical snapshots of the dashboard (e.g. "what did this dashboard look like last Tuesday?") are out of scope; the dashboard always shows the current state.
