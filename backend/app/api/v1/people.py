"""People on the Admin console (spec §1.5, §2A.2, DEV-47): add, edit, deactivate.

Every endpoint needs `manage` on `person` from the permission matrix, checked by
`require_person_manager`. There is no delete endpoint: a person is removed by
deactivating them, which keeps their history (§1.5). A person's memberships are listed
and assigned here too (`/people/{id}/memberships`); those need `manage` on
`membership` instead. Changing an existing membership is in `api/v1/memberships.py`.

Errors: 403 without the grant, or when the hierarchy rule refuses (you can't change
someone at or above your rank, §3.4); 404 for an unknown person; 409 for an email
someone else has; 400 for anything else the server rejects. Each `detail` is a message
the UI can show as it is.
"""

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.config import Settings, get_settings
from app.core.permissions import MembershipContext, can_manage_person, resolve_widest_scope
from app.repositories import admin_people as repo
from app.repositories.membership import build_membership_context
from app.schemas.admin_people import (
    AdminActionResult,
    AdminMembershipRow,
    AdminPersonPage,
    AdminPersonRow,
    AssignMembershipInput,
    CreatePersonInput,
    UpdatePersonInput,
)

router = APIRouter(prefix="/people", tags=["people"])


def actor_contexts(
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> list[MembershipContext]:
    """The signed-in actor's active memberships, in the shape the permission checks use."""
    return [build_membership_context(db, m) for m in actor.active_memberships]


def require_person_manager(
    contexts: list[MembershipContext] = Depends(actor_contexts),
) -> list[MembershipContext]:
    """Allow only actors holding `manage` on `person`; otherwise answer 403."""
    if not can_manage_person(contexts):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage people",
        )
    return contexts


def require_membership_manager(
    contexts: list[MembershipContext] = Depends(actor_contexts),
) -> list[MembershipContext]:
    """Allow only actors holding `manage` on `membership` (at `all`); otherwise 403.

    The hierarchy rule for each membership is checked again in the repository, so
    this only decides who may use the screen at all.
    """
    if resolve_widest_scope(contexts, "membership", "manage") != "all":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage memberships",
        )
    return contexts


def _save(db: Session, change: Callable[[], int]) -> AdminPersonRow:
    """Run a person change, commit it, and answer with the person as now saved.

    `change` returns the changed person's id. The repository's errors become HTTP
    errors. The repository checks everything before it changes anything, so a refusal
    has written nothing and needs no rollback. Only `IntegrityError` comes after a
    write: two requests raced for the same email, and the unique index refused the
    second. That one rolls back, so nothing is half-saved.
    """
    try:
        person_id = change()
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Someone already has that email address."
        ) from None
    except repo.PersonNotFoundError:
        raise HTTPException(status_code=404, detail="Person not found") from None
    except repo.NotAllowedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except repo.EmailTakenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AdminPersonRow(**repo.get_person_row(db, person_id))


@router.get("", response_model=AdminPersonPage)
def list_people(
    search: str = "",
    page: int = Query(0, ge=0),
    page_size: int = Query(10, ge=1, le=100, alias="pageSize"),
    _contexts: list[MembershipContext] = Depends(require_person_manager),
    db: Session = Depends(get_db),
) -> AdminPersonPage:
    """Everyone except anonymised records, searchable by name or email."""
    return AdminPersonPage(**repo.list_people(db, search=search, page=page, page_size=page_size))


@router.post("", response_model=AdminPersonRow, status_code=status.HTTP_201_CREATED)
def create_person(
    body: CreatePersonInput,
    contexts: list[MembershipContext] = Depends(require_person_manager),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> AdminPersonRow:
    """Add a person. They can't sign in until they're assigned a membership."""
    return _save(
        db,
        lambda: (
            repo.create_person(
                db,
                contexts,
                first_name=body.firstName,
                last_name=body.lastName,
                email=body.email,
                allowed_domains=settings.allowed_email_domain_set,
            ).id
        ),
    )


@router.patch("/{person_id}", response_model=AdminPersonRow)
def update_person(
    person_id: int,
    body: UpdatePersonInput,
    contexts: list[MembershipContext] = Depends(require_person_manager),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> AdminPersonRow:
    """Change a person's name and/or AIESEC email."""
    return _save(
        db,
        lambda: (
            repo.update_person(
                db,
                contexts,
                person_id,
                first_name=body.firstName,
                last_name=body.lastName,
                email=body.email,
                allowed_domains=settings.allowed_email_domain_set,
            ).id
        ),
    )


@router.post("/{person_id}/deactivate", response_model=AdminPersonRow)
def deactivate_person(
    person_id: int,
    contexts: list[MembershipContext] = Depends(require_person_manager),
    db: Session = Depends(get_db),
) -> AdminPersonRow:
    """Deactivate: they can't sign in, and their current memberships end. Deletes nothing."""
    return _save(db, lambda: repo.deactivate_person(db, contexts, person_id).id)


@router.post("/{person_id}/reactivate", response_model=AdminPersonRow)
def reactivate_person(
    person_id: int,
    contexts: list[MembershipContext] = Depends(require_person_manager),
    db: Session = Depends(get_db),
) -> AdminPersonRow:
    """Undo a deactivation. Ended memberships stay ended; assign a new one for access."""
    return _save(db, lambda: repo.reactivate_person(db, contexts, person_id).id)


@router.get("/{person_id}/memberships", response_model=list[AdminMembershipRow])
def list_person_memberships(
    person_id: int,
    _contexts: list[MembershipContext] = Depends(require_membership_manager),
    db: Session = Depends(get_db),
) -> list[AdminMembershipRow]:
    """Every membership the person has held, newest first."""
    try:
        rows = repo.list_person_memberships(db, person_id)
    except repo.PersonNotFoundError:
        raise HTTPException(status_code=404, detail="Person not found") from None
    return [AdminMembershipRow(**row) for row in rows]


@router.post("/{person_id}/memberships", response_model=AdminActionResult)
def assign_membership(
    person_id: int,
    body: AssignMembershipInput,
    contexts: list[MembershipContext] = Depends(require_membership_manager),
    db: Session = Depends(get_db),
) -> AdminActionResult:
    """Assign a new membership. In another LC, this is a transfer (spec §5.1).

    A refusal is a normal answer (`status: "rejected"` with a message), like the
    Membership summary's Add member, so the dialog can show it.
    """
    try:
        result = repo.assign_membership(
            db,
            contexts,
            person_id=person_id,
            lc_id=body.lcId,
            position_key=body.positionKey,
            function_key=body.functionKey,
            team_id=body.teamId,
            start_date=body.startDate,
            end_date=body.endDate,
            term_id=body.termId,
        )
    except repo.PersonNotFoundError:
        raise HTTPException(status_code=404, detail="Person not found") from None
    # Every refusal happens before anything is written, so only success commits.
    if result["status"] == "created":
        db.commit()
    return AdminActionResult(**result)
