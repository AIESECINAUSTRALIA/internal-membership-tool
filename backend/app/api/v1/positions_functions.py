"""Positions and functions management endpoints (spec §1.5, §2A.2).

Listing is open to any signed-in actor (the add-member flow needs active
positions and functions). Changes need `manage` on `position` or `function`,
checked by `require_position_manager` / `require_function_manager`.

Positions have one more rule (spec §3.4, `can_edit_position`): you can only
change a position ranked below your own, and only give it a rank below yours.

There is no delete endpoint: deactivating is the soft delete, and the DB's FK
constraints prevent hard deletes while memberships reference a row.
"""

from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.core.permissions import (
    MembershipContext,
    can_edit_position,
    can_manage_function,
    can_manage_position,
)
from app.models.org import Function, Position
from app.repositories.membership import build_membership_context, effective_position_rank
from app.repositories.positions_functions import (
    create_function,
    create_position,
    get_function,
    get_position,
    list_functions,
    list_positions,
    rename_function,
    rename_position,
    set_function_active,
    set_position_active,
    set_position_details,
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

POSITION_NAME_TAKEN_MESSAGE = "A position with that name already exists"
FUNCTION_NAME_TAKEN_MESSAGE = "A function with that name already exists"
OUTRANKED_MESSAGE = "You can only change positions ranked below your own"


def _contexts(db: Session, actor: CurrentActor) -> list[MembershipContext]:
    return [build_membership_context(db, m) for m in actor.active_memberships]


def require_position_manager(
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> CurrentActor:
    """Allow only actors holding `manage` on `position`; otherwise answer 403."""
    if not can_manage_position(_contexts(db, actor)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage positions",
        )
    return actor


def require_function_manager(
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> CurrentActor:
    """Allow only actors holding `manage` on `function`; otherwise answer 403."""
    if not can_manage_function(_contexts(db, actor)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage functions",
        )
    return actor


def _require_outranks(
    db: Session, actor: CurrentActor, *, current_rank: int | None, new_rank: int | None
) -> None:
    """403 unless the hierarchy rule allows this position change (spec §3.4)."""
    if not can_edit_position(_contexts(db, actor), current_rank=current_rank, new_rank=new_rank):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=OUTRANKED_MESSAGE)


def _actor_membership_id(actor: CurrentActor) -> int | None:
    """The membership the audit log should credit for this action."""
    if actor.acting_membership is None:
        return None
    return actor.acting_membership.id


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
    actor: CurrentActor = Depends(require_position_manager),
    db: Session = Depends(get_db),
) -> Position:
    _require_outranks(db, actor, current_rank=None, new_rank=body.rank)
    try:
        position = create_position(
            db,
            label=body.label,
            level=body.level,
            rank=body.rank,
            can_add_same_rank=body.can_add_same_rank,
            actor_membership_id=_actor_membership_id(actor),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=POSITION_NAME_TAKEN_MESSAGE) from None
    return position


@positions_router.patch("/{position_id}", response_model=PositionResponse)
def update_position_endpoint(
    position_id: int,
    body: PositionUpdate,
    actor: CurrentActor = Depends(require_position_manager),
    db: Session = Depends(get_db),
) -> Position:
    position = get_position(db, position_id)
    if position is None:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
    # Compare against the rank the permission code actually uses: a row with no
    # stored rank (e.g. an MCP row inserted by hand) still ranks by its key.
    _require_outranks(db, actor, current_rank=effective_position_rank(position), new_rank=body.rank)

    actor_id = _actor_membership_id(actor)
    try:
        # Each kind of change is its own call with its own audit action, in one
        # transaction: either all of them happen or none do.
        if body.label is not None:
            rename_position(
                db, position_id=position_id, new_label=body.label, actor_membership_id=actor_id
            )
        if body.level is not None or body.rank is not None or body.can_add_same_rank is not None:
            set_position_details(
                db,
                position_id=position_id,
                level=body.level,
                rank=body.rank,
                can_add_same_rank=body.can_add_same_rank,
                actor_membership_id=actor_id,
            )
        if body.active is not None:
            set_position_active(
                db, position_id=position_id, active=body.active, actor_membership_id=actor_id
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=POSITION_NAME_TAKEN_MESSAGE) from None
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.refresh(position)
    return position


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
    actor: CurrentActor = Depends(require_function_manager),
    db: Session = Depends(get_db),
) -> Function:
    try:
        function = create_function(
            db, label=body.label, actor_membership_id=_actor_membership_id(actor)
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=FUNCTION_NAME_TAKEN_MESSAGE) from None
    return function


@functions_router.patch("/{function_id}", response_model=FunctionResponse)
def update_function_endpoint(
    function_id: int,
    body: FunctionUpdate,
    actor: CurrentActor = Depends(require_function_manager),
    db: Session = Depends(get_db),
) -> Function:
    function = get_function(db, function_id)
    if function is None:
        raise HTTPException(status_code=404, detail=f"Function {function_id} not found")

    actor_id = _actor_membership_id(actor)
    try:
        if body.label is not None:
            rename_function(
                db, function_id=function_id, new_label=body.label, actor_membership_id=actor_id
            )
        if body.active is not None:
            set_function_active(
                db, function_id=function_id, active=body.active, actor_membership_id=actor_id
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=FUNCTION_NAME_TAKEN_MESSAGE) from None
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.refresh(function)
    return function


router.include_router(positions_router)
router.include_router(functions_router)
