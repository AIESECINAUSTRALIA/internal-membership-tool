from sqlalchemy import text
from sqlalchemy.orm import Session
import pytest

from app.core.audit import record_audit


def test_record_audit_creates_entry(db_session: Session) -> None:
    entry = record_audit(
        db_session,
        action="lc.create",
        resource_type="lc",
        resource_id=1,
        summary="LC 1 created",
    )
    db_session.flush()
    assert entry.id is not None
    assert entry.action == "lc.create"
    assert entry.resource_id == 1
    assert entry.actor_membership_id is None


def test_record_audit_stores_diff(db_session: Session) -> None:
    entry = record_audit(
        db_session,
        action="lc.rename",
        resource_type="lc",
        resource_id=2,
        summary="LC 2 renamed",
        diff={"before": {"name": "Old"}, "after": {"name": "New"}},
    )
    db_session.flush()
    assert entry.diff == {"before": {"name": "Old"}, "after": {"name": "New"}}


def test_update_is_rejected(db_session: Session) -> None:
    record_audit(db_session, action="lc.create", resource_type="lc", summary="test")
    db_session.flush()
    with pytest.raises(Exception, match="append-only"):
        db_session.execute(text("UPDATE audit_log SET summary = 'changed' WHERE TRUE"))
        db_session.flush()


def test_delete_is_rejected(db_session: Session) -> None:
    record_audit(db_session, action="lc.create", resource_type="lc", summary="test")
    db_session.flush()
    with pytest.raises(Exception, match="append-only"):
        db_session.execute(text("DELETE FROM audit_log WHERE TRUE"))
        db_session.flush()
