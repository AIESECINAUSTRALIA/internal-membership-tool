"""Pydantic schemas for the positions & functions endpoints (spec §1.5, §2A.2)."""

from pydantic import BaseModel, ConfigDict


class PositionResponse(BaseModel):
    id: int
    key: str
    label: str
    rank: int | None
    level: str | None
    can_add_same_rank: bool
    active: bool

    model_config = ConfigDict(from_attributes=True)


class PositionCreate(BaseModel):
    label: str
    level: str | None = None
    rank: int | None = None
    can_add_same_rank: bool = False


class PositionUpdate(BaseModel):
    """Partial update — only present fields are applied."""

    label: str | None = None
    level: str | None = None
    rank: int | None = None
    can_add_same_rank: bool | None = None
    active: bool | None = None


class FunctionResponse(BaseModel):
    id: int
    key: str
    label: str
    active: bool

    model_config = ConfigDict(from_attributes=True)


class FunctionCreate(BaseModel):
    label: str


class FunctionUpdate(BaseModel):
    """Partial update — only present fields are applied."""

    label: str | None = None
    active: bool | None = None
