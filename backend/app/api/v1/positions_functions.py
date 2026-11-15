"""Positions and functions management endpoints (spec §1.5, §2A.2).

Listing is open to any signed-in actor (the add-member flow needs active
positions and functions). Mutations require `manage` on `position` or
`function` respectively, enforced by `require_position_manager` /
`require_function_manager`. There is no delete endpoint: deactivating is the
soft delete, and the DB's FK constraints prevent hard deletes while memberships
reference a row.
"""

from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.core.permissions import can_manage_function, can_manage_position
from app.models.org import Function, Position
from app.repositories.membership import build_membership_context
from app.repositories.positions_functions import (
    create_function,
    create_position,
    get_function,
    get_position,
    list_functions,
    list_positions,
    update_function,
    update_position,
)
from app.schemas.positions_functions import (
    FunctionCreate,
    FunctionResponse,
    FunctionUpdate,
    PositionCreate,
    PositionResponse,
    PositionUpdate,
)

router = APIRouter(tags=["positions-functions"])

LABEL_TAKEN_MSG = "A position with that label already exists"
FUNC_LABEL_TAKEN_MSG = "A function with that label already exists"


def _actor_membership_id(actor: CurrentActor) -> int | None:
    return actor.acting_membership.id if actor.acting_membership else None


def _require_position_manager(
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> CurrentActor:
    contexts = [build_membership_context(db, m) for m in actor.active_memberships]
    if not can_manage_position(contexts):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage positions",
        )
    return actor


def _require_function_manager(
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> CurrentActor:
    contexts = [build_membership_context(db, m) for m in actor.active_memberships]
    if not can_manage_function(contexts):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage functions",
        )
    return actor


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

positions_router = APIRouter(prefix="/positions")


@positions_router.get("", response_model=list[PositionResponse])
def list_positions_endpoint(
    include_inactive: bool = False,
    _actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> Sequence[Position]:
    return list_positions(db, include_inactive=include_inactive)


@positions_router.post("", response_model=PositionResponse, status_code=status.HTTP_201_CREATED)
def create_position_endpoint(
    body: PositionCreate,
    actor: CurrentActor = Depends(_require_position_manager),
    db: Session = Depends(get_db),
) -> Position:
    try:
        pos = create_position(
            db,
            label=body.label,
            level=body.level,
            rank=body.rank,
            can_add_same_rank=body.can_add_same_rank,
            actor_membership_id=_actor_membership_id(actor),
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=LABEL_TAKEN_MSG) from None
    return pos


@positions_router.patch("/{position_id}", response_model=PositionResponse)
def update_position_endpoint(
    position_id: int,
    body: PositionUpdate,
    actor: CurrentActor = Depends(_require_position_manager),
    db: Session = Depends(get_db),
) -> Position:
    if get_position(db, position_id) is None:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
    try:
        pos = update_position(
            db,
            position_id=position_id,
            label=body.label,
            level=body.level,
            rank=body.rank,
            can_add_same_rank=body.can_add_same_rank,
            active=body.active,
            actor_membership_id=_actor_membership_id(actor),
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=LABEL_TAKEN_MSG) from None
    db.refresh(pos)
    return pos


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

functions_router = APIRouter(prefix="/functions")


@functions_router.get("", response_model=list[FunctionResponse])
def list_functions_endpoint(
    include_inactive: bool = False,
    _actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> Sequence[Function]:
    return list_functions(db, include_inactive=include_inactive)


@functions_router.post("", response_model=FunctionResponse, status_code=status.HTTP_201_CREATED)
def create_function_endpoint(
    body: FunctionCreate,
    actor: CurrentActor = Depends(_require_function_manager),
    db: Session = Depends(get_db),
) -> Function:
    try:
        func = create_function(
            db,
            label=body.label,
            actor_membership_id=_actor_membership_id(actor),
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=FUNC_LABEL_TAKEN_MSG) from None
    return func


@functions_router.patch("/{function_id}", response_model=FunctionResponse)
def update_function_endpoint(
    function_id: int,
    body: FunctionUpdate,
    actor: CurrentActor = Depends(_require_function_manager),
    db: Session = Depends(get_db),
) -> Function:
    if get_function(db, function_id) is None:
        raise HTTPException(status_code=404, detail=f"Function {function_id} not found")
    try:
        func = update_function(
            db,
            function_id=function_id,
            label=body.label,
            active=body.active,
            actor_membership_id=_actor_membership_id(actor),
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=FUNC_LABEL_TAKEN_MSG) from None
    db.refresh(func)
    return func


router.include_router(positions_router)
router.include_router(functions_router)
