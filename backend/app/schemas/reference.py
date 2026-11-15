"""Reference data the membership pages pick from (DEV-0043).

Shapes match `Lc`, `Term` and `Team` in `frontend/src/api/types.ts`, so the
frontend uses them without translating. Ids are strings on the wire, like
every other id the frontend sees.
"""

from typing import Literal

from pydantic import BaseModel


class LcOption(BaseModel):
    id: str
    name: str
    type: Literal["lc", "mc"]
    state: str | None
    active: bool


class TermOption(BaseModel):
    id: str
    name: str
    startDate: str
    endDate: str


class TeamLeader(BaseModel):
    membershipId: str
    name: str


class TeamOption(BaseModel):
    id: str
    name: str
    lcId: str
    functionKey: str
    # None = the team currently has no leader.
    leader: TeamLeader | None


class MembershipOptions(BaseModel):
    lcs: list[LcOption]
    terms: list[TermOption]
    teams: list[TeamOption]
