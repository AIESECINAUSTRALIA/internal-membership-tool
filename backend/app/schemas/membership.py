"""Pydantic schemas matching the shapes defined in frontend/src/api/types.ts."""

from datetime import date
from typing import Literal

from pydantic import BaseModel


class LcRef(BaseModel):
    id: str
    name: str
    type: Literal["lc", "mc"]


class PositionRef(BaseModel):
    key: str
    label: str
    level: Literal["lc", "mc"]
    rank: int
    canAddSameRank: bool
    presidential: bool
    homeChartScope: Literal["team", "function", "all"]
    holdsTeam: bool


class FunctionRef(BaseModel):
    key: str
    label: str


class MemberRole(BaseModel):
    membershipId: str
    position: PositionRef
    function: FunctionRef | None = None
    teamId: str | None = None


class MemberSummaryRow(BaseModel):
    personId: str
    firstName: str
    lastName: str
    lc: LcRef
    roles: list[MemberRole]


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    pageSize: int


class MemberQuery(BaseModel):
    search: str = ""
    sortField: Literal["firstName", "lastName", "lc", "position"] = "lastName"
    sortDirection: Literal["asc", "desc"] = "asc"
    page: int = 0
    pageSize: int = 15
    lcId: str | None = None


class AddMemberInput(BaseModel):
    email: str
    lcId: int
    positionKey: str
    functionKey: str | None = None
    teamId: int | None = None
    startDate: date
    endDate: date
    termId: int | None = None
    firstName: str | None = None
    lastName: str | None = None
    confirmedExisting: bool = False
    membershipId: int | None = None


class AddMemberResult(BaseModel):
    status: Literal["created", "confirm_existing", "needs_name", "rejected"]
    message: str | None = None


class ActionResult(BaseModel):
    status: Literal["ok", "rejected"]
    message: str | None = None


class TeamOption(BaseModel):
    id: str
    name: str
    lcId: str
    functionKey: str


class CurrentTeamRef(BaseModel):
    id: str
    name: str


class MembershipDetail(BaseModel):
    membershipId: str
    personName: str
    position: PositionRef
    function: FunctionRef | None = None
    lc: LcRef
    startDate: str
    endDate: str | None = None
    currentTeam: CurrentTeamRef | None = None
    teamOptions: list[TeamOption]


class ExtendTermInput(BaseModel):
    newEndDate: date


class MoveToTeamInput(BaseModel):
    teamId: int
