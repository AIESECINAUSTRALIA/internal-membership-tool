"""LC management endpoints (spec §1.5, §2A.2).

Every mutating endpoint is gated on `manage` on `lc` in the permission
matrix. That check is not built yet — each one carries a TODO.
"""

from collections.abc import Generator, Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.org import StateTimezone
from app.repositories.lc import (
    create_lc,
    deactivate_lc,
    get_lc,
    list_lcs,
    merge_lcs,
    rename_lc,
    set_lc_state,
)
from app.schemas.lc import (
    LCCreate,
    LCMergeRequest,
    LCResponse,
    LCUpdate,
    MergeResult,
    StateTimezoneResponse,
)

router = APIRouter(prefix="/lcs", tags=["lcs"])


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/state-timezones", response_model=list[StateTimezoneResponse])
def list_state_timezones(db: Session = Depends(get_db)) -> Sequence[StateTimezone]:
    """List the state → timezone lookup table."""
    return db.execute(select(StateTimezone)).scalars().all()


@router.get("", response_model=list[LCResponse])
def list_lcs_endpoint(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
) -> object:
    return list_lcs(db, include_inactive=include_inactive)


@router.post("", response_model=LCResponse, status_code=status.HTTP_201_CREATED)
def create_lc_endpoint(body: LCCreate, db: Session = Depends(get_db)) -> object:
    # TODO: gate on manage lc permission
    try:
        lc = create_lc(
            db,
            name=body.name,
            lc_type=body.lc_type,
            state=body.state,
            actor_membership_id=None,  # TODO: replace with real actor when auth is built
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An LC with that name already exists") from None
    return lc


@router.patch("/{lc_id}", response_model=LCResponse)
def update_lc_endpoint(lc_id: int, body: LCUpdate, db: Session = Depends(get_db)) -> object:
    # TODO: gate on manage lc permission
    lc = get_lc(db, lc_id)
    if lc is None:
        raise HTTPException(status_code=404, detail=f"LC {lc_id} not found")

    try:
        if body.name is not None:
            rename_lc(db, lc_id=lc_id, new_name=body.name, actor_membership_id=None)
        if body.state is not None:
            set_lc_state(db, lc_id=lc_id, state=body.state, actor_membership_id=None)
        if body.active is False:
            deactivate_lc(db, lc_id=lc_id, actor_membership_id=None)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An LC with that name already exists") from None
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.refresh(lc)
    return lc


@router.post("/{lc_id}/merge", response_model=MergeResult)
def merge_lcs_endpoint(lc_id: int, body: LCMergeRequest, db: Session = Depends(get_db)) -> object:
    # TODO: gate on manage lc permission
    if get_lc(db, lc_id) is None:
        raise HTTPException(status_code=404, detail=f"LC {lc_id} not found")
    if get_lc(db, body.target_id) is None:
        raise HTTPException(status_code=404, detail=f"LC {body.target_id} not found")
    try:
        memberships_moved, teams_moved = merge_lcs(
            db,
            source_id=lc_id,
            target_id=body.target_id,
            actor_membership_id=None,  # TODO: replace with real actor when auth is built
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return MergeResult(memberships_moved=memberships_moved, teams_moved=teams_moved)
