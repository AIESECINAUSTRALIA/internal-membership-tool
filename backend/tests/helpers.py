"""Shared test helper functions.

All lookup keys use a ``test_`` prefix so they never collide with seed data
in local environments (where ``make seed`` has already populated the DB).
"""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.attribute import Attribute, AttributeAppliesTo, AttributeDataType
from app.models.membership import Membership
from app.models.org import LC, Function, LCType, Position, Term
from app.models.person import Person

TODAY = date(2026, 6, 15)
YEAR_AGO = TODAY - timedelta(days=365)
YEAR_AHEAD = TODAY + timedelta(days=365)


def make_lc(session: Session, *, name: str = "AIESEC in Testville") -> LC:
    lc = LC(name=name, type=LCType.LC, active=True)
    session.add(lc)
    session.flush()
    return lc


def make_position(
    session: Session,
    *,
    key: str = "test_member",
    label: str = "Test Member",
    rank: int = 4,
) -> Position:
    position = Position(key=key, label=label, rank=rank, active=True)
    session.add(position)
    session.flush()
    return position


def make_function(
    session: Session,
    *,
    key: str = "test_bd",
    label: str = "Test BD",
) -> Function:
    function = Function(key=key, label=label, active=True)
    session.add(function)
    session.flush()
    return function


def make_term(
    session: Session,
    *,
    name: str = "Test Term",
    start: date = YEAR_AGO,
    end: date = YEAR_AHEAD,
) -> Term:
    term = Term(name=name, start_date=start, end_date=end)
    session.add(term)
    session.flush()
    return term


def make_person(
    session: Session,
    *,
    full_name: str = "Ada Lovelace",
    email: str = "ada@aiesec.net",
) -> Person:
    person = Person(full_name=full_name, aiesec_email=email, join_date=YEAR_AGO)
    session.add(person)
    session.flush()
    return person


def make_membership(
    session: Session,
    *,
    person: Person,
    lc: LC,
    position: Position,
    term: Term,
    function: Function | None = None,
    start: date = YEAR_AGO,
    end: date | None = None,
) -> Membership:
    membership = Membership(
        person_id=person.id,
        lc_id=lc.id,
        position_id=position.id,
        function_id=function.id if function else None,
        term_id=term.id,
        start_date=start,
        end_date=end,
    )
    session.add(membership)
    session.flush()
    return membership


def make_person_and_recorder(session: Session) -> tuple:
    """A person plus a membership id to use as recorded_by in attribute tests."""
    lc = make_lc(session)
    position = make_position(session, key="test_lcvp", label="LC Vice President", rank=2)
    term = make_term(session)
    person = make_person(session)
    recorder = make_membership(session, person=person, lc=lc, position=position, term=term)
    return person, recorder.id


def make_attribute(
    session: Session,
    *,
    key: str = "test_attr",
    label: str = "Test Attribute",
    applies_to: AttributeAppliesTo = AttributeAppliesTo.PERSON,
    data_type: AttributeDataType = AttributeDataType.TEXT,
    enum_options: list[str] | None = None,
    validation: dict[str, object] | None = None,
) -> Attribute:
    attribute = Attribute(
        key=key,
        label=label,
        applies_to=applies_to,
        data_type=data_type,
        enum_options=enum_options,
        validation=validation,
        active=True,
    )
    session.add(attribute)
    session.flush()
    return attribute


def make_kpi_attribute(
    session: Session,
    *,
    key: str = "ol_signups",
    minimum: float = 0,
) -> Attribute:
    attribute = Attribute(
        key=key,
        label="OL Signups",
        applies_to=AttributeAppliesTo.KPI,
        data_type=AttributeDataType.NUMBER,
        unit="count",
        validation={"required": True, "min": minimum},
        active=True,
    )
    session.add(attribute)
    session.flush()
    return attribute
