from sqlalchemy.orm import Session

from app.repositories.lc import LC_DEFAULT_TIMEZONE, get_lc, list_lcs, resolve_timezone
from tests.helpers import make_lc, make_state_timezone


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
