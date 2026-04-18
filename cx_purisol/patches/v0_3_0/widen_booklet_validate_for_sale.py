"""No-op anchor for sites migrated through Phase 3 (003-sales-integration).

On fresh installs this patch has no effect. On upgraded sites it marks that
the booklet controller's _ALLOWED_STATUSES and _ALLOWED_TRANSITIONS have been
widened to include the Sold state and the In Stock|In Custody -> Sold transitions.
"""


def execute():
    pass
