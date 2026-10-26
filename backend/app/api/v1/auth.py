"""`GET /api/v1/me`: who is signed in, and their active memberships (spec §9).

Sign-in itself happens between the browser, Google and Supabase — this API never
sees a password or a Google token. See `docs/auth.md`.
"""

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentPerson, CurrentUser, DbSession
from app.core.audit import record_audit
from app.core.auth import AuthenticatedUser
from app.core.resolved_permissions import resolve_permissions
from app.models.membership import Membership, Team
from app.models.org import LC, Function, Position
from app.models.person import Person
from app.models.privacy import AuditLog
from app.repositories.membership import get_active_memberships_for_person
from app.repositories.team import get_current_teams_for_memberships
from app.schemas.me import (
    LcOut,
    LookupOut,
    MembershipOut,
    MeResponse,
    PermissionOut,
    PersonOut,
    TeamOut,
)

router = APIRouter(tags=["auth"])


@router.get("/me", response_model=MeResponse)
def read_me(user: CurrentUser, person: CurrentPerson, db: DbSession) -> MeResponse:
    memberships = get_active_memberships_for_person(db, person.id) if person else []
    _record_sign_in_once(db, user, person, allocated=bool(memberships))

    if person is None:
        return MeResponse(email=user.email, person=None, memberships=[], permissions=[])

    teams = get_current_teams_for_memberships(db, [m.id for m in memberships])
    # Only ACTIVE memberships grant anything (spec §3.2): ended or future ones are
    # never passed in, so a person whose term ended gets no permissions.
    positions = [db.get(Position, m.position_id) for m in memberships]
    permissions = resolve_permissions(p.key for p in positions if p is not None)

    return MeResponse(
        email=user.email,
        person=PersonOut(
            id=person.id,
            full_name=person.full_name,
            preferred_name=person.preferred_name,
            aiesec_email=person.aiesec_email,
        ),
        memberships=[_membership_out(db, m, teams) for m in memberships],
        permissions=[
            PermissionOut(resource=p.resource, action=p.action, scope=p.scope) for p in permissions
        ],
    )


SIGN_IN_ACTION = "auth.sign_in"


def _record_sign_in_once(
    db: Session, user: AuthenticatedUser, person: Person | None, *, allocated: bool
) -> None:
    """Write one `auth.sign_in` audit entry per Supabase session (spec §9, §8.4).

    The frontend calls `/me` on every page load, but a reload is not a new sign-in.
    Supabase gives each sign-in its own `session_id` (kept across token refreshes),
    so an entry is written only the first time a session is seen.

    Audit entries are permanent, so nothing personal goes in: the person is referred
    to by id, and an email that matches nobody is logged without the email.
    """
    if user.session_id is not None:
        already_logged = db.execute(
            select(AuditLog.id)
            .where(
                AuditLog.action == SIGN_IN_ACTION,
                AuditLog.diff["session_id"].astext == user.session_id,
            )
            .limit(1)
        ).first()
        if already_logged:
            return

    if person is None:
        summary = "Signed in to the main app; the email matches no person (not allocated)"
    elif not allocated:
        summary = "Signed in to the main app; no active membership (not allocated)"
    else:
        summary = "Signed in to the main app"

    record_audit(
        db,
        action=SIGN_IN_ACTION,
        resource_type="person",
        resource_id=person.id if person else None,
        actor_person_id=person.id if person else None,
        summary=summary,
        diff={"session_id": user.session_id, "allocated": allocated},
    )
    # `/me` is otherwise read-only, so this is the only thing to commit. Two
    # simultaneous first requests could both write an entry; a duplicate sign-in
    # line is harmless, and rare enough not to need a lock.
    db.commit()


def _membership_out(db: Session, membership: Membership, teams: dict[int, Team]) -> MembershipOut:
    # `db.get` reads from the session's identity map after the first lookup, so the
    # same LC / position / function is only queried once per request.
    position = db.get(Position, membership.position_id)
    lc = db.get(LC, membership.lc_id)
    function = db.get(Function, membership.function_id) if membership.function_id else None
    assert position is not None and lc is not None  # guaranteed by the foreign keys
    team = teams.get(membership.id)

    return MembershipOut(
        id=membership.id,
        position=LookupOut(key=position.key, label=position.label),
        function=LookupOut(key=function.key, label=function.label) if function else None,
        lc=LcOut(id=lc.id, name=lc.name, type=lc.type.value),
        team=TeamOut(id=team.id, name=team.name) if team else None,
        start_date=membership.start_date,
        end_date=membership.end_date,
    )
