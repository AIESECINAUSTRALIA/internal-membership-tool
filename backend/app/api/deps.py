"""Dependencies for API request handling.

Spec §9 and Ticket 7: Auth resolution.

`get_current_actor` is the seam ticket 7 (real Google sign-in) fills in; it must
keep returning `CurrentActor`. Until then it is a dev-only stub: it trusts the
`X-Actor-Email` header **only** when `DEV_ACTOR_HEADER_ENABLED=true`, and
otherwise answers 401, so a deployed environment can never be impersonated by
header. Tests do not use the header at all: they replace this dependency with
`app.dependency_overrides[get_current_actor]`.
"""

import os
from collections.abc import Generator, Sequence
from dataclasses import dataclass
from datetime import date

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.membership import Membership
from app.models.person import Person
from app.repositories.membership import (
    build_membership_context,
    get_active_memberships_for_person,
)


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
    """Resolve the authenticated actor from header (dev-only stub for Ticket 7 OAuth)."""
    if os.environ.get("DEV_ACTOR_HEADER_ENABLED") != "true":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign-in is not available yet",
        )
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
