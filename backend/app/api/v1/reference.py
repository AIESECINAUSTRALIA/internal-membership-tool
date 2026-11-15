"""Reference data for the membership pages (DEV-0043).

`GET /api/v1/reference/membership-options`: the real LCs, terms and teams that
Add member and the Membership page's LC filter offer, with real database ids.

Who may call it: a signed-in caller who matches a `person` here (`CurrentActor`).
Anyone with an aiesec.net account worldwide can sign in, so an account that isn't
one of our people must not see our teams or their leaders' names. Signing in does
not depend on this endpoint (the frontend takes positions from elsewhere), so an
unallocated person still reaches the "not allocated" page (spec §9).
"""

from fastapi import APIRouter

from app.api.deps import CurrentActorDep, DbSession
from app.repositories.reference import get_membership_options
from app.schemas.reference import MembershipOptions

router = APIRouter(prefix="/reference", tags=["reference"])


@router.get("/membership-options", response_model=MembershipOptions)
def membership_options(actor: CurrentActorDep, db: DbSession) -> MembershipOptions:
    # `actor` is unused in the body: asking for it is what requires one of our people.
    del actor
    return get_membership_options(db)
