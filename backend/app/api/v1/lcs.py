"""LC management endpoints (spec §1.5, §2A.2).

Reading LCs needs a signed-in actor. Every mutating endpoint also needs
`manage` on `lc` (MC and admin positions), checked by `require_lc_manager`.
There is no delete endpoint: an LC is removed by marking it inactive.
"""

from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.core.permissions import can_manage_lc
from app.models.org import LC, StateTimezone
from app.repositories.lc import (
    activate_lc,
    create_lc,
    deactivate_lc,
    get_lc,
    list_lcs,
    merge_lcs,
    rename_lc,
    set_lc_state,
)
from app.repositories.membership import build_membership_context
from app.schemas.lc import (
    LCCreate,
    LCMergeRequest,
    LCResponse,
    LCUpdate,
    MergeResult,
    StateTimezoneResponse,
)

router = APIRouter(prefix="/lcs", tags=["lcs"])

NAME_TAKEN_MESSAGE = "An LC with that name already exists"


def require_lc_manager(
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> CurrentActor:
    """Allow only actors holding `manage` on `lc`; otherwise answer 403."""
    contexts = [build_membership_context(db, m) for m in actor.active_memberships]
    if not can_manage_lc(contexts):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage LCs",
        )
    return actor


def _actor_membership_id(actor: CurrentActor) -> int | None:
    """The membership the audit log should credit for this action."""
    if actor.acting_membership is None:
        return None
    return actor.acting_membership.id


@router.get("/state-timezones", response_model=list[StateTimezoneResponse])
def list_state_timezones(
    _actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> Sequence[StateTimezone]:
    """List the state → timezone lookup table."""
    return db.execute(select(StateTimezone)).scalars().all()


@router.get("", response_model=list[LCResponse])
def list_lcs_endpoint(
    include_inactive: bool = False,
    _actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> Sequence[LC]:
    return list_lcs(db, include_inactive=include_inactive)


@router.post("", response_model=LCResponse, status_code=status.HTTP_201_CREATED)
def create_lc_endpoint(
    body: LCCreate,
    actor: CurrentActor = Depends(require_lc_manager),
    db: Session = Depends(get_db),
) -> LC:
    try:
        lc = create_lc(
            db,
            name=body.name,
            lc_type=body.lc_type,
            state=body.state,
            actor_membership_id=_actor_membership_id(actor),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=NAME_TAKEN_MESSAGE) from None
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return lc


@router.patch("/{lc_id}", response_model=LCResponse)
def update_lc_endpoint(
    lc_id: int,
    body: LCUpdate,
    actor: CurrentActor = Depends(require_lc_manager),
    db: Session = Depends(get_db),
) -> LC:
    lc = get_lc(db, lc_id)
    if lc is None:
        raise HTTPException(status_code=404, detail=f"LC {lc_id} not found")

    actor_id = _actor_membership_id(actor)
    try:
        if body.name is not None:
            rename_lc(db, lc_id=lc_id, new_name=body.name, actor_membership_id=actor_id)
        if body.state is not None:
            set_lc_state(db, lc_id=lc_id, state=body.state, actor_membership_id=actor_id)
        if body.active is False:
            deactivate_lc(db, lc_id=lc_id, actor_membership_id=actor_id)
        if body.active is True:
            activate_lc(db, lc_id=lc_id, actor_membership_id=actor_id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=NAME_TAKEN_MESSAGE) from None
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.refresh(lc)
    return lc


@router.post("/{lc_id}/merge", response_model=MergeResult)
def merge_lcs_endpoint(
    lc_id: int,
    body: LCMergeRequest,
    actor: CurrentActor = Depends(require_lc_manager),
    db: Session = Depends(get_db),
) -> MergeResult:
    if get_lc(db, lc_id) is None:
        raise HTTPException(status_code=404, detail=f"LC {lc_id} not found")
    if get_lc(db, body.target_id) is None:
        raise HTTPException(status_code=404, detail=f"LC {body.target_id} not found")

    try:
        summary = merge_lcs(
            db,
            source_id=lc_id,
            target_id=body.target_id,
            actor_membership_id=_actor_membership_id(actor),
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="The merge conflicts with existing data"
        ) from None

    return MergeResult(
        memberships_moved=summary.memberships_moved,
        future_memberships_repointed=summary.future_memberships_repointed,
        teams_created=summary.teams_created,
        teams_reused=summary.teams_reused,
        leaders_not_carried=summary.leaders_not_carried,
    )
