from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.membership import Membership
from app.models.org import LCType
from app.models.privacy import AuditLog
from app.repositories.lc import (
    LC_DEFAULT_TIMEZONE,
    create_lc,
    deactivate_lc,
    get_lc,
    list_lcs,
    rename_lc,
    resolve_timezone,
    set_lc_state,
)
from tests.helpers import (
    make_lc,
    make_membership,
    make_person,
    make_position,
    make_state_timezone,
    make_term,
)


def test_list_lcs_returns_active_only_by_default(db_session: Session) -> None:
    active = make_lc(db_session, name="Active LC")
    inactive = make_lc(db_session, name="Inactive LC")
    inactive.active = False
    db_session.flush()

    result = list_lcs(db_session)

    ids = [lc.id for lc in result]
    assert active.id in ids
    assert inactive.id not in ids


def test_list_lcs_include_inactive(db_session: Session) -> None:
    active = make_lc(db_session, name="Active LC")
    inactive = make_lc(db_session, name="Inactive LC")
    inactive.active = False
    db_session.flush()

    result = list_lcs(db_session, include_inactive=True)

    ids = [lc.id for lc in result]
    assert active.id in ids
    assert inactive.id in ids


def test_get_lc_returns_lc(db_session: Session) -> None:
    lc = make_lc(db_session)
    assert get_lc(db_session, lc.id) is lc


def test_get_lc_returns_none_for_unknown_id(db_session: Session) -> None:
    assert get_lc(db_session, 999999) is None


def test_resolve_timezone_uses_state_timezone_lookup(db_session: Session) -> None:
    make_state_timezone(db_session, state="NSW", timezone="Australia/Sydney")
    lc = make_lc(db_session)
    lc.state = "NSW"
    db_session.flush()

    assert resolve_timezone(db_session, lc_id=lc.id) == "Australia/Sydney"


def test_resolve_timezone_defaults_when_no_state(db_session: Session) -> None:
    lc = make_lc(db_session)
    # lc.state is None — no state set

    assert resolve_timezone(db_session, lc_id=lc.id) == LC_DEFAULT_TIMEZONE


def test_resolve_timezone_defaults_when_state_not_in_lookup(db_session: Session) -> None:
    lc = make_lc(db_session)
    lc.state = "ZZ"  # not a real state, no row in state_timezone
    db_session.flush()

    assert resolve_timezone(db_session, lc_id=lc.id) == LC_DEFAULT_TIMEZONE


def test_create_lc_inserts_row(db_session: Session) -> None:
    lc = create_lc(db_session, name="AIESEC in Newtown", lc_type=LCType.LC)
    assert lc.id is not None
    assert lc.name == "AIESEC in Newtown"
    assert lc.active is True
    assert lc.state is None


def test_create_lc_with_state(db_session: Session) -> None:
    lc = create_lc(db_session, name="AIESEC in Sydney", lc_type=LCType.LC, state="NSW")
    assert lc.state == "NSW"


def test_create_lc_writes_audit_entry(db_session: Session) -> None:
    lc = create_lc(db_session, name="AIESEC in Audit City", lc_type=LCType.LC)
    entry = db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "lc.create",
            AuditLog.resource_id == lc.id,
        )
    ).scalar_one()
    assert entry is not None


def test_rename_lc_updates_name(db_session: Session) -> None:
    lc = make_lc(db_session, name="Old Name")
    rename_lc(db_session, lc_id=lc.id, new_name="New Name")
    assert lc.name == "New Name"


def test_rename_lc_writes_audit_entry_with_diff(db_session: Session) -> None:
    lc = make_lc(db_session, name="Before")
    rename_lc(db_session, lc_id=lc.id, new_name="After")
    entry = db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "lc.rename",
            AuditLog.resource_id == lc.id,
        )
    ).scalar_one()
    assert entry.diff == {"before": {"name": "Before"}, "after": {"name": "After"}}


def test_rename_lc_raises_for_unknown_id(db_session: Session) -> None:
    import pytest
    with pytest.raises(ValueError, match="LC 999999 not found"):
        rename_lc(db_session, lc_id=999999, new_name="Anything")


def test_set_lc_state_updates_state(db_session: Session) -> None:
    lc = make_lc(db_session)
    set_lc_state(db_session, lc_id=lc.id, state="VIC")
    assert lc.state == "VIC"


def test_set_lc_state_writes_audit_entry(db_session: Session) -> None:
    lc = make_lc(db_session)
    set_lc_state(db_session, lc_id=lc.id, state="QLD")
    entry = db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "lc.set_state",
            AuditLog.resource_id == lc.id,
        )
    ).scalar_one()
    assert entry.diff == {"before": {"state": None}, "after": {"state": "QLD"}}


def test_set_lc_state_raises_for_unknown_id(db_session: Session) -> None:
    import pytest
    with pytest.raises(ValueError, match="LC 999999 not found"):
        set_lc_state(db_session, lc_id=999999, state="NSW")


def test_deactivate_lc_sets_active_false(db_session: Session) -> None:
    lc = make_lc(db_session, name="To Deactivate")
    deactivate_lc(db_session, lc_id=lc.id)
    assert lc.active is False


def test_deactivate_lc_writes_audit_entry(db_session: Session) -> None:
    lc = make_lc(db_session, name="Audit Deactivate")
    deactivate_lc(db_session, lc_id=lc.id)
    entry = db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "lc.deactivate",
            AuditLog.resource_id == lc.id,
        )
    ).scalar_one()
    assert entry is not None


def test_deactivate_lc_does_not_delete_historical_memberships(db_session: Session) -> None:
    lc = make_lc(db_session, name="Historical LC")
    position = make_position(db_session)
    term = make_term(db_session)
    person = make_person(db_session)
    membership = make_membership(db_session, person=person, lc=lc, position=position, term=term)

    deactivate_lc(db_session, lc_id=lc.id)

    # Membership still exists and still points at the now-inactive LC
    still_there = db_session.get(Membership, membership.id)
    assert still_there is not None
    assert still_there.lc_id == lc.id


def test_deactivate_lc_raises_for_unknown_id(db_session: Session) -> None:
    import pytest
    with pytest.raises(ValueError, match="LC 999999 not found"):
        deactivate_lc(db_session, lc_id=999999)
