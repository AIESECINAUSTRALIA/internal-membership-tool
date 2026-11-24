"""Tests for the positions & functions repository and the rules the database enforces
on those two lookup tables (spec §1.5, §2A.2)."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.org import Position
from app.models.privacy import AuditLog
from app.repositories.positions_functions import (
    create_position,
    rename_position,
    set_position_details,
)
from tests.helpers import make_function, make_position

# ---------------------------------------------------------------------------
# Names are unique, ignoring upper/lower case (unique index on lower(label))
# ---------------------------------------------------------------------------


def test_position_labels_are_unique_ignoring_case(db_session: Session) -> None:
    make_position(db_session, key="test_a", label="Test Role")

    with pytest.raises(IntegrityError):
        make_position(db_session, key="test_b", label="test role")


def test_function_labels_are_unique_ignoring_case(db_session: Session) -> None:
    make_function(db_session, key="test_a", label="Test Function")

    with pytest.raises(IntegrityError):
        make_function(db_session, key="test_b", label="TEST FUNCTION")


# ---------------------------------------------------------------------------
# A change that changes nothing writes no audit row
# ---------------------------------------------------------------------------


def _audit_count(session: Session, position_id: int) -> int:
    return len(
        session.execute(
            select(AuditLog).where(
                AuditLog.resource_type == "position", AuditLog.resource_id == position_id
            )
        )
        .scalars()
        .all()
    )


def test_renaming_to_the_same_label_is_not_audited(db_session: Session) -> None:
    position = make_position(db_session, key="test_same", label="Test Same", rank=2)

    rename_position(
        db_session, position_id=position.id, new_label="Test Same", actor_membership_id=None
    )

    assert _audit_count(db_session, position.id) == 0


def test_setting_details_to_current_values_is_not_audited(db_session: Session) -> None:
    position = make_position(db_session, key="test_same", label="Test Same", rank=2)

    set_position_details(
        db_session,
        position_id=position.id,
        level=None,
        rank=2,
        can_add_same_rank=False,
        actor_membership_id=None,
    )

    assert _audit_count(db_session, position.id) == 0


# ---------------------------------------------------------------------------
# A new position never takes a key that the permission code gives grants to
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "reserved_key"), [("Admin", "admin"), ("MCVP", "mcvp")])
def test_new_position_never_takes_a_key_that_carries_permissions(
    db_session: Session, label: str, reserved_key: str
) -> None:
    # Grants are tied to keys in code (BASELINE_PERMISSION_MATRIX). If no row holds
    # `admin` yet, a position named "Admin" must still not get that key, or it would
    # instantly inherit every admin grant.
    existing = db_session.execute(
        select(Position).where(Position.key == reserved_key)
    ).scalar_one_or_none()
    if existing is not None:
        existing.label = f"Test old {reserved_key}"  # free up the name only
        db_session.flush()

    position = create_position(
        db_session,
        label=label,
        level="mc",
        rank=1,
        can_add_same_rank=False,
        actor_membership_id=None,
    )

    assert position.key == f"{reserved_key}_2"
