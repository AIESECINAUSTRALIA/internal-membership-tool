"""The one place to write an audit-log entry (spec §8.4).

Every membership write, config action, and sign-in calls `record_audit`.
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
    """Add an audit entry to `session` and flush it; does not commit.

    - `action`: `<resource>.<verb>`, e.g. `membership.create`, `membership.extend_term`.
    - `summary`: human-readable one-liner.
    - `diff`: before/after dictionary. Must NEVER contain PII (names, emails).
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
