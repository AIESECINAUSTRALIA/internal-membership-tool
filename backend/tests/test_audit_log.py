"""`audit_log` is append-only, enforced by the database (spec §8.4).

The tamper tests use raw SQL on purpose: they prove the *database* rejects
the change, not just that our Python code never issues it. They run as the
same role the app connects with (the table owner, and a superuser in local
Docker and CI), which is the hardest case — see `docs/data-model.md`.

A rejected statement aborts the surrounding Postgres transaction, so each
tamper attempt gets its own test (the `db_session` fixture rolls back after).
"""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.models.privacy import AuditLog


def _write_entry(session: Session) -> AuditLog:
    return record_audit(
        session,
        action="permission_matrix.update",
        resource_type="permission_matrix",
        resource_id=42,
        summary="Granted edit on kpi_record to LCVP",
        actor_membership_id=7,
        diff={"before": {"can_edit": False}, "after": {"can_edit": True}},
    )


def test_record_audit_inserts_a_readable_row(db_session: Session) -> None:
    entry = _write_entry(db_session)

    stored = db_session.execute(select(AuditLog).where(AuditLog.id == entry.id)).scalar_one()

    assert stored.action == "permission_matrix.update"
    assert stored.resource_type == "permission_matrix"
    assert stored.resource_id == 42
    assert stored.actor_membership_id == 7
    assert stored.actor_person_id is None
    assert stored.diff == {"before": {"can_edit": False}, "after": {"can_edit": True}}
    assert stored.created_at is not None


def test_record_audit_accepts_a_sign_in_with_only_a_person(db_session: Session) -> None:
    # Sign-ins happen before a membership is chosen (spec §8.4).
    entry = record_audit(
        db_session,
        action="auth.sign_in",
        resource_type="person",
        resource_id=3,
        summary="Signed in to the main app",
        actor_person_id=3,
    )

    assert entry.id is not None
    assert entry.actor_membership_id is None
    assert entry.diff is None


def test_update_is_rejected_by_the_database(db_session: Session) -> None:
    entry = _write_entry(db_session)

    with pytest.raises(DBAPIError, match="append-only"):
        db_session.execute(
            text("UPDATE audit_log SET summary = 'tampered' WHERE id = :id"), {"id": entry.id}
        )


def test_delete_is_rejected_by_the_database(db_session: Session) -> None:
    entry = _write_entry(db_session)

    with pytest.raises(DBAPIError, match="append-only"):
        db_session.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": entry.id})


def test_delete_is_rejected_even_in_replica_mode(db_session: Session) -> None:
    # `session_replication_role = replica` normally switches triggers off for
    # the session — a bypass needing no schema change. The triggers are
    # created `ENABLE ALWAYS`, so they still fire. (Setting the role needs a
    # superuser, which local Docker and CI connect as.)
    entry = _write_entry(db_session)
    db_session.execute(text("SET LOCAL session_replication_role = replica"))

    with pytest.raises(DBAPIError, match="append-only"):
        db_session.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": entry.id})


def test_truncate_is_rejected_by_the_database(db_session: Session) -> None:
    # Row-level triggers don't fire on TRUNCATE, so this needs its own guard.
    _write_entry(db_session)

    with pytest.raises(DBAPIError, match="append-only"):
        db_session.execute(text("TRUNCATE audit_log"))
