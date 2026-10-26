"""FastAPI dependencies shared by the routes.

A route asks for what it needs as a typed parameter, e.g. `person: CurrentPerson`,
and FastAPI runs the matching function first. Tests swap any of them out with
`app.dependency_overrides`.
"""

from collections.abc import Generator, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.auth import AuthenticatedUser, AuthError, TokenVerifier, build_token_verifier
from app.db.session import SessionLocal
from app.models.membership import Membership
from app.models.person import Person, PersonStatus
from app.repositories.membership import get_active_memberships_for_person

# `auto_error=False` so a missing header reaches our code and gets the same 401 as a
# bad token, rather than FastAPI's default 403.
_bearer = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    """One database session per request, always closed afterwards."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_token_verifier(settings: Annotated[Settings, Depends(get_settings)]) -> TokenVerifier:
    try:
        return build_token_verifier(settings)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> AuthenticatedUser:
    """The caller, from their Supabase access token. 401 without a valid one."""
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Not signed in",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return verifier.verify(credentials.credentials)
    except AuthError as exc:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail, headers=headers
        ) from exc


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


def get_current_person(user: CurrentUser, db: DbSession) -> Person | None:
    """The `person` whose `aiesec_email` matches the signed-in email (spec §9).

    None when nobody matches. An ANONYMISED person also counts as no match: after a
    deletion request their record must never sign anyone in again (spec §8).
    """
    stmt = select(Person).where(
        func.lower(Person.aiesec_email) == user.email,
        Person.status != PersonStatus.ANONYMISED,
    )
    return db.execute(stmt).scalars().first()


CurrentPerson = Annotated[Person | None, Depends(get_current_person)]


@dataclass(frozen=True)
class CurrentActor:
    """The signed-in person and their active memberships, for feature endpoints."""

    person: Person
    active_memberships: Sequence[Membership]
    acting_membership: Membership | None


def get_current_actor(person: CurrentPerson, db: DbSession) -> CurrentActor:
    """The signed-in person, for endpoints that act on data (e.g. `api/v1/members.py`).

    Same token check as `/me`. Unlike `/me` (which reports "not allocated" to the
    frontend), a caller with no matching `person` gets 401 here.
    """
    if person is None:
        raise HTTPException(status_code=401, detail="No person found for this account")
    # Access follows the dates (spec §4.1).
    active_memberships = get_active_memberships_for_person(db, person.id, as_of=date.today())
    acting = active_memberships[0] if active_memberships else None
    return CurrentActor(
        person=person,
        active_memberships=active_memberships,
        acting_membership=acting,
    )


CurrentActorDep = Annotated[CurrentActor, Depends(get_current_actor)]
