"""Pydantic schemas for the Profile page (Spec §2A.9).

They mirror `Me` and its parts in frontend/src/api/types.ts, field for field,
so the frontend can swap its mock for the real endpoint without changes.
"""

from typing import Literal

from pydantic import BaseModel

from app.core.permissions import Action, Scope
from app.schemas.membership import FunctionRef, PositionRef

# One custom-field value. Dates travel as "YYYY-MM-DD" strings. `bool` comes
# before `int` so `true` is never read as 1.
CustomFieldValue = str | bool | int | float | None


class CustomField(BaseModel):
    key: str
    label: str
    dataType: Literal["text", "number", "date", "boolean", "enum"]
    enumOptions: list[str] | None = None
    value: CustomFieldValue


class MeLc(BaseModel):
    id: str
    name: str
    type: Literal["lc", "mc"]
    state: str | None
    active: bool


class MeTeam(BaseModel):
    id: str
    name: str


class MembershipView(BaseModel):
    id: str
    position: PositionRef
    function: FunctionRef | None
    lc: MeLc
    team: MeTeam | None
    startDate: str
    endDate: str | None


class MePerson(BaseModel):
    id: str
    firstName: str
    lastName: str
    email: str
    customFields: list[CustomField]


class PermissionGrant(BaseModel):
    resource: str
    action: Action
    scope: Scope


class Me(BaseModel):
    person: MePerson
    memberships: list[MembershipView]
    permissions: list[PermissionGrant]
