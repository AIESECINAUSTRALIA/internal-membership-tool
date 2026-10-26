"""Response shape of `GET /api/v1/me`: the signed-in person (spec §9, §2A.9)."""

from datetime import date

from pydantic import BaseModel


class PersonOut(BaseModel):
    id: int
    full_name: str
    preferred_name: str | None
    # The only contact detail the tool stores (spec §4.1).
    aiesec_email: str


class LookupOut(BaseModel):
    """A row of a lookup table (`position`, `function`), by its stable `key`."""

    key: str
    label: str


class LcOut(BaseModel):
    id: int
    name: str
    type: str  # "LC" or "MC"


class TeamOut(BaseModel):
    id: int
    name: str


class MembershipOut(BaseModel):
    id: int
    position: LookupOut
    function: LookupOut | None
    lc: LcOut
    team: TeamOut | None
    start_date: date
    end_date: date | None


class PermissionOut(BaseModel):
    resource: str
    action: str
    scope: str


class MeResponse(BaseModel):
    # The email the caller signed in with, even when no `person` matches it.
    email: str
    # Null when the email matches no `person`: the frontend shows the not-allocated page.
    person: PersonOut | None
    # ACTIVE memberships only. Empty means not allocated (spec §9).
    memberships: list[MembershipOut]
    # Everything the person may do, from all active memberships, widest scope per
    # (resource, action) (spec §3.2). Empty when not allocated. See docs/auth.md.
    permissions: list[PermissionOut]
