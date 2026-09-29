"""The one place to write an audit-log entry (spec §8.4).

Every privacy/config action and every sign-in calls `record_audit`. Logged at
minimum: permission-matrix changes, membership create/close, KPI record
create/edit/delete, deletion-request state changes, report generation, and
sign-ins (main app and Admin console). Page views are **not** logged.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.models.privacy import AuditLog


def record_audit(
    session: Session,
    *,
    action: str,
    resource_type: str,
    summary: str,
    resource_id: int | None = None,
    actor_membership_id: int | None = None,
    actor_person_id: int | None = None,
    diff: dict[str, Any] | None = None,
) -> AuditLog:
    """Add an audit entry to `session` and flush it; **does not commit**.

    The entry joins the caller's transaction, so it is saved if and only if
    the change it describes is saved: call this in the same session, before
    that session commits.

    - `action`: `<resource>.<verb>`, e.g. `kpi_record.edit`, `auth.sign_in`.
    - `summary`: a human-readable one-liner shown in the Admin console.
    - Actor: pass `actor_membership_id` for normal actions, `actor_person_id`
      for sign-ins (no membership is chosen yet), neither for `system`.
    - `diff`: `{"before": ..., "after": ...}` for config-type changes. It must
      **never contain personal data** (names, emails) — entries can't be edited
      or deleted later, so a leak here is permanent. Refer to people by id.
    """
    entry = AuditLog(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        summary=summary,
        actor_membership_id=actor_membership_id,
        actor_person_id=actor_person_id,
        diff=diff,
    )
    session.add(entry)
    session.flush()
    return entry
