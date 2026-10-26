"""Pydantic schemas for the LC endpoints."""

from pydantic import BaseModel, ConfigDict

from app.models.org import LCType


class LCCreate(BaseModel):
    name: str
    lc_type: LCType
    state: str | None = None


class LCUpdate(BaseModel):
    """Partial update — only fields that are present are applied."""

    name: str | None = None
    state: str | None = None
    active: bool | None = None


class LCMergeRequest(BaseModel):
    target_id: int


class LCResponse(BaseModel):
    id: int
    name: str
    type: LCType
    state: str | None
    active: bool

    model_config = ConfigDict(from_attributes=True)


class MergeResult(BaseModel):
    """What a merge changed. KPI records are not moved: they stay with the
    membership they were logged against, so they keep counting towards the
    source LC."""

    memberships_moved: int
    future_memberships_repointed: int
    teams_created: int
    teams_reused: int
    leaders_not_carried: int


class StateTimezoneResponse(BaseModel):
    state: str
    timezone: str

    model_config = ConfigDict(from_attributes=True)
