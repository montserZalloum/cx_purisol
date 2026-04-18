# Contract: Booklet Generation API

**Feature**: `001-core-data-model` · **Date**: 2026-04-18

This is the only externally-callable interface introduced in Phase 1. All other interactions with the Phase-1 DocTypes go through Frappe's standard desk UI and REST endpoints (no custom contract).

---

## `purisol_generate_booklets`

### Module path

`cx_purisol.api.booklet_generation.purisol_generate_booklets`

### Binding

- Decorated `@frappe.whitelist()` — callable from the Frappe desk and from `/api/method/cx_purisol.api.booklet_generation.purisol_generate_booklets`.
- Authorization: caller MUST hold the `Purisol Administrator` role. The function checks this explicitly with `frappe.only_for("Purisol Administrator")` as its first line; a missing role raises `frappe.PermissionError` *before* any DB work.

### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `quantity` | `int` | Yes | Number of booklets to generate. Must be a positive integer. |
| `batch_id` | `str \| None` | No | Optional free-text identifier; written to `Purisol Coupon Booklet.batch_id` on every booklet produced. Trimmed; empty string is treated as `None`. |

Frappe will deliver HTTP query-string values as strings; the function MUST coerce `quantity` with `int(quantity)` and raise a clear error if coercion fails.

### Return value

**Sync path** (`quantity ≤ 20`) — returns a dict:

```json
{
  "mode": "sync",
  "first_booklet": "WP-00001",
  "last_booklet": "WP-00005",
  "total_coupons": 100,
  "batch_id": null
}
```

**Async path** (`quantity > 20`) — returns a dict:

```json
{
  "mode": "async",
  "job_name": "purisol_generate_booklets_<uuid>",
  "channel": "purisol_generate_booklets_progress",
  "quantity": 50
}
```

The actual work happens in the enqueued job; the final summary is delivered via the realtime channel (see "Progress events" below).

### Errors

All error signalling uses standard Frappe exceptions so the desk renders them uniformly:

| Condition | Exception | Message (before `_()`) |
|-----------|-----------|------------------------|
| Caller lacks `Purisol Administrator` role | `frappe.PermissionError` | (Frappe default) |
| `quantity` is missing, non-integer, zero, or negative | `frappe.ValidationError` | `"Quantity must be a positive integer."` |
| Internal DB failure during generation (sync) | Propagates as-is | — |
| Internal DB failure during generation (async) | Caught in job, emitted as `status=failed` progress event; job logs to `frappe.log_error` | — |

No error category is "silent success" (constitution V).

---

## Progress events (realtime)

**Channel**: `purisol_generate_booklets_progress`
**Delivered by**: `frappe.publish_realtime(event=..., message=..., user=<initiating user>)` — scoped to the initiating user so other users don't see other admins' jobs.

### Event payloads

- **Started** (async only, emitted at the start of the job):

  ```json
  {
    "status": "started",
    "job_name": "purisol_generate_booklets_<uuid>",
    "total": 50,
    "done": 0,
    "batch_id": null
  }
  ```

- **Progress** (emitted at most every 1% of the run OR every 500 ms, whichever is less frequent):

  ```json
  {
    "status": "progress",
    "job_name": "...",
    "total": 50,
    "done": 24,
    "last_booklet": "WP-00024"
  }
  ```

- **Complete** (emitted on async success):

  ```json
  {
    "status": "complete",
    "job_name": "...",
    "total": 50,
    "first_booklet": "WP-00001",
    "last_booklet": "WP-00050",
    "total_coupons": 1000,
    "batch_id": null
  }
  ```

- **Failed**:

  ```json
  {
    "status": "failed",
    "job_name": "...",
    "done": 17,
    "error": "Short, user-safe error description"
  }
  ```

The **"complete"** payload has the same shape as the sync-path return value (minus the `mode` discriminator) so UI code can render one summary component regardless of path.

---

## Post-conditions (invariants the contract guarantees)

After a successful call of `purisol_generate_booklets(quantity=N, batch_id=B)`:

1. Exactly `N` new `Purisol Coupon Booklet` records exist relative to the pre-call state, all with `status = "In Stock"` and `batch_id = B` (if `B` was supplied).
2. Exactly `N × 20` new `Purisol Coupon` records exist, all with `status = "Available"`, `page_number ∈ [1, 20]`.
3. For every new booklet with name `WP-K`, exactly 20 coupons link to it with names `CP-((K-1)*20+1)` … `CP-(K*20)` and `page_number` `1` … `20` in matching order.
4. Booklet numbering is contiguous with the pre-call maximum (no gaps, no duplicates).
5. Coupon numbering is contiguous with the pre-call maximum (no gaps, no duplicates).
6. On failure, no partially-constructed booklet (booklet without its 20 coupons) is left behind.
7. On a retry after a failed async run, conditions 1–6 hold relative to the observable state *at retry time*; no numbering from the failed run is re-used or skipped.

Post-conditions 1–7 correspond 1-to-1 with spec SC-001, SC-002, SC-005, SC-006, SC-007.

---

## Out of scope for this contract

- Cancellation of an in-flight async job (deferred).
- Scheduling or deferred-start generation (deferred).
- Progress persistence beyond the realtime channel (deferred).
- Emission of any notification event other than generation progress (deferred to Phase 5).
