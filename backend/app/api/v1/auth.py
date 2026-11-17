"""EXPA OAuth authentication and the current user's memberships."""

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentPerson, CurrentUser, DbSession
from app.config import get_settings
from app.core.audit import record_audit
from app.core.auth import AuthError, ExpaOAuthClient, is_allowed_email
from app.core.resolved_permissions import resolve_permissions
from app.core.sessions import (
    activate_session,
    consume_pending_session,
    create_pending_session,
    get_valid_session,
    revoke_session,
)
from app.models.membership import Membership, Team
from app.models.org import LC, Function, Position
from app.models.person import Person, PersonStatus
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

COOKIE_NAME = "__session"
PENDING_COOKIE_NAME = "__oauth_pending"


def _set_session_cookie(response: Response, name: str, token: str, max_age: int) -> None:
    response.set_cookie(
        key=name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


@router.get("/auth/login")
def login(db: DbSession) -> RedirectResponse:
    settings = get_settings()
    oauth = ExpaOAuthClient(settings)

    # Validate provider configuration before creating a pending session.
    if not settings.expa_client_id or not settings.expa_client_secret:
        raise HTTPException(status_code=503, detail="EXPA authentication is not configured")

    _, pending_token, state = create_pending_session(db, ttl_hours=1)

    response = RedirectResponse(oauth.authorization_url(state), status_code=302)
    _set_session_cookie(
        response,
        PENDING_COOKIE_NAME,
        pending_token,
        3600,
    )
    return response


@router.get("/auth/callback")
async def callback(
    request: Request,
    db: DbSession,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    settings = get_settings()
    pending_token = request.cookies.get(PENDING_COOKIE_NAME)

    if error:
        raise HTTPException(status_code=401, detail="EXPA authentication was denied")

    if not state or not code or not pending_token:
        raise HTTPException(status_code=401, detail="Missing OAuth callback parameters")

    pending = consume_pending_session(db, token=pending_token, state=state)
    if pending is None:
        raise HTTPException(status_code=401, detail="Invalid or expired OAuth state")

    oauth = ExpaOAuthClient(settings)
    try:
        access_token = await oauth.exchange_code(code)
        identity = await oauth.get_current_person(access_token)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    # The EXPA access token is not persisted or sent to the browser.
    if not is_allowed_email(identity.aiesec_email, settings.allowed_email_domain_set):
        raise HTTPException(status_code=403, detail="Only AIESEC accounts can sign in")

    try:
        # Match the stable EXPA ID first.
        person = db.execute(
            select(Person).where(Person.expa_id == identity.expa_id)
        ).scalar_one_or_none()

        # Only unlinked local accounts may be matched by email.
        if person is None:
            person = db.execute(
                select(Person).where(
                    func.lower(Person.aiesec_email) == identity.aiesec_email,
                    Person.status != PersonStatus.ANONYMISED,
                    Person.expa_id.is_(None),
                )
            ).scalar_one_or_none()

        if person is None or person.status == PersonStatus.ANONYMISED:
            raise HTTPException(
                status_code=403,
                detail="Account is not allocated",
            )

        memberships = get_active_memberships_for_person(db, person.id)
        if not memberships:
            raise HTTPException(
                status_code=403,
                detail="Account is not allocated",
            )

        # Only persist the identity link for allocated accounts.
        if person.expa_id is None:
            person.expa_id = identity.expa_id

        token = activate_session(
            db,
            session=pending,
            person_id=person.id,
            ttl_hours=settings.session_ttl_hours,
        )

        record_audit(
            db,
            action="auth.sign_in",
            resource_type="person",
            resource_id=person.id,
            actor_person_id=person.id,
            summary="Signed in to the main app",
            diff={"allocated": True},
        )

        # Identity link, session activation and audit commit together.
        db.commit()

    except Exception:
        db.rollback()
        raise

    response = RedirectResponse(settings.app_base_url, status_code=302)
    response.delete_cookie(PENDING_COOKIE_NAME, path="/")
    _set_session_cookie(response, COOKIE_NAME, token, settings.session_ttl_hours * 3600)
    return response


@router.post("/auth/logout", status_code=204)
def logout(request: Request, db: DbSession) -> Response:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        session = get_valid_session(db, token)
        if session is not None:
            revoke_session(db, session)

    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/")
    response.delete_cookie(PENDING_COOKIE_NAME, path="/")
    return response


@router.get("/me", response_model=MeResponse)
def read_me(user: CurrentUser, person: CurrentPerson, db: DbSession) -> MeResponse:
    memberships = get_active_memberships_for_person(db, person.id) if person else []

    if person is None:
        return MeResponse(email=user.email, person=None, memberships=[], permissions=[])

    teams = get_current_teams_for_memberships(db, [m.id for m in memberships])
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
        lc=LcOut(
            id=lc.id,
            name=lc.name,
            type=lc.type.value,
            state=lc.state,
            active=lc.active,
        ),
        team=TeamOut(id=team.id, name=team.name) if team else None,
        start_date=membership.start_date,
        end_date=membership.end_date,
    )
