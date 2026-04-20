# Phase 0 Research — Notifications

**Feature**: 006-notifications | **Date**: 2026-04-19

This document resolves every `NEEDS CLARIFICATION` flag implicit in the Technical Context and documents, for each non-trivial choice, the **decision**, the **rationale**, and the **alternatives considered**. All decisions are tight-bounded by the Phase-6 spec, the Purisol constitution, and the realities of the existing Phase 1–5 codebase.

---

## 1. Where does the `Purisol Notify` utility module live?

**Decision**: `cx_purisol/cx_purisol/api/notify.py` — a plain Python module, not whitelisted, co-located with the other phase-level service modules already in the `api/` folder (`discrepancy.py`, `consumption.py`, `sell_booklets.py`, `booklet_generation.py`).

**Rationale**:
- Matches the existing project convention — `api/` already houses server-side service modules (not just `@frappe.whitelist()`-decorated endpoints). Phase 5's detection service sits here.
- A dedicated `notifications/` subpackage was considered but would introduce a new folder for a single file, which is heavier than needed for MVP. If Phase 7+ adds additional notification-adjacent modules (preference store, digest builder), the code can migrate then without breaking callers — the caller imports `from cx_purisol.cx_purisol.api import notify`, a single-line change regardless of path.
- The "not whitelisted" choice is explicit: Phase 6 notifications must not be callable from external HTTP requests. The four trigger sites are the only legitimate callers, all server-internal.

**Alternatives considered**:
- *New `cx_purisol/cx_purisol/notifications/` subpackage* — rejected for MVP (overkill for one file).
- *Top-level `cx_purisol/notifications.py`* — rejected; the `cx_purisol/cx_purisol/` nested module is the Frappe convention for app code, and mixing top-level utility modules would diverge from Phases 1–5.
- *As a method on `Purisol Settings` controller* — rejected; the utility has no state and is not a DocType concern. Method-on-controller would imply singleton scope and would muddle "this is configuration" with "this is plumbing".

---

## 2. What does the channel-dispatcher abstraction actually look like in Phase 6?

**Decision**: `send(recipient, subject, message, reference_doctype=None, reference_name=None)` is the sole public function. Internally, it resolves the recipient to a list of enabled users (`_resolve_recipients`) and then calls `_emit_bell(user, subject, message, reference_doctype, reference_name)` for each — the only channel registered in Phase 6. No explicit registry, no `channel` parameter, no dispatcher class. A future phase adds `_emit_email`, `_emit_sms`, etc., and modifies `send` to fan out to each registered channel; the trigger-site signature does not change.

**Rationale**:
- Matches constitution VII ("a dispatcher routes the event to registered channels") while avoiding YAGNI for Phase 6. An explicit registry with pluggable handlers is deferred until there are actually ≥2 channels to plug in.
- The spec FR-001 requires "a single `send()` function that every Phase 6 trigger calls" — making `channel` a call-site argument would violate that (call sites would have to know about channels).
- Keeps the utility under ~80 lines of Python — easy to audit, easy to test, easy to extend.
- The "channel" concept lives in Phase 6 as comments and private function names (`_emit_bell`), not as a user-facing abstraction. Future phases that add channels need to touch only this module, never a trigger site — which is precisely the extensibility contract the constitution requires.

**Alternatives considered**:
- *Channel registry with decorator-based registration* (`@register_channel("bell")` etc.) — rejected as YAGNI for one channel. Adds a class and an import-time side effect for no current benefit.
- *Per-channel boolean flags on `Purisol Settings`* (`enable_bell`, `enable_email`, …) — rejected for Phase 6 since only one channel exists; adding flags now would require a migration later to re-interpret them. The "feature flag per channel" decision belongs to the phase that actually adds ≥2 channels.
- *Making `send` accept a `channels` list argument with a default of `["bell"]`* — rejected. Exposes the channel concept to callers, violating the constitution's "trigger emits an abstract event" principle. Trigger code should not know whether the dispatcher ships the message over bell or email.

---

## 3. How is Warehouse Low Stock dedup stored?

**Decision**: Add one new field `last_warehouse_low_stock_notified_on` (fieldtype `Date`, read-only, hidden) to `Purisol Settings`. The warehouse trigger reads this field, compares to `frappe.utils.today()`, and updates it via `frappe.db.set_single_value("Purisol Settings", "last_warehouse_low_stock_notified_on", frappe.utils.today())` after firing a notification.

**Rationale**:
- **Correctness under concurrency**: `Purisol Settings` is a singleton (one row in `tabSingles`). Concurrent Sales Invoice submits that both qualify for the warehouse trigger both run `check_warehouse_low_stock`. The check-then-set pattern is race-prone in principle, but in practice (a) MariaDB's default READ-COMMITTED isolation means the second submit reads the first's update if the first has committed, and (b) if both have read "not set" before either writes, both will fire — which is an acceptable worst case at single-shop scale (2 bell entries instead of 1 is a noise issue, not a correctness issue). Spec does not require strict at-most-once under concurrency; it requires "at most once per day" which is functionally achieved.
- **Simplicity vs. query-based dedup**: The alternative — query `Notification Log` for today's existing warehouse-low-stock entries via subject matching — is fragile: any subject-phrase change (localization, minor copy edit) silently breaks dedup. A dedicated field is explicit and unambiguous.
- **Minimal schema footprint**: Single Date field, read-only (no admin interaction), hidden (does not clutter Settings UI). The spec explicitly permits this ("MAY be stored on `Purisol Settings` as a new transient field" — FR-016).
- **Audit trail**: `Purisol Settings` has `track_changes = 1` from Phase 1, so the field's update history is recorded in `tabVersion` — satisfies constitution IV passively.

**Alternatives considered**:
- *Query `Notification Log` by subject/date* — rejected for fragility (see above).
- *Dedicated `Purisol Warehouse Low Stock Log` DocType* — rejected; massive overkill for a single boolean-per-day.
- *Redis / in-memory cache* — rejected; does not survive worker restarts and is not visible to concurrent workers unless a shared Redis is guaranteed (Frappe default but not part of the spec contract). A database field is the definitive cross-worker truth.
- *`frappe.cache().set_value(..., expires_in_sec=86400)`* — rejected; same concern as pure Redis, plus it does not survive Bench restarts, plus it is harder to audit than a DocType field.

---

## 4. Where in the Consumption Entry `on_submit` lifecycle do Phase-6 triggers run?

**Decision**: Both Phase-6 triggers (Booklet Depleted, Customer Low Stock) run **inside** the existing `on_submit` method, in the following order:

1. Phase-4 coupon flips (unchanged).
2. Phase-4 booklet aggregate update — **widened** to call `notify.send(...)` inside the existing `if triggered_depletion:` block, immediately after the booklet's `.save(...)` and `add_comment(...)` (so the notification emits only if the transition actually happened).
3. Phase-5 `detect_for_entry(self)` (unchanged).
4. Phase-5 `has_warnings` / `discrepancies_detected` population (unchanged).
5. **NEW** — after all the above, iterate over the unique customers among affected Sold booklets and call `notify.send(...)` per qualifying customer.

The Customer Low Stock pass runs last because it depends on booklet aggregates being fully recomputed (for the customer's total remaining). The Booklet Depleted call is inlined with the depletion branch because that is the single point in the codebase where `status → Depleted` happens; FR-010 requires the notification to be emitted from that specific call site.

**Rationale**:
- **Atomicity**: all trigger calls run inside the `on_submit` transaction. A raise in any trigger (infrastructure failure, misconfigured role) rolls the whole submit back, matching FR-015 and SC-008. The same atomicity posture Phase 5 adopted for discrepancy detection (research.md §1 of 005) applies here verbatim: Phase-6 triggers have no business-rule failures of their own — they are pure read-and-insert against ERPNext's own `Notification Log` — so any raise is necessarily infrastructure-level, and rolling back is the correct posture.
- **Order — why Customer Low Stock runs after discrepancy detection**: if a consumption entry triggers both a discrepancy and a customer-low-stock condition, both notifications fire. The `after_insert` on the discrepancy fires during step 3; the customer-low-stock fires during step 5. Two independent notifications, which is the intended behaviour per spec (discrepancy via Story 1, customer-low-stock via Story 2 — each Administrator user gets both).
- **Order — why Booklet Depleted is co-located with the depletion branch**: if we emit the Booklet Depleted notification in a generic post-loop pass, we'd lose the exact context (which booklet just transitioned). Inlining keeps the trigger site next to the state-change site — this is FR-010's explicit requirement and is the same principle Phase 5 follows for `triggering_consumption_entry`.

**Alternatives considered**:
- *Emit notifications in `after_submit` (post-commit)* — rejected. Decouples the notification from the triggering event; a crash between `on_submit` commit and `after_submit` run would silently drop notifications. Violates FR-015's "same transaction".
- *Run Customer Low Stock check BEFORE depletion*  — rejected. Depletion changes `status` from `Sold` to `Depleted`, which removes the booklet from the "Sold non-Depleted" total. If we ran customer-low-stock first, a booklet that just depleted would still contribute to the customer's remaining, over-counting. Running depletion first produces the correct post-depletion total.
- *Dispatch via a generic `after_state_change` observer pattern on the booklet* — rejected as Phase-6 overkill; inline is clearer.

---

## 5. How is the set of enabled Administrator users determined?

**Decision**:

```python
def _resolve_recipients(recipient: str) -> list[str]:
    # Role-first: try matching as a Role name
    if frappe.db.exists("Role", recipient):
        # Users who hold this role AND are enabled
        user_rows = frappe.get_all(
            "Has Role",
            filters={"role": recipient, "parenttype": "User"},
            pluck="parent",
        )
        if not user_rows:
            return []
        enabled = frappe.get_all(
            "User",
            filters={"name": ["in", user_rows], "enabled": 1},
            pluck="name",
        )
        return enabled

    # User fallback: exact User name match
    if frappe.db.exists("User", recipient):
        is_enabled = frappe.db.get_value("User", recipient, "enabled")
        return [recipient] if is_enabled else []

    # Neither a role nor a user — empty, no error
    return []
```

**Rationale**:
- **Role-first**: the spec consistently passes the role name (`"Purisol Administrator"`), not individual users. Checking Role first avoids a lookup-miss on User when the caller always passes a role.
- **Disabled users excluded**: spec edge case "Disabled user with the Administrator role" — Phase 6 silently skips them.
- **Silent no-op on unknown input**: FR-014 requires "no error, no partial writes" when the recipient set is empty. Returning `[]` and letting the caller's `for user in resolved:` loop become a no-op is the cleanest pattern.
- **Two round-trip queries in the role path**: one to `Has Role` + one to `User`. Could be collapsed into a single JOIN via `frappe.db.sql`, but `frappe.get_all` is the convention across the codebase and the queries are indexed and fast.

**Alternatives considered**:
- *`frappe.get_all("User", filters={"role_profile_name": ...})`* — rejected; role-profile-based lookup matches only users with that role profile set, not users who hold the role directly. The `Has Role` child table is the general path.
- *Cache the resolved list for the request's lifetime* — rejected for MVP. At single-admin scale (1–3 admins), re-resolving per call is trivially cheap. A cache would add staleness risk (admin added/disabled mid-session) without meaningful performance gain.
- *Parallel-dispatch via `frappe.enqueue`* — rejected. Adds latency (queue pickup) without helping atomicity, and the volumes do not warrant it (constitution VIII).

---

## 6. What does `Notification Log` record shape look like?

**Decision**: Each `Notification Log` entry created by `_emit_bell`:

```python
frappe.get_doc({
    "doctype": "Notification Log",
    "type": "Alert",
    "subject": subject,                          # short, localized, with interpolated fields
    "email_content": message,                    # body — can be plain text or HTML; Phase 6 uses plain text
    "for_user": user_name,                       # one entry per recipient user
    "document_type": reference_doctype or None,  # e.g. "Purisol Coupon Discrepancy"
    "document_name": reference_name or None,     # e.g. "PCD-2026-00001"
    "from_user": None,                           # system-generated
}).insert(ignore_permissions=True)
```

- `type = "Alert"` is the ERPNext bell-icon type (vs. `"Mention"`, `"Energy Point"`). This is what appears in the bell dropdown.
- `email_content` is the body field on `Notification Log` (Frappe's naming is historical — "email_content" is used for bell body too; not an email-specific artifact).
- `ignore_permissions=True` is required because the triggering submit already performed the permission check on the host event; the recipient user may not have permission to "create a Notification Log for themselves", but the system does on their behalf.

**Rationale**:
- ERPNext's `Notification Log` is the canonical bell-icon DocType — this is the standard payload shape. No custom fields needed.
- Plain text for Phase 6 body: the spec mentions "body" and a prescribed phrase template; HTML would be overkill. If Phase 7 introduces richer content (click-through buttons, multiple links in one notification), we can switch to HTML without breaking anything.
- Empty `document_name` is valid for the warehouse trigger — Frappe routes `document_type = "Purisol Coupon Booklet"` with no `document_name` to the list view, which is the correct behaviour for FR-009.

**Alternatives considered**:
- *Set `type = "Mention"` to make notifications more prominent* — rejected. "Mention" is semantically "user was @-referenced"; "Alert" is the correct type for system-generated notifications.
- *Populate `from_user = "Administrator"`* — rejected. Suggests a human performed the action, which is misleading. Leaving `from_user` blank correctly communicates system origin.
- *Persist notification body as HTML with styled headers* — deferred to a future phase if the plain-text body turns out to be hard to scan in the bell dropdown.

---

## 7. How do the four subject/body templates look exactly?

**Decision** (all phrases wrapped in `frappe._()`; `{N}` placeholders):

| Trigger | Subject template | Body template |
|---------|------------------|---------------|
| New Discrepancy Opened | `Discrepancy {0} opened` | `Discrepancy {0} opened: {1} in booklet {2}, delivery man {3}.` |
| Customer Low Stock | `Customer {0} low on coupons` | `Customer {0} has {1} coupons remaining. Prepare a new booklet.` |
| Warehouse Low Stock | `Warehouse low on booklet stock` | `Only {0} booklets remain in stock. Generate a new batch.` |
| Booklet Depleted | `Booklet {0} depleted` | `Booklet {0} for customer {1} is fully consumed. Follow up for resale.` |

**Rationale**:
- Subjects are short (< 60 chars) so they render fully in the bell dropdown.
- Bodies match PRD Section 10 phrasing (slight wording tweaks for grammar + localization-friendly placeholder order).
- `{N}` numeric placeholders let Arabic translations reorder the words (e.g., "{0} booklet {2} in {1} discrepancy opened") without code changes.
- Discrepancy body interpolates: `{0} = discrepancy name (PCD-2026-xxxxx)`, `{1} = discrepancy_type (translated)`, `{2} = booklet.name (WP-xxxxx)`, `{3} = consumption_entry.delivery_man (Employee name)`.
- Customer Low Stock body interpolates: `{0} = customer_name (from Customer.customer_name, not the raw Customer ID)`, `{1} = total_remaining (int)`.
- Warehouse Low Stock body interpolates: `{0} = in_stock_count (int)`.
- Booklet Depleted body interpolates: `{0} = booklet.name`, `{1} = customer_name` (from `Customer.customer_name`; falls back to `booklet.customer` raw ID if the Customer record can't be resolved — extremely unlikely but defensive).

**Alternatives considered**:
- *Include more fields in the body (e.g. posting date, entry name)* — rejected for MVP; keeps the bell dropdown compact. Administrators can click through to the referenced record for detail.
- *HTML formatting with bold / colors* — rejected for Phase 6 plain-text bodies; revisit if noise becomes a problem.
- *Emit separate "short" and "long" messages (subject vs. body)* — adopted as-is in the decision above; subject is the one-liner, body is the fuller one-liner.

---

## 8. How does the triggering delivery man get into the discrepancy notification body?

**Decision**: The `after_insert` on `PurisolCouponDiscrepancy` reads `self.triggering_consumption_entry` and fetches the `delivery_man` field:

```python
delivery_man = frappe.db.get_value(
    "Purisol Coupon Consumption Entry",
    self.triggering_consumption_entry,
    "delivery_man",
)
```

If `triggering_consumption_entry` is set (it always is for auto-created discrepancies per spec FR-005), this produces the employee name. The Phase-6 subject/body templates interpolate it directly.

**Rationale**:
- Single indexed `get_value` — cheap.
- Uses `triggering_consumption_entry` as the source of truth; avoids requiring the detection service to pass `delivery_man` as an extra argument.
- If a future path inserts a `Purisol Coupon Discrepancy` without a triggering entry (not an MVP path), the `get_value` returns `None` and the template renders `"delivery man None"` — acceptable degenerate case for a non-MVP scenario.

**Alternatives considered**:
- *Pass `delivery_man` as an explicit argument to `notify.send()`* — rejected; would require widening the `send` signature beyond its channel-agnostic shape. Better to lookup at the notification-construction site.
- *Denormalize `delivery_man` onto `Purisol Coupon Discrepancy`* — rejected; adds a field that duplicates data already available through the `triggering_consumption_entry` link. Constitution IV prefers derived values over copies.

---

## 9. Interaction with Phase-4 / Phase-5 tests

**Decision**: Phase-4 and Phase-5 integration tests do not currently assert "zero Notification Log entries". Phase 6 adds notifications that will fire from any Consumption Entry submit that deletes a booklet or drops a customer below threshold — both conditions that Phase-4 tests may incidentally exercise.

Action: **No Phase-4 or Phase-5 test changes are required**. Phase-6 tests assert notification behaviour via **delta assertions** (`count_notifications(for_user=admin)` before vs. after the action), not absolute counts, so they are robust against the ambient Notification Log state. Phase-4 tests that happen to trigger a Phase-6 notification as a side effect continue to pass because they never looked at the Notification Log table.

One defensive check: Phase-6 tests re-seed the `Purisol Administrator` user fresh (idempotent), so their delta assertions are against that user — not any pre-existing admin — which avoids cross-test bleed.

**Rationale**:
- Minimizes change surface. Phase 4 and Phase 5 tests have been green for months; touching them risks introducing regressions unrelated to Phase 6.
- Delta-based assertions are the Frappe-community convention for testing notification-like side effects — absolute-count assertions are brittle.
- Zero new Phase-4/5 "flakiness" introduced: the new notifications are atomic with the triggering submit, so the submit either succeeds with the notification or rolls back the whole thing — there is no partial state.

**Alternatives considered**:
- *Truncate `Notification Log` in `setUp`/`tearDown`* — rejected. Affects other concurrent tests and couples Phase 6 fixtures to an assumption about Notification Log ownership. The delta-check pattern is simpler and strictly local.
- *Disable Phase-6 notifications in the test site via a setting* — rejected. Would mean tests exercise a different code path than production; defeats the point of integration testing.

---

## 10. Warehouse-dedup: does it reset at midnight automatically?

**Decision**: No scheduled job. Reset is implicit — `last_warehouse_low_stock_notified_on` is compared to `frappe.utils.today()` at each qualifying trigger. When the server's date rolls over, the next comparison naturally fails the dedup check and the next qualifying submit fires.

**Rationale**:
- Zero moving parts. No cron, no enqueued job, no scheduler event to wire.
- Matches the spec's "resets at day-boundary rollover" wording without requiring an actual rollover action.
- If the shop opens at 6am and the trigger fires at 6:30am, the stored date is today. Tomorrow at any time, `today()` returns tomorrow's date, the comparison fails, next qualifying trigger fires. No gap, no over-fire.
- If the server is down across a day boundary (unlikely in practice for a shop-POS-style deployment), the next qualifying trigger after the restart fires fresh on the new day — expected behaviour.

**Alternatives considered**:
- *Nightly scheduled job that clears the field* — rejected as unnecessary. The comparison-at-read-time produces the same user-visible behaviour with zero extra code.
- *Store the date alongside the notification's Notification Log entry (queryable for dedup)* — rejected; couples dedup to subject-line matching (see §3).

---

## 11. What happens if `Notification Log` DocType itself is missing (e.g. a stripped-down Frappe install)?

**Decision**: Phase 6 assumes `Notification Log` is available. It ships in standard Frappe Framework 15.x. If a deployment disables it, `_emit_bell`'s `.insert()` raises `DoesNotExistError` and the trigger's host submit rolls back — which is a deployment issue, not a Phase-6 bug. We do not add a "is Notification Log available?" guard because absence indicates a misconfigured Frappe, and silently skipping would hide that misconfiguration.

**Rationale**:
- Standard Frappe ships Notification Log. The spec's dependency section makes this assumption explicit.
- Adding a guard would be defensive code against a scenario that cannot occur in supported environments.
- The failure mode (submit rolls back with a clear error) surfaces the deployment issue early — which is better than silently dropping notifications.

**Alternatives considered**:
- *Runtime check with graceful degradation* — rejected for reasons above. A deployment that disables Notification Log cannot support Phase 6's feature, so degradation would mask a real misconfiguration.

---

## 12. How are Arabic translations delivered?

**Decision**: All new `_()`-wrapped phrases introduced by Phase 6 are appended to `cx_purisol/translations/ar.csv` in the standard Frappe translation-file format (`english_source_string,arabic_translation_string`). The strings are:

| English source | Arabic translation |
|----------------|--------------------|
| `Discrepancy {0} opened` | `فُتح التباين {0}` |
| `Discrepancy {0} opened: {1} in booklet {2}, delivery man {3}.` | `فُتح التباين {0}: {1} في الدفتر {2}، المندوب {3}.` |
| `Customer {0} low on coupons` | `العميل {0} على وشك نفاد القسائم` |
| `Customer {0} has {1} coupons remaining. Prepare a new booklet.` | `لدى العميل {0} {1} قسيمة متبقية. جهّز دفتراً جديداً.` |
| `Warehouse low on booklet stock` | `مخزون الدفاتر منخفض في المستودع` |
| `Only {0} booklets remain in stock. Generate a new batch.` | `لم يتبقَّ سوى {0} دفاتر في المخزون. أنشئ دفعة جديدة.` |
| `Booklet {0} depleted` | `نفاد الدفتر {0}` |
| `Booklet {0} for customer {1} is fully consumed. Follow up for resale.` | `الدفتر {0} للعميل {1} مستهلك بالكامل. تابع لإعادة البيع.` |

**Rationale**:
- Numeric placeholders (`{0}`, `{1}`, ...) preserve field identities across translation. In the discrepancy body, the Arabic version reorders `{0}`, `{1}`, `{2}`, `{3}` positions without requiring code changes.
- Arabic phrasing uses natural Arabic sentence structure (verb-subject-object where English is subject-verb-object for some templates).
- Translations are reviewed by a native Arabic-speaking deployment owner before Phase 6 ships; the table above is the first-draft baseline.

**Alternatives considered**:
- *Separate `.po`/`.mo` files* — rejected; Frappe uses CSV natively, aligning with the existing `ar.csv` already shipped for Phases 1–5.
- *Skip Arabic for Phase 6, ship English only* — rejected; violates constitution IX ("Arabic and English MUST both render correctly").

---

## 13. Does disabling `Purisol Settings.enable_consumption_warnings` disable Phase-6 notifications?

**Decision**: No. `enable_consumption_warnings` is a Phase-5 toggle that governs the post-submit modal dialog on Coupon Consumption Entry (a UX surface). Phase 6 notifications are a separate, always-on feature. If an administrator wants to mute bell notifications, that is a Phase-7+ preferences feature and is out of scope for Phase 6.

**Rationale**:
- Coupling two different features to a single flag would confuse the admin ("I disabled warnings and now I get no discrepancy bell alerts — why?").
- The spec's Phase-6 out-of-scope list explicitly includes a "notification-preferences UI" — muting individual triggers is deferred.
- The flag's name refers specifically to "consumption warnings" (the modal), not to alerts broadly. Re-interpreting it would require renaming the field, which is more intrusive than leaving the two features orthogonal.

**Alternatives considered**:
- *Repurpose `enable_consumption_warnings` to also gate the New Discrepancy bell notification* — rejected for reasons above. If the admin wants to mute it, a Phase-7 per-trigger toggle is the clean path.
- *Add four new boolean flags on `Purisol Settings` (`enable_customer_low_stock_notifications`, etc.)* — rejected for MVP. "Always fire all four" is the simplest, most visible baseline; opt-out is a later iteration.

---

## 14. Is a patch needed?

**Decision**: Yes — one post-model-sync entry, `cx_purisol.patches.v0_6_0.add_warehouse_low_stock_dedup_field`. The patch body is a no-op anchor (`print` message announcing Phase-6 migration). Matches the Phase 2/3/4/5 pattern.

**Rationale**:
- On fresh installs, the new field on `Purisol Settings` lands via the JSON merge at install time — no data migration needed.
- On upgraded sites, the field is added as null on the existing singleton row via Frappe's automatic schema-migration. The patch is an explicit anchor that tells "this site has been through Phase 6" without needing to interpret `tabSingles` state.
- Having an explicit anchor makes it easy to diagnose "did this site go through Phase 6?" by inspecting `tabPatch Log` — consistent with the prior-phase convention.

**Alternatives considered**:
- *Skip the patch entirely* — rejected. Diverges from the established anchor pattern.
- *Make the patch actually set the field to null on all existing Purisol Settings rows* — unnecessary; `frappe.db.set_single_value(..., None)` would be a no-op because Frappe's schema migration initialises new fields to their default (empty for Date).

---

## 15. Performance — any concern about the per-customer SUM query?

**Decision**: The Customer Low Stock pass runs one `SELECT SUM(remaining_count) FROM tabPurisol Coupon Booklet WHERE customer = %s AND status = 'Sold'` query per unique customer affected by the consumption entry. At single-shop scale (dozens of customers total, 1–3 affected per entry), this is trivial — sub-millisecond per query on an indexed customer column.

**Rationale**:
- The `customer` field on `Purisol Coupon Booklet` is link-indexed (Frappe defaults); aggregation on an indexed key over a few dozen rows is fast.
- A realistic worst-case entry touches 5 distinct customers → 5 queries; still well under any performance threshold.
- A `frappe.get_all(..., filters, fields=["customer", "remaining_count"])` + Python-side sum would be slightly faster for many customers but adds complexity; chosen SQL-sum is simpler and correct.

**Alternatives considered**:
- *Single query fetching all affected customers' remainings in one go* — marginal benefit at MVP scale; can optimise later if profiling shows hot path.
- *Materialise `Customer.total_remaining_coupons` as a denormalized field updated by consumption/sale hooks* — rejected as premature optimisation. Would add write-path complexity across Phases 3, 4, 6 for performance wins that single-shop scale does not require.

---

## 16. Why not use the existing ERPNext `Notification` DocType (the rules-based one)?

**Decision**: ERPNext ships two related-but-distinct DocTypes:
- `Notification` (a configuration record: "when X happens on DocType Y, send email/alert to Z") — a rules engine.
- `Notification Log` (a log of actual delivered notifications — one row per sent alert, which is what appears in the bell icon).

Phase 6 writes directly to `Notification Log` (the log), not to `Notification` (the rules engine). The rules engine would let us declare "when Purisol Coupon Discrepancy is inserted, send to Purisol Administrator" via UI configuration without Python code — but it has two problems:
1. It does not support the condition logic we need (threshold comparison for customer-low-stock, per-day dedup for warehouse-low-stock).
2. It is configuration, not code — migrating it across environments requires fixture records, which complicates testing.

So we skip the rules-engine and emit directly.

**Rationale**:
- Matches the plan's "Notifications are created programmatically via Server Scripts" (PRD §9.7) — direct log writes are the Python-code equivalent.
- Keeps conditions in Python where they can be unit-tested.
- Deferred: a future phase that wants declarative notification rules for *simple* cases (e.g. "any Submittable cancel → alert") can introduce `Notification` DocType records alongside the Phase 6 `Purisol Notify` utility — they coexist fine.

**Alternatives considered**:
- *Use `Notification` DocType for the static-rule triggers (discrepancy, depletion)* — rejected for now (consistency: all four triggers go through one Python utility). Revisit in Phase 7+ if UI-configurable notifications become a requirement.

---
