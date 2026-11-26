"""Changing one membership on the Admin console (spec §2A.2, DEV-47): correct or end.

Both need `manage` on `membership` (`require_membership_manager`), and the repository
applies the hierarchy rule (§3.4) and the level-match rule (§3.6) to each one. Listing
and assigning a person's memberships is under `/people/{id}/memberships`
(`api/v1/people.py`).

Separate from `/members` (`api/v1/members.py`), which is the main app's Membership
summary with its own scoped grants (§2A.5).

A refusal is a normal answer (`status: "rejected"` with a message), the same as the
Membership summary's actions, so the dialog can show it.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.v1.people import require_membership_manager
from app.core.permissions import MembershipContext
from app.repositories import admin_people as repo
from app.schemas.admin_people import AdminActionResult, CorrectMembershipInput, EndMembershipInput

router = APIRouter(prefix="/memberships", tags=["memberships"])


@router.patch("/{membership_id}", response_model=AdminActionResult)
def correct_membership(
    membership_id: int,
    body: CorrectMembershipInput,
    contexts: list[MembershipContext] = Depends(require_membership_manager),
    db: Session = Depends(get_db),
) -> AdminActionResult:
    """Fix a mistake in position, function or dates. Fields left out are unchanged."""
    correction = repo.MembershipCorrection(
        position_key=body.positionKey,
        function_key=body.functionKey,
        # `functionKey: null` sent on purpose removes the function; left out, it stays.
        clear_function="functionKey" in body.model_fields_set and body.functionKey is None,
        start_date=body.startDate,
        end_date=body.endDate,
    )
    result = repo.correct_membership(db, contexts, membership_id, correction)
    if result["status"] == "ok":
        db.commit()
    return AdminActionResult(**result)


@router.post("/{membership_id}/end", response_model=AdminActionResult)
def end_membership(
    membership_id: int,
    body: EndMembershipInput,
    contexts: list[MembershipContext] = Depends(require_membership_manager),
    db: Session = Depends(get_db),
) -> AdminActionResult:
    """End a membership on an earlier date. History is kept."""
    result = repo.end_membership(db, contexts, membership_id, body.endDate)
    if result["status"] == "ok":
        db.commit()
    return AdminActionResult(**result)
