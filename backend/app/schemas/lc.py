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
    memberships_moved: int
    teams_moved: int


class StateTimezoneResponse(BaseModel):
    state: str
    timezone: str

    model_config = ConfigDict(from_attributes=True)
