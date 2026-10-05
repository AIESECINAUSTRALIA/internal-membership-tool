"""Dependencies for API request handling.

Spec §9 and Ticket 7: Auth resolution.
Currently provides a test-double / header-based dependency (`X-Actor-Email`)
so Ticket DEV-0042 can be fully tested without waiting for real Google OAuth.
Ticket 7 will replace header extraction with JWT verification.
"""

from collections.abc import Generator, Sequence
from dataclasses import dataclass
from datetime import date

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.membership import Membership
from app.models.person import Person
from app.repositories.membership import get_active_memberships_for_person


def get_db() -> Generator[Session, None, None]:
    """Database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@dataclass(frozen=True)
class CurrentActor:
    person: Person
    active_memberships: Sequence[Membership]
    acting_membership: Membership | None


def get_current_actor(
    db: Session = Depends(get_db),
    x_actor_email: str | None = Header(default=None, alias="X-Actor-Email"),
) -> CurrentActor:
    """Resolve the authenticated actor from header (stub for Ticket 7 OAuth)."""
    if not x_actor_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing actor email header (X-Actor-Email)",
        )
    stmt = select(Person).where(Person.aiesec_email == x_actor_email.strip().lower())
    person = db.execute(stmt).scalar_one_or_none()

    if person is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No person found for email",
        )
    # access follows the dates
    active_memberships = get_active_memberships_for_person(db, person.id, as_of=date.today())
    # default acting membership is the highest-ranked one (or None if unallocated)
    acting = active_memberships[0] if active_memberships else None

    return CurrentActor(
        person=person,
        active_memberships=active_memberships,
        acting_membership=acting,
    )
