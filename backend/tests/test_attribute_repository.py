import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.attribute import (
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
    make_attribute,
    make_kpi_attribute,
    make_person_and_recorder,
)


def test_set_and_get_person_attribute(db_session: Session) -> None:
    person, recorder_id = make_person_and_recorder(db_session)
    attribute = make_attribute(
        db_session,
        key="test_dietary_requirements",
        label="Dietary requirements",
    )

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
    person, recorder_id = make_person_and_recorder(db_session)
    attribute = make_attribute(
        db_session,
        key="test_onboarding_complete",
        label="Onboarding complete",
        applies_to=AttributeAppliesTo.MEMBERSHIP,
        data_type=AttributeDataType.BOOLEAN,
    )

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
    person, recorder_id = make_person_and_recorder(db_session)
    attribute = make_attribute(
        db_session,
        key="test_shirt_size",
        label="Shirt size",
        data_type=AttributeDataType.ENUM,
        enum_options=["S", "M", "L"],
    )

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
    person, recorder_id = make_person_and_recorder(db_session)
    attribute = make_attribute(
        db_session,
        key="test_hours_committed",
        label="Hours committed per week",
        applies_to=AttributeAppliesTo.MEMBERSHIP,
        data_type=AttributeDataType.NUMBER,
        validation={"min": 0},
    )

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
    person, recorder_id = make_person_and_recorder(db_session)
    attribute = make_attribute(
        db_session,
        key="test_join_reason",
        label="Reason for joining",
        validation={"required": True},
    )

    with pytest.raises(AttributeValidationError):
        set_attribute_value(
            db_session,
            attribute=attribute,
            entity_type=AttributeEntityType.PERSON,
            entity_id=person.id,
            raw_value=None,
            recorded_by_membership_id=recorder_id,
        )


def test_rejects_entity_type_not_matching_applies_to(db_session: Session) -> None:
    person, recorder_id = make_person_and_recorder(db_session)
    attribute = make_attribute(
        db_session,
        key="test_dietary_requirements",
        label="Dietary requirements",
        applies_to=AttributeAppliesTo.PERSON,
    )

    # A PERSON attribute written against a membership id would silently attach
    # the value to the wrong row, since entity_id means something different per
    # entity_type.
    with pytest.raises(AttributeValidationError):
        set_attribute_value(
            db_session,
            attribute=attribute,
            entity_type=AttributeEntityType.MEMBERSHIP,
            entity_id=recorder_id,
            raw_value="Vegetarian",
            recorded_by_membership_id=recorder_id,
        )

    rows = (
        db_session.execute(
            select(AttributeValue).where(AttributeValue.attribute_id == attribute.id)
        )
        .scalars()
        .all()
    )
    assert rows == []


@pytest.mark.parametrize("entity_type", list(AttributeEntityType))
def test_rejects_kpi_attribute(db_session: Session, entity_type: AttributeEntityType) -> None:
    person, recorder_id = make_person_and_recorder(db_session)
    # KPI values belong in kpi_record, never attribute_value — so a KPI
    # attribute must be rejected whichever entity_type is passed.
    attribute = make_kpi_attribute(db_session, key="test_ol_signups")
    entity_id = person.id if entity_type == AttributeEntityType.PERSON else recorder_id

    with pytest.raises(AttributeValidationError):
        set_attribute_value(
            db_session,
            attribute=attribute,
            entity_type=entity_type,
            entity_id=entity_id,
            raw_value=10,
            recorded_by_membership_id=recorder_id,
        )

    rows = (
        db_session.execute(
            select(AttributeValue).where(AttributeValue.attribute_id == attribute.id)
        )
        .scalars()
        .all()
    )
    assert rows == []
