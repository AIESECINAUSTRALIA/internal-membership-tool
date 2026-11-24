"""Response shapes of `GET /api/v1/me` (the signed-in person, spec §9) and of the
Profile routes under it (§2A.9): `/me/custom-fields` and `/me/memberships`."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.schemas.membership import FunctionRef, PositionRef


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
    state: str | None
    active: bool


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


# ---------------------------------------------------------------------------
# Profile: your own custom fields (`GET/PATCH /api/v1/me/custom-fields`, §2A.9).
# Kept off `MeResponse` on purpose: `/me` is the sign-in check, so a problem with
# the attribute catalog must never stop anyone signing in. These mirror
# `CustomField` in frontend/src/api/types.ts, field for field.
# ---------------------------------------------------------------------------

# One custom-field value. Dates travel as "YYYY-MM-DD" strings. `bool` comes
# before `int` so `true` is never read as 1.
CustomFieldValue = str | bool | int | float | None


class CustomField(BaseModel):
    key: str
    label: str
    dataType: Literal["text", "number", "date", "boolean", "enum"]
    enumOptions: list[str] | None = None
    value: CustomFieldValue


# ---------------------------------------------------------------------------
# Profile: your position history (`GET /api/v1/me/memberships`, §2A.9).
# Every membership you have held, past, current and future. `MeResponse` above
# keeps only the active ones, because those are what grant access (§3.2).
# These mirror `MembershipView` in frontend/src/api/types.ts, field for field.
# ---------------------------------------------------------------------------


class HistoryLc(BaseModel):
    id: str
    name: str
    type: Literal["lc", "mc"]
    state: str | None
    active: bool


class HistoryTeam(BaseModel):
    id: str
    name: str


class MembershipHistoryItem(BaseModel):
    id: str
    position: PositionRef
    function: FunctionRef | None
    lc: HistoryLc
    # The team this membership is in today, if any.
    team: HistoryTeam | None
    startDate: str
    endDate: str | None
