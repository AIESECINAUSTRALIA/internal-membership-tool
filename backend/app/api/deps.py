"""FastAPI dependencies shared by the routes.

A route asks for what it needs as a typed parameter, e.g. `person: CurrentPerson`,
and FastAPI runs the matching function first. Tests swap any of them out with
`app.dependency_overrides`.
"""

from collections.abc import Generator, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser
from app.core.sessions import get_valid_session
from app.db.session import SessionLocal
from app.models.membership import Membership
from app.models.person import Person, PersonStatus
from app.repositories.membership import (
    build_membership_context,
    get_active_memberships_for_person,
)


def get_db() -> Generator[Session, None, None]:
    """One database session per request, always closed afterwards."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, db: DbSession) -> AuthenticatedUser:
    """The caller, from their `__session` cookie. 401 without a valid session.

    The cookie holds a random token; we look up its hash in `user_session` (see
    `app/core/sessions.py`). The allowed-email-domain check is NOT repeated here: it
    runs once, at sign-in. A session therefore outlives a change to
    ALLOWED_EMAIL_DOMAINS by at most SESSION_TTL_HOURS (docs/auth.md).
    """
    token = request.cookies.get("__session")
    if not token:
        raise HTTPException(status_code=401, detail="Not signed in")

    session = get_valid_session(db, token)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    person = db.get(Person, session.person_id)
    if person is None or person.status == PersonStatus.ANONYMISED:
        raise HTTPException(status_code=401, detail="Account is unavailable")

    if not person.expa_id:
        raise HTTPException(status_code=401, detail="EXPA identity is not linked")

    return AuthenticatedUser(
        subject=person.expa_id,
        email=person.aiesec_email.lower(),
    )


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


def get_current_person(user: CurrentUser, db: DbSession) -> Person | None:
    """The signed-in `person`, matched by their linked EXPA id (spec §9).

    An ANONYMISED person never counts as a match: after a deletion request their
    record must never sign anyone in again (spec §8).
    """
    return (
        db.execute(
            select(Person).where(
                Person.expa_id == user.subject,
                Person.status != PersonStatus.ANONYMISED,
            )
        )
        .scalars()
        .first()
    )


CurrentPerson = Annotated[Person | None, Depends(get_current_person)]


def get_today() -> date:
    """Today's date, as a dependency so tests can fix the date
    (`app.dependency_overrides[get_today] = lambda: date(...)`)."""
    return date.today()


@dataclass(frozen=True)
class CurrentActor:
    """The signed-in person and their active memberships, for feature endpoints."""

    person: Person
    active_memberships: Sequence[Membership]
    acting_membership: Membership | None


def get_current_actor(person: CurrentPerson, db: DbSession) -> CurrentActor:
    """Resolve the authenticated actor and their active memberships.

    Authentication is handled by CurrentPerson, which depends on the session from
    CurrentUser. The acting membership is the one with the highest-ranked position.
    """
    if person is None:
        raise HTTPException(
            status_code=401,
            detail="No person found for this account",
        )

    active_memberships = get_active_memberships_for_person(
        db,
        person.id,
        as_of=date.today(),
    )

    acting = max(
        active_memberships,
        key=lambda m: build_membership_context(db, m).position_rank,
        default=None,
    )

    return CurrentActor(
        person=person,
        active_memberships=active_memberships,
        acting_membership=acting,
    )


CurrentActorDep = Annotated[CurrentActor, Depends(get_current_actor)]
