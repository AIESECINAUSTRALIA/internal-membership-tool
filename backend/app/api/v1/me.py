"""The signed-in person's own custom fields and position history: the Profile
page (Spec §2A.9).

`GET /api/v1/me` itself (who you are, your active memberships and permissions)
lives in `auth.py`: it is the sign-in check. These have their own routes so a
problem with either can never stop anyone signing in, and so `/me`'s
memberships stay exactly the ones that grant access (§3.2).

No endpoint here takes a person id. The person is always the signed-in actor
from `get_current_actor`, so these endpoints cannot read or write anyone else's
record. The §3.4 rank check does not apply: you are always acting on yourself.
"""

from fastapi import APIRouter, Body, HTTPException, status

from app.api.deps import CurrentActorDep, DbSession
from app.core.permissions import resolve_widest_scope
from app.repositories import person as repo
from app.repositories.attribute import AttributeValidationError
from app.repositories.membership import build_membership_context
from app.schemas.me import CustomField, CustomFieldValue, MembershipHistoryItem

router = APIRouter(prefix="/me", tags=["me"])


def _custom_fields(db: DbSession, actor: CurrentActorDep) -> list[CustomField]:
    return [
        CustomField(**field)
        for field in repo.get_custom_fields(db, actor.person.id, actor.active_memberships)
    ]


@router.get("/custom-fields", response_model=list[CustomField])
def get_my_custom_fields(actor: CurrentActorDep, db: DbSession) -> list[CustomField]:
    """Your editable person-level custom fields and their values (getMyCustomFields)."""
    return _custom_fields(db, actor)


@router.get("/memberships", response_model=list[MembershipHistoryItem])
def get_my_membership_history(actor: CurrentActorDep, db: DbSession) -> list[MembershipHistoryItem]:
    """Every membership you have held, past, current and future, newest first
    (getMyMembershipHistory). Display only: it grants nothing."""
    return [MembershipHistoryItem(**item) for item in repo.membership_history(db, actor.person.id)]


@router.patch("/custom-fields", response_model=list[CustomField])
def update_my_custom_fields(
    actor: CurrentActorDep,
    db: DbSession,
    values: dict[str, CustomFieldValue] = Body(...),
) -> list[CustomField]:
    """Save your own person-level custom fields (updateMyCustomFields).

    The body maps attribute keys to values, e.g. `{"shirt_size": "M"}`. Any key
    that isn't an editable custom field (including `full_name`, `aiesec_email`,
    membership fields or dates) gets a 422 and nothing is saved. Returns the
    fields as they are after saving, in the same shape as the GET.
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
    return _custom_fields(db, actor)
