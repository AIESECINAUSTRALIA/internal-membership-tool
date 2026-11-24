"""Pydantic schemas for the positions & functions endpoints (spec §1.5, §2A.2)."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# Which kind of entity a position belongs to (spec §3.6).
Level = Literal["lc", "mc"]

# A display name: surrounding spaces are trimmed, and it can't end up empty.
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class PositionResponse(BaseModel):
    id: int
    key: str
    label: str
    # Still nullable in the database for positions created before DEV-0049.
    rank: int | None
    level: str | None
    can_add_same_rank: bool
    active: bool

    model_config = ConfigDict(from_attributes=True)


class PositionCreate(BaseModel):
    """Level and rank are required: every position belongs to an LC or the MC
    (spec §3.6), and the hierarchy rule (§3.4) needs a rank to compare."""

    label: Label
    level: Level
    rank: int = Field(ge=1)
    can_add_same_rank: bool = False


class PositionUpdate(BaseModel):
    """Partial update: only the fields that are sent are changed.

    `level` and `rank` can be changed but not cleared. Sending them as `null`
    is rejected (422) instead of being silently ignored.
    """

    label: Label | None = None
    level: Level | None = None
    rank: int | None = Field(default=None, ge=1)
    can_add_same_rank: bool | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def level_and_rank_cannot_be_cleared(self) -> Self:
        for field in ("level", "rank"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError("Level and rank can't be cleared")
        return self


class FunctionResponse(BaseModel):
    id: int
    key: str
    label: str
    active: bool

    model_config = ConfigDict(from_attributes=True)


class FunctionCreate(BaseModel):
    label: Label


class FunctionUpdate(BaseModel):
    """Partial update: only the fields that are sent are changed."""

    label: Label | None = None
    active: bool | None = None
