"""Attribute catalog endpoints: KPIs and custom fields (spec §1.5, §4.2).

Everything here needs `manage` on `attribute` (MC and admin positions), checked
by `require_attribute_manager`. There is no delete endpoint: an attribute is
removed by marking it inactive, which leaves its stored values alone.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.core.permissions import can_manage_attribute
from app.models.attribute import Attribute, AttributeAppliesTo
from app.repositories.attribute import (
    AttributeValidationError,
    activate_attribute,
    attribute_ids_in_use,
    create_attribute,
    deactivate_attribute,
    list_attributes,
    update_attribute,
)
from app.repositories.membership import build_membership_context
from app.schemas.attribute import AttributeCreate, AttributeResponse, AttributeUpdate

router = APIRouter(prefix="/attributes", tags=["attributes"])

KEY_TAKEN_MESSAGE = "An attribute with that key already exists"


def require_attribute_manager(
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> CurrentActor:
    """Allow only actors holding `manage` on `attribute`; otherwise answer 403."""
    contexts = [build_membership_context(db, m) for m in actor.active_memberships]
    if not can_manage_attribute(contexts):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage attributes",
        )
    return actor


def _actor_membership_id(actor: CurrentActor) -> int | None:
    """The membership the audit log should credit for this action."""
    if actor.acting_membership is None:
        return None
    return actor.acting_membership.id


def _respond(attribute: Attribute, *, in_use: bool) -> AttributeResponse:
    response = AttributeResponse.model_validate(attribute)
    return response.model_copy(update={"in_use": in_use})


@router.get("", response_model=list[AttributeResponse])
def list_attributes_endpoint(
    applies_to: AttributeAppliesTo | None = None,
    include_inactive: bool = False,
    _actor: CurrentActor = Depends(require_attribute_manager),
    db: Session = Depends(get_db),
) -> list[AttributeResponse]:
    attributes = list_attributes(db, applies_to=applies_to, include_inactive=include_inactive)
    in_use = attribute_ids_in_use(db, [attribute.id for attribute in attributes])
    return [_respond(attribute, in_use=attribute.id in in_use) for attribute in attributes]


@router.post("", response_model=AttributeResponse, status_code=status.HTTP_201_CREATED)
def create_attribute_endpoint(
    body: AttributeCreate,
    actor: CurrentActor = Depends(require_attribute_manager),
    db: Session = Depends(get_db),
) -> AttributeResponse:
    try:
        attribute = create_attribute(
            db,
            **body.model_dump(),
            actor_membership_id=_actor_membership_id(actor),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=KEY_TAKEN_MESSAGE) from None
    except AttributeValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _respond(attribute, in_use=False)


@router.patch("/{attribute_id}", response_model=AttributeResponse)
def update_attribute_endpoint(
    attribute_id: int,
    body: AttributeUpdate,
    actor: CurrentActor = Depends(require_attribute_manager),
    db: Session = Depends(get_db),
) -> AttributeResponse:
    attribute = db.get(Attribute, attribute_id)
    if attribute is None:
        raise HTTPException(status_code=404, detail=f"Attribute {attribute_id} not found")

    changes = body.model_dump(exclude_unset=True)
    active = changes.pop("active", None)
    actor_id = _actor_membership_id(actor)
    try:
        if changes:
            update_attribute(
                db, attribute_id=attribute_id, changes=changes, actor_membership_id=actor_id
            )
        if active is False:
            deactivate_attribute(db, attribute_id=attribute_id, actor_membership_id=actor_id)
        if active is True:
            activate_attribute(db, attribute_id=attribute_id, actor_membership_id=actor_id)
        db.commit()
    except AttributeValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.refresh(attribute)
    return _respond(attribute, in_use=bool(attribute_ids_in_use(db, {attribute_id})))
