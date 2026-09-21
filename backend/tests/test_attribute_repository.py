from sqlalchemy import select
from sqlalchemy.orm import Session

import pytest

from app.models.attribute import (
    Attribute,
    AttributeAppliesTo,
    AttributeDataType,
    AttributeEntityType,
    AttributeValue,
)
from app.repositories.attribute import (
    AttributeValidationError,
    get_attribute_value,
    set_attribute_value,
)
from tests.helpers import (
    TODAY,
    YEAR_AGO,
    make_lc,
    make_membership,
    make_person,
    make_position,
    make_term,
)


def _make_person_and_recorder(session: Session) -> tuple:
    """A person plus a membership id to record attribute changes under."""
    lc = make_lc(session)
    position = make_position(session, key="test_lcvp", label="LC Vice President", rank=2)
    term = make_term(session)
    person = make_person(session)
    recorder = make_membership(session, person=person, lc=lc, position=position, term=term)
    return person, recorder.id


def test_set_and_get_person_attribute(db_session: Session) -> None:
    person, recorder_id = _make_person_and_recorder(db_session)
    attribute = Attribute(
        key="dietary_requirements",
        label="Dietary requirements",
        applies_to=AttributeAppliesTo.PERSON,
        data_type=AttributeDataType.TEXT,
        active=True,
    )
    db_session.add(attribute)
    db_session.flush()

    set_attribute_value(
        db_session,
        attribute=attribute,
        entity_type=AttributeEntityType.PERSON,
        entity_id=person.id,
        raw_value="Vegetarian",
        recorded_by_membership_id=recorder_id,
    )

    result = get_attribute_value(
        db_session,
        attribute=attribute,
        entity_type=AttributeEntityType.PERSON,
        entity_id=person.id,
    )
    assert result == "Vegetarian"


def test_setting_again_overwrites_rather_than_duplicates(db_session: Session) -> None:
    person, recorder_id = _make_person_and_recorder(db_session)
    attribute = Attribute(
        key="onboarding_complete",
        label="Onboarding complete",
        applies_to=AttributeAppliesTo.MEMBERSHIP,
        data_type=AttributeDataType.BOOLEAN,
        active=True,
    )
    db_session.add(attribute)
    db_session.flush()

    set_attribute_value(
        db_session,
        attribute=attribute,
        entity_type=AttributeEntityType.MEMBERSHIP,
        entity_id=recorder_id,
        raw_value=False,
        recorded_by_membership_id=recorder_id,
    )
    set_attribute_value(
        db_session,
        attribute=attribute,
        entity_type=AttributeEntityType.MEMBERSHIP,
        entity_id=recorder_id,
        raw_value=True,
        recorded_by_membership_id=recorder_id,
    )

    rows = (
        db_session.execute(
            select(AttributeValue).where(AttributeValue.attribute_id == attribute.id)
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].value_bool is True


def test_rejects_value_outside_enum_options(db_session: Session) -> None:
    person, recorder_id = _make_person_and_recorder(db_session)
    attribute = Attribute(
        key="shirt_size",
        label="Shirt size",
        applies_to=AttributeAppliesTo.PERSON,
        data_type=AttributeDataType.ENUM,
        enum_options=["S", "M", "L"],
        active=True,
    )
    db_session.add(attribute)
    db_session.flush()

    with pytest.raises(AttributeValidationError):
        set_attribute_value(
            db_session,
            attribute=attribute,
            entity_type=AttributeEntityType.PERSON,
            entity_id=person.id,
            raw_value="XXL",
            recorded_by_membership_id=recorder_id,
        )


def test_rejects_value_below_configured_minimum(db_session: Session) -> None:
    person, recorder_id = _make_person_and_recorder(db_session)
    attribute = Attribute(
        key="hours_committed",
        label="Hours committed per week",
        applies_to=AttributeAppliesTo.MEMBERSHIP,
        data_type=AttributeDataType.NUMBER,
        validation={"min": 0},
        active=True,
    )
    db_session.add(attribute)
    db_session.flush()

    with pytest.raises(AttributeValidationError):
        set_attribute_value(
            db_session,
            attribute=attribute,
            entity_type=AttributeEntityType.MEMBERSHIP,
            entity_id=recorder_id,
            raw_value=-5,
            recorded_by_membership_id=recorder_id,
        )


def test_rejects_missing_required_value(db_session: Session) -> None:
    person, recorder_id = _make_person_and_recorder(db_session)
    attribute = Attribute(
        key="join_reason",
        label="Reason for joining",
        applies_to=AttributeAppliesTo.PERSON,
        data_type=AttributeDataType.TEXT,
        validation={"required": True},
        active=True,
    )
    db_session.add(attribute)
    db_session.flush()

    with pytest.raises(AttributeValidationError):
        set_attribute_value(
            db_session,
            attribute=attribute,
            entity_type=AttributeEntityType.PERSON,
            entity_id=person.id,
            raw_value=None,
            recorded_by_membership_id=recorder_id,
        )