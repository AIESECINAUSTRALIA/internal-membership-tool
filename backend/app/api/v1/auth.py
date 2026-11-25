"""Sign-in with EXPA, sign-out, and `GET /me` (spec §9). Read `docs/auth.md` first.

- `GET  /auth/login`    start sign-in: redirect to EXPA
- `GET  /auth/callback` EXPA redirects back here; we create the session
- `POST /auth/logout`   end the session
- `GET  /me`            who is signed in, their active memberships and permissions

Login and callback are pages the *browser* visits (redirects), not API calls the
frontend makes, so they answer with redirects rather than JSON errors.
"""

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentPerson, CurrentUser, DbSession
from app.config import get_settings
from app.core.audit import record_audit
from app.core.auth import AuthError, ExpaIdentity, ExpaOAuthClient, is_allowed_email
from app.core.resolved_permissions import resolve_permissions
from app.core.sessions import (
    activate_session,
    consume_pending_session,
    create_pending_session,
    delete_pending_session,
    get_valid_session,
    revoke_session,
)
from app.models.membership import Membership, Team
from app.models.org import LC, Function, Position
from app.models.person import SIGN_IN_BLOCKED, Person, PersonStatus
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

# Where a failed sign-in sends the browser. The callback is a page the browser
# visits, not an API call, so it must always end on a frontend page rather than a
# JSON error. `SignInPage` shows a message for each `?error=` reason.
#
# Not-allocated people also land on the sign-in page (with the spec §2A.3 message),
# not on `/not-allocated`: that page's route guard needs a signed-in user, and we
# deliberately give no session to someone with no active membership.
SIGN_IN_PATH = "/sign-in"


class SignInError:
    """The `?error=` values the frontend understands. Keep in sync with
    `frontend/src/pages/SignInPage.tsx`."""

    DENIED = "denied"  # the user cancelled on EXPA's page
    EXPIRED = "expired"  # missing or stale state/cookie: start again
    EXPA = "expa"  # EXPA could not be reached or answered badly
    DOMAIN = "domain"  # the EXPA account's email is not an allowed AIESEC domain
    NOT_ALLOCATED = "not_allocated"  # no person row, or no active membership


def _set_session_cookie(response: Response, name: str, token: str, max_age: int) -> None:
    """httpOnly so page scripts can never read the token; SameSite=Lax so other sites'
    POSTs don't carry it (the Origin check in app/main.py is the second layer)."""
    response.set_cookie(
        key=name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=get_settings().uses_https,
        samesite="lax",
        path="/",
    )


def _frontend_url(path: str) -> str:
    return f"{get_settings().frontend_origin.rstrip('/')}{path}"


# Audit summaries for refused sign-ins, by reason. No personal data (spec §8.4).
REFUSED_SIGN_IN_SUMMARIES = {
    SignInError.DOMAIN: "Sign-in refused: EXPA account outside the allowed email domains",
    SignInError.NOT_ALLOCATED: "Sign-in refused: no active membership (not allocated)",
}


def _fail_sign_in(
    db: Session,
    pending_token: str | None,
    reason: str,
    *,
    audit: bool = False,
    person_id: int | None = None,
) -> RedirectResponse:
    """End a failed sign-in: undo any half-done work, delete the pending session and
    its cookie, and send the browser to a frontend page that explains what happened.

    `audit=True` also writes an `auth.sign_in` entry with `allocated: false` (spec
    open question 17). Only refusals *after EXPA confirmed who the person is* are
    audited (`domain`, `not_allocated`): each one needs a real EXPA account to go
    through a full sign-in. The other failures (cancelled, expired state, EXPA
    errors) can be triggered by anyone, in a loop, without an account. Auditing
    them would let a script fill the permanent, append-only audit log.

    The entry never holds the email: only the person id when there is a person row,
    and the reason.
    """
    db.rollback()
    if pending_token:
        delete_pending_session(db, pending_token)

    if audit:
        record_audit(
            db,
            action="auth.sign_in",
            resource_type="person",
            resource_id=person_id,
            actor_person_id=person_id,
            summary=REFUSED_SIGN_IN_SUMMARIES[reason],
            diff={"allocated": False, "reason": reason},
        )

    db.commit()

    url = f"{_frontend_url(SIGN_IN_PATH)}?{urlencode({'error': reason})}"
    response = RedirectResponse(url, status_code=302)
    response.delete_cookie(PENDING_COOKIE_NAME, path="/")
    return response


@router.get("/auth/login")
def login(db: DbSession) -> RedirectResponse:
    """Start sign-in: remember this browser, then send it to EXPA."""
    settings = get_settings()
    oauth = ExpaOAuthClient(settings)

    # Check the configuration before writing anything to the database.
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


def _find_person(db: Session, identity: ExpaIdentity) -> Person | None:
    """The `person` this EXPA account belongs to, or None.

    1. By EXPA person id: stable, survives an email change. Set on first sign-in.
    2. Otherwise by AIESEC email, but only for people not yet linked to an EXPA
       account, so one EXPA account can never take over another person's row.
       Emails are compared lower-cased; if two rows ever differ only in case,
       the oldest wins instead of crashing.
    """
    person = db.execute(
        select(Person).where(Person.expa_id == identity.expa_id)
    ).scalar_one_or_none()
    if person is not None:
        return person

    return (
        db.execute(
            select(Person)
            .where(
                func.lower(Person.aiesec_email) == identity.aiesec_email,
                Person.status != PersonStatus.ANONYMISED,
                Person.expa_id.is_(None),
            )
            .order_by(Person.id)
            .limit(1)
        )
        .scalars()
        .first()
    )


@router.get("/auth/callback")
def callback(
    request: Request,
    db: DbSession,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """EXPA sends the browser back here. On success: a session cookie and a redirect
    to the app. On any failure: a redirect to a frontend page explaining it.

    A plain `def` (not `async`): FastAPI runs it in a worker thread, so the blocking
    database and EXPA calls below don't stall other requests.
    """
    settings = get_settings()
    pending_token = request.cookies.get(PENDING_COOKIE_NAME)

    if error:
        return _fail_sign_in(db, pending_token, SignInError.DENIED)

    if not state or not code or not pending_token:
        return _fail_sign_in(db, pending_token, SignInError.EXPIRED)

    pending = consume_pending_session(db, token=pending_token, state=state)
    if pending is None:
        return _fail_sign_in(db, pending_token, SignInError.EXPIRED)

    oauth = ExpaOAuthClient(settings)
    try:
        access_token = oauth.exchange_code(code)
        identity = oauth.get_current_person(access_token)
    except AuthError:
        return _fail_sign_in(db, pending_token, SignInError.EXPA)

    # The EXPA access token is not persisted or sent to the browser.
    if not is_allowed_email(identity.aiesec_email, settings.allowed_email_domain_set):
        return _fail_sign_in(db, pending_token, SignInError.DOMAIN, audit=True)

    person = _find_person(db, identity)
    if person is None or person.status in SIGN_IN_BLOCKED:
        # No person id in the audit entry: there is no row, or it was anonymised or
        # deactivated and must not gain new activity linked to it.
        return _fail_sign_in(db, pending_token, SignInError.NOT_ALLOCATED, audit=True)

    # Only ACTIVE memberships let someone in (spec §3.2): an ended term means
    # "not allocated", not "signed in with no permissions".
    if not get_active_memberships_for_person(db, person.id):
        person_id = person.id  # read before the rollback in _fail_sign_in expires it
        return _fail_sign_in(
            db, pending_token, SignInError.NOT_ALLOCATED, audit=True, person_id=person_id
        )

    try:
        # Link the EXPA account on first sign-in, so later sign-ins match by id.
        if person.expa_id is None:
            person.expa_id = identity.expa_id

        token = activate_session(
            db,
            session=pending,
            person_id=person.id,
            ttl_hours=settings.session_ttl_hours,
        )

        # No email in the audit entry: audit rows are permanent (spec §8.4).
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

    response = RedirectResponse(_frontend_url("/"), status_code=302)
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
