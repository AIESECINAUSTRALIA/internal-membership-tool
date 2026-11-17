"""FastAPI dependencies shared by the routes."""

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
    """One database session per request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, db: DbSession) -> AuthenticatedUser:
    """Authenticate the request using its server-side session cookie."""
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
    """Resolve the local person using the linked EXPA identity."""
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
    return date.today()


@dataclass(frozen=True)
class CurrentActor:
    """The authenticated person and their active memberships."""

    person: Person
    active_memberships: Sequence[Membership]
    acting_membership: Membership | None


def get_current_actor(person: CurrentPerson, db: DbSession) -> CurrentActor:
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
