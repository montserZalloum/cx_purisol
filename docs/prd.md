# Purisol — Water Coupon Management System
## Product Requirements Document (PRD)

**Version:** 1.0
**Date:** April 18, 2026
**Platform:** ERPNext (Custom App)
**Prefix Convention:** All custom DocTypes are prefixed with `Purisol` to prevent conflicts with standard ERPNext DocTypes and enable easy identification.

---

## 1. Executive Summary

Purisol is a custom ERPNext application designed for a water distribution business that operates on a **coupon booklet** sales model. Customers purchase pre-paid booklets (20 coupons each), and redeem coupons with delivery men on each water bottle delivery. The system automates the full lifecycle of booklets, from generation to depletion, while providing strong controls against theft, unrecorded sales, and missing coupons.

The system integrates tightly with standard ERPNext modules (Item, Customer, Sales Invoice, Journal Entry, Employee) so that operational tracking and financial accounting stay in sync — no parallel records, no reconciliation overhead.

---

## 2. Business Context

### 2.1 Current Operation
- The shop sells pre-printed coupon booklets, each containing 20 physical coupons.
- Each booklet has a unique sequential number; each coupon within has a sequential number that is unique **system-wide** (not reset per booklet).
- A customer buys an entire booklet in advance.
- Delivery men carry booklets on their routes. When a customer wants a water bottle, they tear out one coupon and hand it to the delivery man.
- At end of day, delivery men return to the shop and hand over all consumed coupons collected that day (potentially from multiple customers).
- The accountant records consumed coupons into the system, and the system reconciles which coupons belong to which booklet and which customer.

### 2.2 Key Business Risks Being Mitigated
1. **Theft via missing pages:** A delivery man may sell coupons from a booklet but not hand in some of them, pocketing the revenue. The system must detect gaps in the consumed-coupon sequence within a booklet.
2. **Unrecorded booklet sales:** A delivery man may sell a whole booklet to a customer without informing the shop, then hand in consumed coupons from an "unknown" booklet. The system must detect coupons belonging to booklets that have no assigned customer.
3. **Lost track of custody:** When multiple delivery men hold booklets at once, and sometimes pass booklets between each other on the road, the shop must know exactly who holds which booklet at any time.

---

## 3. Goals & Non-Goals

### 3.1 Goals (MVP)
- Automate booklet and coupon generation with strict sequential numbering.
- Track custody of every booklet through its full lifecycle.
- Record coupon consumption efficiently and accurately.
- Detect and escalate discrepancies (missing coupons, unassigned booklets).
- Tie discrepancies to delivery-man financial liability through proper ERPNext accounting documents.
- Notify admin proactively about customers running low, new discrepancies, low booklet stock, and depleted booklets.
- Provide operational and financial reports plus a daily dashboard.

### 3.2 Non-Goals (Out of Scope for MVP)
- Delivery-man mobile app or self-service portal.
- Barcode/QR code scanning (design to allow future addition without refactor).
- Multi-branch support (single shop only for MVP).
- Customer-facing portal.
- Automated SMS/WhatsApp notifications (Bell notification only for MVP).
- Partial booklet refunds or returns (booklets, once sold, run to depletion).
- Booklet expiration policies.
- Multi-currency or multi-price-tier automation beyond standard ERPNext Price Lists.

---

## 4. User Roles (MVP)

For the initial release, the shop is small and operated by a single person.

| Role | Who | Access |
|------|-----|--------|
| **Purisol Administrator** | Shop owner (also the accountant) | Full access to all Purisol DocTypes, ERPNext financial documents, reports, and settings. |
| **Delivery Man** | Field staff | **No system access.** Represented as an `Employee` record in ERPNext. All operations involving them are performed by the Administrator on their behalf. |

**Future roles** (post-MVP): Separate Accountant role, Delivery Man portal with read-only access to their own custody.

---

## 5. Core Concepts & Terminology

| Term | Definition |
|------|------------|
| **Booklet** | A physical collection of 20 coupons, tracked in the system as a `Purisol Coupon Booklet` record. |
| **Coupon** | A single tear-out page within a booklet, tracked as a `Purisol Coupon` record. |
| **Custody** | The state of a booklet being physically held by a specific delivery man or by the shop. |
| **Consumption** | The act of a coupon being used (torn out and handed to the delivery man in exchange for a water bottle). |
| **Discrepancy** | Any anomaly detected by the system: missing coupons in a booklet's consumption sequence, or consumed coupons from an unassigned booklet. |
| **Liability** | A financial amount owed by a delivery man to the shop, arising from an unresolved discrepancy ruled against them. |

---

## 6. Numbering Scheme

### 6.1 Booklet Numbering
- Format: `WP-NNNNN` (e.g., `WP-00001`, `WP-00002`, ...)
- Strictly sequential, zero-padded to 5 digits.
- Generated automatically by ERPNext Naming Series.

### 6.2 Coupon Numbering
- Format: `CP-NNNNN` (e.g., `CP-00001`, `CP-00002`, ...)
- Sequential **system-wide**, not reset per booklet.
- Coupons belonging to booklet `WP-N` are numbered from `CP-((N-1)*20 + 1)` to `CP-(N*20)`.

| Booklet | First Coupon | Last Coupon |
|---------|--------------|-------------|
| WP-00001 | CP-00001 | CP-00020 |
| WP-00002 | CP-00021 | CP-00040 |
| WP-00003 | CP-00041 | CP-00060 |
| WP-NNNNN | CP-((N-1)*20+1) | CP-(N*20) |

### 6.3 Other Document Naming Series

| DocType | Naming Series | Example |
|---------|---------------|---------|
| Purisol Custody Entry | `PCE-.YYYY.-.#####` | PCE-2026-00001 |
| Purisol Coupon Consumption Entry | `PCC-.YYYY.-.#####` | PCC-2026-00001 |
| Purisol Coupon Discrepancy | `PCD-.YYYY.-.#####` | PCD-2026-00001 |

---

## 7. DocType Specifications

All custom DocTypes use the `Purisol` prefix.

### 7.1 Purisol Coupon Booklet

The master record for a physical booklet.

**Naming:** Auto-name from series `WP-.#####`
**Is Submittable:** No (state-managed)
**Track Changes:** Yes

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `booklet_number` | Data (read-only) | Yes | Same as `name`, e.g., `WP-00001`. |
| `status` | Select | Yes | One of: `In Stock`, `In Custody`, `Sold`, `Depleted`. Default `In Stock`. |
| `current_delivery_man` | Link → Employee | No | The delivery man currently holding this booklet. `null` if `In Stock` or `Sold`. |
| `customer` | Link → Customer | No | The customer who bought this booklet. Populated when status transitions to `Sold`. |
| `sold_on` | Datetime | No | When the booklet was sold to a customer. |
| `sales_invoice` | Link → Sales Invoice | No | The ERPNext Sales Invoice generated on sale (source of truth for revenue). |
| `depleted_on` | Datetime | No | When the last coupon in this booklet was consumed. Set automatically. |
| `first_coupon` | Data (read-only) | Yes | Computed: `CP-XXXXX` (first coupon in this booklet). |
| `last_coupon` | Data (read-only) | Yes | Computed: `CP-XXXXX` (last coupon in this booklet). |
| `total_coupons` | Int (read-only) | Yes | Always 20. |
| `consumed_count` | Int (read-only) | Yes | Number of coupons in this booklet marked `Consumed`. Recomputed on consumption events. |
| `remaining_count` | Int (read-only) | Yes | `total_coupons - consumed_count`. |
| `batch_id` | Data | No | Optional batch identifier for booklets generated together. |
| `notes` | Small Text | No | Free-text notes. |

**Validation Rules:**
- Status transitions follow the state machine in Section 8.
- `customer` cannot be cleared once set unless by the Administrator with explicit override.
- `first_coupon` and `last_coupon` are immutable after creation.

---

### 7.2 Purisol Coupon

The record for an individual coupon within a booklet.

**Naming:** Auto-name from series `CP-.#####`
**Is Submittable:** No (state-managed)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `coupon_number` | Data (read-only) | Yes | Same as `name`, e.g., `CP-00001`. |
| `booklet` | Link → Purisol Coupon Booklet | Yes | The parent booklet. |
| `page_number` | Int (read-only) | Yes | Position within the booklet (1–20). |
| `status` | Select | Yes | One of: `Available`, `Consumed`. Default `Available`. |
| `consumed_on` | Datetime | No | Timestamp set when coupon is marked `Consumed`. |
| `consumed_by_delivery_man` | Link → Employee | No | The delivery man who handed this coupon in. Set on consumption. |
| `consumption_entry` | Link → Purisol Coupon Consumption Entry | No | The entry document that recorded this consumption. |

**Validation Rules:**
- Status can only transition `Available` → `Consumed`, never back.
- `consumed_on`, `consumed_by_delivery_man`, `consumption_entry` are required when status is `Consumed`.
- A coupon can only be marked `Consumed` if its parent booklet has status `Sold`.

---

### 7.3 Purisol Custody Entry

Logs every custody event: initial assignment from shop to delivery man, transfer between delivery men, or return to shop.

**Naming:** Auto-name from series `PCE-.YYYY.-.#####`
**Is Submittable:** Yes (ensures immutability and audit trail)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `entry_type` | Select | Yes | One of: `Assign` (shop → delivery man), `Transfer` (delivery man → delivery man), `Return` (delivery man → shop). |
| `from_delivery_man` | Link → Employee | Conditional | Required for `Transfer` and `Return`. Must match each booklet's current custody. |
| `to_delivery_man` | Link → Employee | Conditional | Required for `Assign` and `Transfer`. |
| `entry_datetime` | Datetime | Yes | When the custody change happened. Default `now()`. |
| `booklets` | Table → Purisol Custody Entry Booklet | Yes | Child table listing the booklets involved. |
| `notes` | Small Text | No | Free text. |
| `created_by` | Link → User (read-only) | Yes | The Administrator who logged the entry. |

**Child Table: Purisol Custody Entry Booklet**

| Field | Type | Required |
|-------|------|----------|
| `booklet` | Link → Purisol Coupon Booklet | Yes |
| `booklet_status_at_entry` | Data (read-only) | Yes (snapshot) |

**Validation Rules:**
- For `Assign`: each booklet must currently have status `In Stock`.
- For `Transfer`: each booklet must currently have status `In Custody` AND `current_delivery_man == from_delivery_man`.
- For `Return`: each booklet must currently have status `In Custody` AND `current_delivery_man == from_delivery_man`.
- On submit: updates each booklet's `status` and `current_delivery_man` accordingly.
- Partial transfers are supported: a single Custody Entry can move any subset of booklets from one delivery man to another.

---

### 7.4 Purisol Coupon Consumption Entry

The daily record of coupons handed in by a delivery man.

**Naming:** Auto-name from series `PCC-.YYYY.-.#####`
**Is Submittable:** Yes

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `posting_date` | Date | Yes | Default `today()`. |
| `posting_time` | Time | Yes | Default `now()`. |
| `delivery_man` | Link → Employee | Yes | The delivery man handing in the coupons. |
| `received_by` | Link → User (read-only) | Yes | The Administrator recording the entry. |
| `coupons` | Table → Purisol Coupon Consumption Item | Yes | Child table of individual coupons consumed. |
| `total_coupons` | Int (read-only) | Yes | Count of rows in `coupons`. |
| `discrepancies_detected` | Table → Purisol Coupon Consumption Discrepancy (read-only) | No | Informational list of discrepancies flagged on submit (linked to separate Purisol Coupon Discrepancy records). |
| `has_warnings` | Check (read-only) | No | True if any discrepancies were detected. |
| `notes` | Small Text | No | |

**Child Table: Purisol Coupon Consumption Item**

| Field | Type | Required |
|-------|------|----------|
| `coupon` | Link → Purisol Coupon | Yes |
| `booklet` | Link → Purisol Coupon Booklet (fetched, read-only) | Yes |
| `customer` | Link → Customer (fetched, read-only) | No (null if booklet unassigned — will flag discrepancy) |

**Validation Rules:**
- **Blocking errors** (prevent submit):
  - Any coupon in the list is already `Consumed`.
  - Any coupon does not exist in the system.
  - Same coupon appears twice in the same entry.
- **Warning discrepancies** (allow submit but flag and create `Purisol Coupon Discrepancy`):
  - Any coupon belongs to a booklet with no assigned customer (booklet status != `Sold`).
  - Any coupon creates a gap in the booklet's consumption sequence (e.g., coupons 1, 2 previously consumed; now 7, 8 being submitted; coupons 3, 4, 5, 6 missing).
- On submit, for each coupon:
  - Set status to `Consumed`.
  - Set `consumed_on`, `consumed_by_delivery_man`, `consumption_entry`.
  - Update parent booklet's `consumed_count`, `remaining_count`.
  - If booklet's `consumed_count == 20`, transition booklet to `Depleted`, set `depleted_on`, and trigger depletion notification.
- Trigger customer-low-stock notification check for each affected customer.

---

### 7.5 Purisol Coupon Discrepancy

An investigation record for each anomaly. Created automatically by the system, resolved manually by the Administrator.

**Naming:** Auto-name from series `PCD-.YYYY.-.#####`
**Is Submittable:** Yes (submit = resolve)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `discrepancy_type` | Select | Yes | One of: `Missing Coupons` (gap in sequence), `Unassigned Booklet` (coupon from booklet with no customer). |
| `status` | Select | Yes | One of: `Open`, `Under Review`, `Resolved - Admin Error`, `Resolved - Delivery Man Liable`, `Resolved - Paid`. Default `Open`. |
| `opened_on` | Datetime (read-only) | Yes | When the discrepancy was detected. |
| `resolved_on` | Datetime (read-only) | No | Set when status moves to any `Resolved - *` value. |
| `triggering_consumption_entry` | Link → Purisol Coupon Consumption Entry | Yes | The entry that triggered the discrepancy. |
| `booklet` | Link → Purisol Coupon Booklet | Yes | The booklet involved. |
| `customer` | Link → Customer | No | The customer the booklet is assigned to (null for `Unassigned Booklet` cases). |
| `affected_coupons` | Table → Purisol Discrepancy Coupon | Yes | List of coupons involved (missing ones for `Missing Coupons`, or the handed-in coupon for `Unassigned Booklet`). |
| `liable_delivery_man` | Link → Employee | No | The delivery man ruled responsible. Set when Administrator resolves. |
| `related_delivery_men` | Table → Purisol Discrepancy Related Person | No | Auto-populated list of delivery men who had touchpoints with this booklet in the relevant period. Used as investigation aid. |
| `estimated_amount` | Currency | Yes | Auto-computed: `coupon_unit_price × affected_coupons_count`. Editable by Administrator. |
| `resolution_action` | Select | No | One of: `None` (admin error), `Add to Liability Ledger`, `Immediate Cash Payment`. Required when resolving. |
| `journal_entry` | Link → Journal Entry | No | Created if `resolution_action == Add to Liability Ledger`. |
| `payment_entry` | Link → Payment Entry | No | Created if `resolution_action == Immediate Cash Payment`. |
| `resolution_notes` | Small Text | No | Free text explaining the resolution. |

**Child Table: Purisol Discrepancy Coupon**

| Field | Type |
|-------|------|
| `coupon_number` | Data (may be a CP number for existing coupons, or a synthetic number for missing ones based on the known gap). |
| `notes` | Data |

**Child Table: Purisol Discrepancy Related Person**

| Field | Type | Notes |
|-------|------|-------|
| `delivery_man` | Link → Employee | |
| `role` | Select | `Custody Holder`, `Submitted Adjacent Coupons`. |
| `reference_document` | Dynamic Link | Related custody or consumption entry. |

**Resolution Flow (enforced on save/submit):**
1. `Resolved - Admin Error`: no financial entry. Administrator may optionally retroactively link the booklet to a customer (through a separate action).
2. `Resolved - Delivery Man Liable`: requires `liable_delivery_man` set. On submit, creates a Journal Entry:
   - Debit: Employee Liability account (per delivery man).
   - Credit: Sales / Inventory adjustment account (as configured in Purisol Settings).
   - The amount can then be deducted from future Salary Slips via standard ERPNext workflow.
3. `Resolved - Paid`: requires `liable_delivery_man` set. On submit, creates a Payment Entry:
   - Cash receipt from delivery man.
   - Against Sales / Inventory adjustment account.

---

### 7.6 Purisol Settings

A Single DocType (singleton) holding system-wide configuration.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `coupon_item` | Link → Item | — | The ERPNext Item representing the coupon booklet (required for Sales Invoice generation). |
| `default_price_list` | Link → Price List | Standard Selling | Used when selling to a customer who has no specific Price List set. |
| `customer_low_stock_threshold` | Int | 3 | When a customer's total remaining coupons (across all active booklets) reaches this, send notification. |
| `warehouse_low_stock_threshold` | Int | 5 | When in-stock booklet count falls below this, send notification to generate a new batch. |
| `employee_liability_account` | Link → Account | — | GL account used as the debit side when creating liability Journal Entries. |
| `discrepancy_offset_account` | Link → Account | — | GL account used as the credit side (typically Sales Adjustment or Inventory Adjustment). |
| `default_cash_account` | Link → Account | — | Used when creating Payment Entries for cash-resolved discrepancies. |
| `enable_consumption_warnings` | Check | Yes | Toggle for enabling/disabling discrepancy warnings on consumption entries. |

---

## 8. Business Logic & Workflows

### 8.1 Booklet State Machine

```
                ┌─────────────────────────────────────────────────┐
                │                                                 │
   [Created]    │                                                 │
       │        ▼                                                 │
       ▼   ┌────────┐   Custody Entry   ┌────────────┐           │
    In Stock ───────(Assign)──────────► In Custody   │           │
                │                      │     │       │           │
                │                      │     │ Sale to customer  │
                │                      │     ▼       │           │
                │                      │   Sold ──────┼─ All 20 consumed
                │                      │              │           │
                │                      └──────────────┘           │
                │                                                 │
                │                                                 ▼
                │                                           Depleted
                │                                           (terminal)
```

**Transitions:**

| From | To | Trigger | Side Effects |
|------|-----|---------|--------------|
| (new) | `In Stock` | Booklet generation | Coupons created in `Available` state |
| `In Stock` | `In Custody` | Custody Entry (type `Assign`) on submit | `current_delivery_man` set |
| `In Custody` | `In Custody` | Custody Entry (type `Transfer`) on submit | `current_delivery_man` updated |
| `In Custody` | `In Stock` | Custody Entry (type `Return`) on submit | `current_delivery_man` cleared |
| `In Custody` | `Sold` | Customer assignment action (see 8.4) | `customer`, `sold_on`, `sales_invoice` set; `current_delivery_man` cleared |
| `Sold` | `Depleted` | Consumption Entry on submit; `consumed_count == 20` | `depleted_on` set; notification sent |

**Not allowed:**
- `Sold` → `In Custody` or `In Stock` (no returns in MVP).
- `Depleted` → anything (terminal state).

---

### 8.2 Booklet Generation

**Trigger:** Administrator invokes "Generate Booklets" action from a dedicated form or the list view.

**Inputs:**
- `quantity` (int, required) — how many booklets to create.
- `batch_id` (string, optional) — for tracking.

**Process:**
1. Determine the next booklet number from the last `Purisol Coupon Booklet.name`.
2. For each booklet to create:
   - Create `Purisol Coupon Booklet` with status `In Stock`.
   - Create 20 `Purisol Coupon` records with sequential numbers and status `Available`, linked to the new booklet.
3. Return a summary: first/last booklet numbers generated, total coupons created.

**Performance considerations:**
- For quantities > 20 (i.e., > 400 coupon records), run as a background job using `frappe.enqueue` to avoid request timeout.
- Use `bulk_insert` for coupon creation where possible.

---

### 8.3 Custody Assignment and Transfer

**Assignment (Shop → Delivery Man):**
1. Administrator creates a Purisol Custody Entry with `entry_type = Assign`.
2. Selects the `to_delivery_man`.
3. Adds booklets (filtered list shows only `In Stock` booklets).
4. Submits. Booklets transition to `In Custody`, `current_delivery_man` set.

**Transfer (Delivery Man → Delivery Man):**
1. Administrator creates a Purisol Custody Entry with `entry_type = Transfer`.
2. Selects `from_delivery_man` and `to_delivery_man`.
3. Adds booklets (filtered list shows only booklets currently with `from_delivery_man`).
4. Submits. Booklets keep status `In Custody`, `current_delivery_man` updated.

**Return (Delivery Man → Shop):**
1. Administrator creates a Purisol Custody Entry with `entry_type = Return`.
2. Selects `from_delivery_man`.
3. Adds booklets.
4. Submits. Booklets transition back to `In Stock`, `current_delivery_man` cleared.

**Partial transfers** are naturally supported: the child table lets the Administrator include any subset of booklets.

---

### 8.4 Booklet Sale to Customer

This is the moment of revenue recognition. It must create a Sales Invoice.

**Trigger:** Administrator action "Sell Booklet to Customer" — either:
- From the booklet form (single booklet), or
- From a custom form "Sell Booklets" for batch sale (multiple booklets to same customer).

**Inputs:**
- `customer` (Link → Customer, required)
- `booklets` (list of Purisol Coupon Booklets, must be `In Custody` or `In Stock`)
- `price_list` (optional, defaults to customer's configured list or Purisol Settings default)
- `payment_mode` (optional: cash, credit, etc.)

**Process:**
1. Validate that each booklet is `In Custody` or `In Stock`.
2. Create an ERPNext `Sales Invoice`:
   - Customer: the selected customer.
   - Items: one row per booklet, `item_code = Purisol Settings.coupon_item`, qty=1, rate from Price List.
   - Standard ERPNext tax, accounting, and payment processing applies.
3. On Sales Invoice submit:
   - For each booklet: set `customer`, `sold_on`, `sales_invoice`, transition status to `Sold`, clear `current_delivery_man`.
   - Fire customer-low-stock check (the new booklet adds to their remaining count).

**Note:** The delivery man who was carrying the booklet when sold is not stored on the booklet (since custody ends at sale). However, the custody history is preserved through the Custody Entry audit trail — any investigation can reconstruct who held the booklet and when.

---

### 8.5 Coupon Consumption Recording

**Trigger:** Administrator opens "New Coupon Consumption Entry" at end of day.

**Entry UI supports two input modes** (see Section 12 for full UI requirements):
- **Mode A:** Enter booklet number → system displays a checklist of available (not-yet-consumed) coupons → Administrator checks which ones to record.
- **Mode B:** Enter coupon numbers directly (one per row or via paste); the system auto-fills the booklet and customer.

Both modes populate the same child table (`coupons`).

**On Submit (validation + side effects):**
1. Validate each coupon exists and is not already `Consumed`.
2. Detect discrepancies:
   - **Unassigned Booklet:** For each coupon whose parent booklet has `status != Sold`, flag `Unassigned Booklet` discrepancy.
   - **Missing Coupons:** For each booklet in the entry, compute the set of previously consumed coupons + currently being consumed coupons. If there's any gap between the lowest and highest numbers (e.g., 1, 2, 7, 8 consumed but 3–6 still Available), flag `Missing Coupons` discrepancy for the gap.
3. If discrepancies exist:
   - Create a `Purisol Coupon Discrepancy` record for each with status `Open`.
   - Link them back to this Consumption Entry via `discrepancies_detected`.
   - Set `has_warnings = True`.
   - Show a non-blocking warning dialog to the Administrator listing the discrepancies.
4. For each coupon, update status to `Consumed` and populate `consumed_on`, `consumed_by_delivery_man`, `consumption_entry`.
5. For each affected booklet:
   - Increment `consumed_count`, decrement `remaining_count`.
   - If `consumed_count == 20`, transition to `Depleted`, set `depleted_on`, and trigger **Booklet Depleted** notification.
6. For each affected customer:
   - Compute total remaining coupons across all booklets currently `Sold` for that customer.
   - If total ≤ `Purisol Settings.customer_low_stock_threshold`, send **Customer Low Stock** notification.

---

### 8.6 Discrepancy Investigation & Resolution

**Creation:** Automatic, by the Coupon Consumption Entry logic (Section 8.5).

**Investigation workflow:**
1. Administrator opens the Purisol Coupon Discrepancy record from the "Open Discrepancies" list or dashboard.
2. Reviews `affected_coupons`, `related_delivery_men` (auto-populated with delivery men who had custody of, or submitted adjacent coupons from, this booklet).
3. Changes status to `Under Review` while investigating (optional).
4. Decides outcome by setting `resolution_action`:
   - **`None` (Admin Error):** No financial consequence.
     - If `Unassigned Booklet`: Administrator may separately assign the booklet to a customer via a "Retroactive Customer Assignment" action (creates a backdated Sales Invoice).
     - Status → `Resolved - Admin Error`.
   - **`Add to Liability Ledger`:** Delivery man owes the amount.
     - Requires `liable_delivery_man`.
     - On submit, system creates a Journal Entry: Debit Employee Liability Account (per delivery man), Credit Discrepancy Offset Account.
     - Status → `Resolved - Delivery Man Liable`.
     - Amount is now reflected in delivery-man receivables report and can be deducted via Salary Slip.
   - **`Immediate Cash Payment`:** Delivery man pays on the spot.
     - Requires `liable_delivery_man`.
     - On submit, system creates a Payment Entry: Debit Cash Account, Credit Discrepancy Offset Account.
     - Status → `Resolved - Paid`.

**Locking:** Once resolved (submitted), the discrepancy record is immutable. Corrections require a reversing Journal Entry / Payment Entry through standard ERPNext flows.

---

### 8.7 Automatic Status Management Summary

| Event | Affected Records | Status Changes |
|-------|------------------|----------------|
| Booklet generation | New Purisol Coupon Booklet, 20 new Purisol Coupons | Booklet: `In Stock`; Coupons: `Available` |
| Custody Entry (Assign) submit | Booklets in entry | `In Stock` → `In Custody` |
| Custody Entry (Transfer) submit | Booklets in entry | `In Custody` → `In Custody` (new owner) |
| Custody Entry (Return) submit | Booklets in entry | `In Custody` → `In Stock` |
| Sales Invoice submit (booklet item) | Linked booklets | `In Custody` / `In Stock` → `Sold` |
| Coupon Consumption Entry submit | Coupons, affected Booklets | Coupons: `Available` → `Consumed`; Booklet: `Sold` → `Depleted` if all 20 consumed |
| Discrepancy resolve | — | `Open` → `Resolved - *` |

---

## 9. Integration with ERPNext Standard Modules

Purisol leans on ERPNext primitives wherever possible. This ensures accounting integrity and reduces custom code.

### 9.1 Item
- A single Item `Water Coupon Booklet` (or configurable via Purisol Settings) represents booklets for sales purposes.
- The Item's UOM is `Booklet`.
- Item is non-stock (since physical booklet tracking is handled by `Purisol Coupon Booklet`, not by ERPNext inventory).

### 9.2 Price Lists
- Leverage standard ERPNext Price Lists for tiered pricing (retail, wholesale, etc.).
- Customers can be associated with a default Price List on their Customer record.
- Pricing Rules (discounts, bulk pricing) work out of the box.

### 9.3 Sales Invoice
- Every booklet sale creates a standard Sales Invoice.
- One line item per booklet (so individual booklets can be referenced).
- Standard revenue recognition, AR, tax handling.
- Sales Invoice is linked back to each `Purisol Coupon Booklet.sales_invoice`.

### 9.4 Journal Entry
- Used for `Resolved - Delivery Man Liable` discrepancies.
- Debit: Employee Liability Account (per-employee tracking).
- Credit: Discrepancy Offset Account (configured).

### 9.5 Payment Entry
- Used for `Resolved - Paid` discrepancies.
- Standard cash receipt against Discrepancy Offset Account.

### 9.6 Employee / Salary Slip
- Delivery men are `Employee` records.
- Unpaid liabilities (open delivery-man liability account balances) can be deducted from Salary Slips using ERPNext's standard deduction mechanism. Not automated in MVP — Administrator creates the Salary Slip adjustment manually.

### 9.7 Notification
- Uses standard ERPNext Notification framework (bell icon).
- Notifications are created programmatically via Server Scripts.

---

## 10. Notifications & Alerts (MVP)

All notifications are delivered via the ERPNext bell icon (in-system only). Email/WhatsApp/SMS is future work.

| Notification | Trigger | Recipient | Content |
|--------------|---------|-----------|---------|
| **Customer Low Stock** | On Coupon Consumption Entry submit, customer's total remaining ≤ threshold | Administrator | "Customer {name} has only {N} coupons remaining. Prepare a new booklet." |
| **New Discrepancy Opened** | On Coupon Consumption Entry submit, discrepancy detected | Administrator | "Discrepancy {PCD-xxx} opened: {type} in booklet {WP-xxx}, delivery man {name}." |
| **Warehouse Low Stock** | After Sales Invoice submit, if `In Stock` booklet count < threshold | Administrator | "Only {N} booklets remain in stock. Generate a new batch." |
| **Booklet Depleted** | When a booklet transitions to `Depleted` | Administrator | "Booklet {WP-xxx} for customer {name} is fully consumed. Follow up for resale." |
| **Consumption Entry Has Warnings** | Same trigger as New Discrepancy, summary popup on UI | Administrator (UI-level) | List of all discrepancies detected in the entry just submitted. |

Thresholds are configured in `Purisol Settings`.

---

## 11. Reports & Dashboard

### 11.1 Operational Reports

| Report | Filters | Columns |
|--------|---------|---------|
| **Daily Delivery Man Summary** | Date, Delivery Man | Delivery man, coupons submitted, booklets touched, discrepancies count, discrepancy value |
| **Active Booklets per Customer** | Customer | Customer, booklet number, status, consumed count, remaining count, sold date, days since sale |
| **Current Custody by Delivery Man** | Delivery Man | Delivery man, booklet number, days in custody, customer (null = unsold) |
| **Coupon Consumption Log** | Date range, Delivery Man, Customer, Booklet | Date, coupon, booklet, customer, delivery man, consumption entry ref |

### 11.2 Financial / Oversight Reports

| Report | Filters | Columns |
|--------|---------|---------|
| **Delivery Man Discrepancies** | Date range, Delivery Man, Status | Discrepancy ID, date, type, booklet, coupons count, amount, status, resolution |
| **Delivery Man Liability Balance** | Delivery Man | Delivery man, total owed (from Journal Entries), total paid, open balance |
| **Booklet Sales Report** | Date range, Customer, Price List | Sale date, booklet, customer, invoice ref, amount, status |
| **Discrepancy Rate by Delivery Man** | Date range | Delivery man, coupons submitted, discrepancies count, % rate, total discrepancy value |

### 11.3 Analytical Reports

| Report | Purpose |
|--------|---------|
| **Customer Consumption Rate** | Average days between booklet purchase and full depletion, per customer. Used to predict next purchase. |
| **Booklet Lifecycle Duration** | Time from generation → custody → sold → depleted. Helps size generation batches. |

### 11.4 Dashboard (Landing Page)

A dedicated Purisol Dashboard visible on login. Key widgets:

| Widget | Content |
|--------|---------|
| **Booklets In Stock** | Count + quick link to generate new batch |
| **Booklets In Custody** | Count + breakdown per delivery man |
| **Active (Sold) Booklets** | Count |
| **Customers Low on Coupons** | List of customers with remaining ≤ threshold |
| **Open Discrepancies** | Count, with colour-coded severity; click → list view |
| **Outstanding Delivery Man Liabilities** | Total amount + per-delivery-man breakdown |
| **Today's Consumption Entries** | Count, total coupons processed, top delivery men |
| **Recent Depleted Booklets (last 7 days)** | List with customer names, for resale follow-up |

---

## 12. UI / UX Requirements

### 12.1 Coupon Consumption Entry Form — Dual Input Mode

The consumption entry form must offer **both** input methods on the same screen; the Administrator picks whichever is faster for the situation.

**Layout:**
1. **Header section:** delivery_man, posting_date, posting_time.
2. **Input method selector:** a tab-style toggle between:
   - **"By Booklet"** (Mode A)
   - **"By Coupon Number"** (Mode B)
3. **Mode A panel:**
   - Input: booklet number (autocomplete).
   - On selection: display a checklist of all `Available` coupons for that booklet, showing page number and coupon number.
   - Administrator ticks coupons to record → "Add to Entry" button adds them to the main child table.
4. **Mode B panel:**
   - Input: coupon number (autocomplete or paste-friendly).
   - On each entry, the system fetches the parent booklet and customer and adds a row to the main child table.
5. **Main child table:** All coupons added (from either mode), with columns: Coupon, Booklet, Customer. Remove button per row.
6. **Submit button:** triggers validations described in 8.5.

### 12.2 Discrepancy Resolution Form

- Top section is read-only: discrepancy type, opened date, affected booklet, coupons.
- `related_delivery_men` is displayed prominently as an investigation aid.
- Resolution section (editable):
  - Select `resolution_action`.
  - If action requires a liable delivery man, the field appears and becomes required.
  - `estimated_amount` is pre-filled, editable.
  - `resolution_notes` (free text).
- "Resolve & Submit" button.

### 12.3 Sell Booklet to Customer Form

A simplified wizard-style form:
1. Select customer (autocomplete).
2. Add booklets: multi-select from list filtered to `In Stock` or `In Custody` booklets.
3. Price List (auto-filled from customer or settings).
4. Payment mode (optional, or create draft Sales Invoice for later payment).
5. "Create Sale" button → creates Sales Invoice → on Invoice submit, booklets transition to `Sold`.

### 12.4 Generate Booklets Form

Simple form:
- Quantity (int).
- Optional batch ID.
- "Generate" button → launches background job if quantity is large, shows progress.
- On completion: summary of generated booklets (first number, last number, total coupons).

### 12.5 Data Entry Optimizations

- Autocomplete for all Link fields.
- Keyboard shortcuts for common actions (submit, new entry).
- **Future-proofing for barcode scanning:** All coupon-number input fields should accept USB/Bluetooth barcode scanner input transparently (most scanners act as keyboards + Enter key). No extra work in MVP; just ensure the input field accepts paste/keyboard input and Enter submits/advances.

---

## 13. Permissions (MVP)

Only one Purisol-specific role is created: **Purisol Administrator**.

Role assignments for this role:

| DocType | Create | Read | Write | Submit | Cancel | Amend |
|---------|--------|------|-------|--------|--------|-------|
| Purisol Coupon Booklet | Yes | Yes | Yes | N/A | N/A | N/A |
| Purisol Coupon | No (system-generated) | Yes | Yes | N/A | N/A | N/A |
| Purisol Custody Entry | Yes | Yes | Yes | Yes | Yes | Yes |
| Purisol Coupon Consumption Entry | Yes | Yes | Yes | Yes | Yes | Yes |
| Purisol Coupon Discrepancy | No (system-generated) | Yes | Yes | Yes | Yes | No |
| Purisol Settings | No (singleton) | Yes | Yes | N/A | N/A | N/A |

Plus standard ERPNext roles (Sales User, Accounts User) for managing Customer, Sales Invoice, Journal Entry, Payment Entry.

---

## 14. Out of Scope / Future Enhancements

Explicitly deferred for later releases:

1. **Delivery Man Portal:** Self-service mobile app for delivery men to view their custody, log sales, and record consumptions directly.
2. **Barcode/QR Code Scanning:** Physical coupons would carry scannable codes; consumption entry via scan.
3. **Multi-Branch / Multi-Warehouse:** Support for multiple shop locations with independent booklet stocks.
4. **Booklet Returns / Refunds:** Allow partial refund of unused coupons if a customer discontinues.
5. **Booklet Expiration:** Expire booklets after a fixed period (e.g., 1 year).
6. **External Notifications:** Email, WhatsApp, SMS alerts in addition to bell.
7. **Automatic Salary Deduction:** Auto-create Salary Slip deductions from open delivery man liabilities.
8. **Customer Portal:** Customers see remaining coupons, order new booklets.
9. **Route Optimization:** Suggest delivery routes based on customer geography and consumption rate.
10. **Multiple Booklet Sizes:** Support booklets with configurable page counts (not just 20).

---

## 15. Technical Considerations

### 15.1 Performance
- Generating 50 booklets creates 1,050 records (50 booklets + 1,000 coupons). Use background job (`frappe.enqueue`) and bulk insert.
- Discrepancy detection on consumption entries runs O(n log n) for gap analysis per booklet. Acceptable for typical daily volumes (< 200 coupons/day).
- Dashboard widgets should cache aggregations with reasonable TTL (e.g., 5 minutes).

### 15.2 Data Integrity
- Use database transactions for multi-record state changes (e.g., custody entry updating multiple booklets).
- Coupon sequence numbering is computed, not stored — always regenerate from `booklet.name` + `page_number` to avoid drift.
- Submitted documents (Custody Entry, Consumption Entry, Discrepancy, Sales Invoice, Journal Entry, Payment Entry) are immutable per ERPNext conventions; corrections via cancel+amend or reversing entries.

### 15.3 Audit Trail
- Every Purisol document uses ERPNext's built-in "Track Changes" feature.
- Consumption details on the individual Coupon record (`consumed_on`, `consumed_by_delivery_man`, `consumption_entry`) provide permanent traceability even if aggregation data drifts.
- Custody Entry documents form a complete chain of custody history.

### 15.4 Extensibility
- Input UI for consumption entry is designed to accept barcode scanner input without modification.
- Notification framework is pluggable — adding email/WhatsApp later only requires new channel config, not logic changes.
- Price logic uses standard Price List, so any future pricing complexity is handled by ERPNext.

### 15.5 Error Handling
- Validation errors (blocking): raised as `frappe.ValidationError` with clear messages in Arabic/English.
- Warning conditions (discrepancies): non-blocking; logged as Discrepancy records and shown via UI dialog on submit.
- Background job failures: logged and surfaced via ERPNext Error Log; Administrator notified.

---

## 16. Acceptance Criteria

The MVP is considered complete when all of the following pass:

### 16.1 Booklet & Coupon Generation
- [ ] Administrator can generate N booklets; exactly N booklet records and N×20 coupon records are created with correct sequential numbering.
- [ ] Booklet `WP-00002` contains coupons `CP-00021` through `CP-00040`.
- [ ] Each new booklet starts with status `In Stock`; each coupon starts `Available`.

### 16.2 Custody Management
- [ ] Administrator can assign a subset of booklets to a delivery man; affected booklets transition to `In Custody` with correct `current_delivery_man`.
- [ ] Administrator can transfer a subset of booklets from one delivery man to another in a single Custody Entry.
- [ ] Administrator can return booklets from delivery man to shop (`In Stock`).
- [ ] Custody history is preserved: every transition is a distinct Custody Entry record.

### 16.3 Sale
- [ ] Selling one or more booklets to a customer creates a Sales Invoice with correct line items and pricing (using Price List).
- [ ] On Sales Invoice submit, booklets transition to `Sold` with correct `customer`, `sold_on`, `sales_invoice`.
- [ ] Booklets can be sold from both `In Stock` and `In Custody` states.

### 16.4 Consumption Recording
- [ ] Administrator can record consumption via Mode A (pick coupons from booklet checklist) and Mode B (enter coupon numbers).
- [ ] Submitted consumption entry updates each coupon to `Consumed` with correct metadata.
- [ ] Affected booklets' `consumed_count`/`remaining_count` are updated correctly.
- [ ] When the 20th coupon of a booklet is consumed, booklet transitions to `Depleted` automatically.

### 16.5 Discrepancy Detection
- [ ] Submitting a consumption entry with a coupon from an unassigned booklet creates an `Unassigned Booklet` discrepancy.
- [ ] Submitting coupons that create a gap (e.g., 7, 8 when 3–6 are unconsumed) creates a `Missing Coupons` discrepancy listing the missing coupon numbers.
- [ ] Submitting duplicate coupons or coupons already consumed is blocked (not just warned).

### 16.6 Discrepancy Resolution
- [ ] Administrator can resolve as `Admin Error` with no financial entry.
- [ ] Administrator can resolve as `Delivery Man Liable`, which auto-creates a correct Journal Entry.
- [ ] Administrator can resolve as `Paid`, which auto-creates a correct Payment Entry.
- [ ] Once resolved, the discrepancy is locked.

### 16.7 Notifications
- [ ] Customer low-stock notification fires when a customer's total remaining coupons falls to ≤ threshold after a consumption entry.
- [ ] Discrepancy notification fires on consumption entry submit when discrepancies are detected.
- [ ] Warehouse low-stock notification fires when `In Stock` booklet count falls below threshold.
- [ ] Booklet depleted notification fires when a booklet transitions to `Depleted`.

### 16.8 Reports & Dashboard
- [ ] All reports listed in Section 11 are accessible, filter correctly, and show accurate data.
- [ ] The Purisol Dashboard loads on login and displays live metrics per Section 11.4.

### 16.9 Data Integrity & Audit
- [ ] Each coupon stores `consumed_on`, `consumed_by_delivery_man`, `consumption_entry` after consumption.
- [ ] Every booklet's custody history is reconstructible from Custody Entry records.
- [ ] No state transition violates the state machine in Section 8.1.

---

## Appendix A — Glossary of DocType Prefix Convention

All custom DocTypes in this system are prefixed with **`Purisol`** to:
- Avoid collisions with core ERPNext DocTypes (e.g., `Coupon` already exists as a discount coupon).
- Make Purisol-related records immediately distinguishable in the ERPNext UI, search results, and database queries.
- Simplify future upgrades and migrations (easy to identify custom entities).

**Full list of Purisol DocTypes:**
1. `Purisol Coupon Booklet`
2. `Purisol Coupon`
3. `Purisol Custody Entry`
4. `Purisol Custody Entry Booklet` (child table)
5. `Purisol Coupon Consumption Entry`
6. `Purisol Coupon Consumption Item` (child table)
7. `Purisol Coupon Consumption Discrepancy` (child table, references `Purisol Coupon Discrepancy`)
8. `Purisol Coupon Discrepancy`
9. `Purisol Discrepancy Coupon` (child table)
10. `Purisol Discrepancy Related Person` (child table)
11. `Purisol Settings` (singleton)

---

## Appendix B — Key Business Rules Quick Reference

1. **Booklets have 20 coupons each**, numbered sequentially system-wide (not reset per booklet).
2. **Custody ends at sale.** Once a booklet is sold, `current_delivery_man` is cleared. Any delivery man may thereafter hand in coupons from that booklet — that's normal, not a discrepancy.
3. **Missing Coupons discrepancy** is detected per-booklet by analyzing the full consumption sequence, not just within a single entry.
4. **Unassigned Booklet discrepancy** means coupons were submitted from a booklet that is still `In Custody` or `In Stock` — implying an unrecorded sale or theft.
5. **Customer low-stock check** aggregates across all the customer's `Sold` (not `Depleted`) booklets — notification fires only when the grand total is at or below threshold.
6. **Booklet depletion is automatic** the moment the 20th coupon is consumed.
7. **Financial consequences of discrepancies** go through standard ERPNext Journal Entries or Payment Entries, not custom records — ensuring full GL integrity.
8. **Discrepancy investigation** uses `related_delivery_men` as an aid: this list auto-includes the booklet's custody holder and any delivery men who submitted coupons from the same booklet in the relevant timeframe.

---

**End of PRD v1.0**
