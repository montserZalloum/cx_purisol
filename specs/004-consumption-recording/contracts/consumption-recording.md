# Phase 1 Contracts — Consumption Recording

**Feature**: 004-consumption-recording | **Date**: 2026-04-18

This document captures the behavioural contracts for every external interface Phase 4 exposes, in a form that tests and client code can reason about without reading the implementation. Four contract surfaces:

1. **Consumption Entry submit** — the primary server-side operation.
2. **Consumption Entry cancel** — the reversal operation.
3. **Mode A API** — `list_available_coupons` (whitelisted read helper).
4. **Mode B API** — `resolve_coupons` (whitelisted read helper).

Each contract lists **Preconditions** (what must be true to call), **Postconditions** (what is true after a successful call), **Errors** (every rejection path + its exact error type and message shape), and **Permissions** (who can call it).

---

## 1. Contract — Submit a `Purisol Coupon Consumption Entry`

**Operation**: `frappe.get_doc("Purisol Coupon Consumption Entry", name).submit()` (or the equivalent form-UI submit action; same code path).

### 1.1. Preconditions

1. The caller holds the `Purisol Administrator` role.
2. The DocType exists as a draft (`docstatus = 0`) with:
   - `delivery_man` set to an existing `Employee` record.
   - `posting_date` set to any date (backdated / future permitted — admin judgement).
   - `posting_time` set to any time.
   - `coupons` child table has ≥ 1 row; every row has a `coupon` value.
   - `has_warnings` is `0` and `discrepancies_detected` is empty (Phase 4 reserved rules).

### 1.2. Postconditions (on success)

Let `R = self.coupons` (rows), `C = {r.coupon for r in R}` (distinct coupon names), `B = {r.booklet for r in R}` (distinct booklet names). All of the following hold after the submit transaction commits:

1. `self.docstatus == 1`.
2. For **every** `c in C`:
   - `Purisol Coupon[c].status == "Consumed"`
   - `Purisol Coupon[c].consumed_on == self.posting_datetime`
   - `Purisol Coupon[c].consumed_by_delivery_man == self.delivery_man`
   - `Purisol Coupon[c].consumption_entry == self.name`
3. For **every** `b in B`:
   - `Purisol Coupon Booklet[b].consumed_count == count({c ∈ Purisol Coupon | c.booklet == b ∧ c.status == "Consumed"})`
   - `Purisol Coupon Booklet[b].remaining_count == 20 - Purisol Coupon Booklet[b].consumed_count`
4. For every `b in B` whose pre-submit `status` was `Sold` AND whose post-submit `consumed_count` is `20`:
   - `Purisol Coupon Booklet[b].status == "Depleted"`
   - `Purisol Coupon Booklet[b].depleted_on == self.posting_datetime`
   - `Purisol Coupon Booklet[b]` has a `Comment` with body matching `_("Depleted via {0}").format(self.name)`.
5. `Purisol Coupon` records **not** listed in `C` are bit-for-bit unchanged. `Purisol Coupon Booklet` records **not** in `B` are bit-for-bit unchanged.
6. No `Purisol Coupon Discrepancy` record is created. No `Notification Log` entry is created by this flow.

### 1.3. Postconditions (on failure)

If any rule in §1.4 is violated, the submit raises (see below). All of the following hold after the raise:

1. `self.docstatus == 0` (draft state preserved).
2. Every `Purisol Coupon` in `C` is bit-for-bit identical to its pre-submit state.
3. Every `Purisol Coupon Booklet` in `B` is bit-for-bit identical to its pre-submit state.
4. No `Comment` is added to any booklet.
5. No `Purisol Coupon Discrepancy` or `Notification Log` record is created.

**This is the "all-or-nothing" guarantee** (FR-034, FR-060).

### 1.4. Errors (blocking validations)

All errors are raised as `frappe.ValidationError` inside the submit transaction via `frappe.throw(_("..."))`. On the first validation pass (`validate`) the message is a single error. In `before_submit`, multiple errors are aggregated into one `<br>`-separated message.

| # | Rule | Error message (template) | Lifecycle hook | Spec reference |
|---|------|--------------------------|----------------|----------------|
| E1 | `coupons` table is empty | `_("Consumption Entry must list at least one coupon.")` | `validate` | FR-030 |
| E2 | Duplicate `coupon` in `coupons` | `_("Coupon {0} appears more than once in this entry.").format(name)` | `validate` | FR-032 |
| E3 | `coupon` link does not resolve to an existing `Purisol Coupon` | `_("Coupon {0} does not exist.").format(name)` | `before_submit` | FR-031 |
| E4 | Referenced coupon's current `status == "Consumed"` | `_("Coupon {0} is already Consumed (recorded on entry {1}).").format(name, prior_entry)` | `before_submit` | FR-033 |
| E5 | `has_warnings != 0` | `_("has_warnings is reserved for Phase 5 and cannot be set.")` | `validate` | FR-035 (defensive) |
| E6 | Any row in `discrepancies_detected` | `_("discrepancies_detected is reserved for Phase 5.")` | `validate` | FR-035 (defensive) |
| E7 | `delivery_man` empty | (default Frappe "Mandatory fields required" for Link field) | form-level | FR-001 |
| E8 | Caller lacks `Purisol Administrator` role | `frappe.PermissionError` | permissions rule | FR-070 |

**Concurrency-race note**: If two submits reference the same coupon and both pass `before_submit`'s status check, the second `on_submit`'s `frappe.db.set_value(..., update_modified=True)` raises `frappe.TimestampMismatchError`; Frappe translates this into a user-visible retry error and rolls back. Behaviourally indistinguishable from E4 from the Administrator's perspective (FR-061, SC-009).

### 1.5. Permissions

| Who | Can call? |
|-----|-----------|
| `Purisol Administrator` | Yes |
| Any other role | `frappe.PermissionError` |

---

## 2. Contract — Cancel a submitted `Purisol Coupon Consumption Entry`

**Operation**: `frappe.get_doc("Purisol Coupon Consumption Entry", name).cancel()` (or form-UI cancel).

### 2.1. Preconditions

1. The caller holds the `Purisol Administrator` role.
2. `self.docstatus == 1`.
3. Every coupon in `self.coupons` still exists (deletion of coupons is permission-denied in Phase 1).

### 2.2. Postconditions (on success)

Let `R`, `C`, `B` as in §1.2. All of the following hold after the cancel transaction commits:

1. `self.docstatus == 2` (cancelled).
2. For **every** `c in C`:
   - `Purisol Coupon[c].status == "Available"`
   - `Purisol Coupon[c].consumed_on == NULL`
   - `Purisol Coupon[c].consumed_by_delivery_man == NULL`
   - `Purisol Coupon[c].consumption_entry == NULL`
3. For **every** `b in B`:
   - `Purisol Coupon Booklet[b].consumed_count == count({c ∈ Purisol Coupon | c.booklet == b ∧ c.status == "Consumed"})` (recomputed)
   - `Purisol Coupon Booklet[b].remaining_count == 20 - consumed_count`
4. For every `b in B` that was `Depleted` pre-cancel AND `self` is the trigger-of-record AND post-cancel `consumed_count < 20`:
   - `Purisol Coupon Booklet[b].status == "Sold"`
   - `Purisol Coupon Booklet[b].depleted_on == NULL`
   - `Purisol Coupon Booklet[b]` has a new `Comment` with body `_("Depletion reverted — entry {0} cancelled.").format(self.name)`.
5. For every `b in B` that stays `Depleted` (because a later entry now holds `consumed_count == 20`):
   - Status unchanged. `consumed_count` and `remaining_count` reflect the post-cancel count.
6. `Purisol Coupon` records not in `C` are unchanged. `Purisol Coupon Booklet` records not in `B` are unchanged.
7. `Sales Invoice` state is unchanged (cancellation of consumption does not touch sales).

### 2.3. Postconditions (on failure)

If any integrity check fails during cancel:

1. `self.docstatus == 1` (submitted state preserved).
2. Every `Purisol Coupon` in `C` is bit-for-bit identical to pre-cancel state.
3. Every `Purisol Coupon Booklet` in `B` is bit-for-bit identical to pre-cancel state.

### 2.4. Errors

Phase 4 does not enumerate a specific "blocked by X" error for cancel — standard Frappe cancel semantics apply, plus `frappe.TimestampMismatchError` on concurrent modifications. The cancel is all-or-nothing by construction (FR-053).

### 2.5. Permissions

Same as §1.5.

---

## 3. Contract — `list_available_coupons(booklet: str) → list[dict]`

**Whitelisted endpoint**: `cx_purisol.cx_purisol.api.consumption.list_available_coupons`

Used by the Mode A widget to render the "tick the coupons the delivery man handed in" checklist.

### 3.1. Inputs

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `booklet` | `str` | Yes | The `name` of an existing `Purisol Coupon Booklet`. |

### 3.2. Output

```json
[
  {"coupon": "CP-00001", "page_number": 1},
  {"coupon": "CP-00002", "page_number": 2},
  ...
]
```

- Always a `list` (may be empty).
- Sorted by `page_number` ascending.
- Contains **only** coupons of the given booklet with `status == "Available"`. `Consumed` coupons are excluded.
- If the booklet doesn't exist, returns `[]` (no error) — the caller (UI) surfaces "Unknown booklet" via a separate check. Rationale: keeps the contract idempotent for the common case where the Administrator deletes and re-types; error surfacing is the UI's job in Mode A (FR-012).

### 3.3. Errors

| # | Condition | Error |
|---|-----------|-------|
| A1 | Caller lacks `Purisol Administrator` role | `frappe.PermissionError` (via `frappe.only_for`) |
| A2 | `booklet` param empty / missing | `frappe.throw(_("Booklet name is required."))` |

### 3.4. Side effects

None. Pure read.

### 3.5. Permissions

| Who | Can call? |
|-----|-----------|
| `Purisol Administrator` | Yes |
| Any other role | `frappe.PermissionError` |

---

## 4. Contract — `resolve_coupons(coupon_numbers: list[str]) → dict`

**Whitelisted endpoint**: `cx_purisol.cx_purisol.api.consumption.resolve_coupons`

Used by the Mode B widget when the Administrator presses Enter (single line) or pastes a block of coupon numbers. Single round trip for a pasted block; the UI renders one row per resolved coupon and one red-line error per unresolved coupon, preserving valid rows on error (FR-020, FR-021, Story 2 scenario 4).

### 4.1. Inputs

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `coupon_numbers` | `list[str]` | Yes | Non-empty list. Blank / whitespace-only entries are filtered out server-side. |

### 4.2. Output

```json
{
  "resolved": [
    {"coupon": "CP-00001", "booklet": "WP-00001", "customer": "Acme Co."},
    {"coupon": "CP-00022", "booklet": "WP-00002", "customer": "Beta Ltd."}
  ],
  "unresolved": ["CP-99999", "CP-abcde"]
}
```

- `resolved` contains **one entry per input coupon_number that resolves to an existing `Purisol Coupon`**. Order is preserved relative to the input (after blank-filtering).
- Each resolved entry carries the coupon's `booklet` and the booklet's `customer` (possibly empty string if the booklet is not `Sold`). Fetched via a single `frappe.get_all` + a single booklet `frappe.get_all`.
- `unresolved` contains every input coupon_number that did NOT resolve, in input order. Includes whitespace-trimmed numbers that still don't resolve.
- The endpoint **does not filter `resolved` by `status`** — an already-`Consumed` coupon still appears in `resolved`. The UI may choose to flag it, but submit-time validation is authoritative (FR-033). Rationale: the Administrator may want to see the row with its current state before deciding to remove it.

### 4.3. Errors

| # | Condition | Error |
|---|-----------|-------|
| B1 | Caller lacks `Purisol Administrator` role | `frappe.PermissionError` (via `frappe.only_for`) |
| B2 | `coupon_numbers` is empty after blank-filtering | `frappe.throw(_("No coupon numbers to resolve."))` |
| B3 | `coupon_numbers` is not a list | (default Frappe type-check error) |

### 4.4. Side effects

None. Pure read. No record is created, modified, or flagged as "reserved" — draft state is not a reservation (spec edge case).

### 4.5. Permissions

| Who | Can call? |
|-----|-----------|
| `Purisol Administrator` | Yes |
| Any other role | `frappe.PermissionError` |

---

## 5. What these contracts deliberately DO NOT include

- **No WebSocket / realtime channel**: Phase 6 will introduce notification emission; Phase 4's submit/cancel does not publish any realtime event.
- **No discrepancy-detection hooks**: Phase 5 will add the "missing coupons" and "unassigned booklet" warning logic, layered on top of these contracts without modifying them.
- **No bulk-creation API**: coupons are consumed one Consumption Entry at a time; bulk-day / backfill imports are explicitly out of scope.
- **No coupon-reassignment API**: a coupon cannot be moved from one entry to another; the Administrator cancels the wrong entry and submits a new one (spec's "cancel + amend" round-trip).
- **No Mode C / machine-to-machine API**: future barcode-scanner integration reuses Mode B's keyboard path; no separate endpoint (FR-022).
