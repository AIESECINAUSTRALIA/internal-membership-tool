"""Schemas for the Admin console's People and Memberships screens (DEV-47).

Field names match `frontend/src/api/types.ts` (camelCase), like `schemas/membership.py`.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.schemas.membership import FunctionRef, LcRef


class AdminPersonRow(BaseModel):
    id: str
    firstName: str
    lastName: str
    email: str
    # Has at least one membership active today.
    active: bool
    status: Literal["active", "alumnus", "inactive"]


class AdminPersonPage(BaseModel):
    rows: list[AdminPersonRow]
    total: int


class CreatePersonInput(BaseModel):
    firstName: str
    lastName: str
    email: str


class UpdatePersonInput(BaseModel):
    """Partial update: only fields that are present are changed."""

    firstName: str | None = None
    lastName: str | None = None
    email: str | None = None


class PositionLabel(BaseModel):
    key: str
    label: str


class AdminMembershipRow(BaseModel):
    id: str
    lc: LcRef
    position: PositionLabel | None
    function: FunctionRef | None
    termName: str | None
    teamName: str | None
    startDate: date
    endDate: date | None
    current: bool


class AssignMembershipInput(BaseModel):
    lcId: int
    positionKey: str
    functionKey: str | None = None
    teamId: int | None = None
    startDate: date
    endDate: date
    termId: int | None = None


class CorrectMembershipInput(BaseModel):
    """Partial update. Send `functionKey: null` explicitly to remove the function;
    leaving it out keeps the current one."""

    positionKey: str | None = None
    functionKey: str | None = None
    startDate: date | None = None
    endDate: date | None = None


class EndMembershipInput(BaseModel):
    endDate: date


class AdminActionResult(BaseModel):
    status: Literal["ok", "created", "rejected"]
    message: str | None = None
    membershipId: str | None = None
