"""The signed-in person's own record: the Profile page (Spec §2A.9).

Neither endpoint takes a person id. The person is always the signed-in actor
from `get_current_actor`, so these endpoints cannot read or write anyone else's
record. The §3.4 rank check does not apply: you are always acting on yourself.
"""

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.core.permissions import resolve_widest_scope
from app.repositories import person as repo
from app.repositories.attribute import AttributeValidationError
from app.repositories.membership import build_membership_context
from app.schemas.me import CustomFieldValue, Me

router = APIRouter(prefix="/me", tags=["me"])


def _me(db: Session, actor: CurrentActor) -> Me:
    contexts = [build_membership_context(db, m) for m in actor.active_memberships]
    return Me(
        **repo.build_me(
            db,
            person=actor.person,
            active_memberships=actor.active_memberships,
            contexts=contexts,
        )
    )


@router.get("", response_model=Me)
def get_me(
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> Me:
    """Identity, custom fields, position history and permissions (getMe)."""
    return _me(db, actor)


@router.patch("/custom-fields", response_model=Me)
def update_my_custom_fields(
    values: dict[str, CustomFieldValue] = Body(...),
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> Me:
    """Save your own person-level custom fields (updateMyCustomFields).

    The body maps attribute keys to values, e.g. `{"shirt_size": "M"}`. Any key
    that isn't an editable custom field (including `full_name`, `aiesec_email`,
    membership fields or dates) gets a 422 and nothing is saved.
    """
    contexts = [build_membership_context(db, m) for m in actor.active_memberships]
    # Every position holds `member_record:edit` at `own` scope or wider, and any
    # scope covers your own record, so holding the grant at all is enough.
    if actor.acting_membership is None or (
        resolve_widest_scope(contexts, "member_record", "edit") is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit your record.",
        )

    try:
        repo.update_own_custom_fields(
            db,
            person=actor.person,
            active_memberships=actor.active_memberships,
            acting_membership=actor.acting_membership,
            values=values,
        )
    except (repo.UnknownCustomFieldError, AttributeValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    db.commit()
    return _me(db, actor)
