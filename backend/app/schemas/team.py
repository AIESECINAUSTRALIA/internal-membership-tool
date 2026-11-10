"""Pydantic schemas for the team endpoints."""

from pydantic import BaseModel, ConfigDict


class TeamCreate(BaseModel):
    name: str
    function_id: int
    term_id: int


class TeamUpdate(BaseModel):
    """Partial update — only present fields are applied."""

    name: str | None = None
    function_id: int | None = None
    leader_membership_id: int | None = None
    # Set to False to disband the team (spec §1.5). True is not accepted here —
    # a disbanded team cannot be re-activated.
    active: bool | None = None


class MoveMemberRequest(BaseModel):
    membership_id: int


class TeamResponse(BaseModel):
    id: int
    lc_id: int
    function_id: int
    term_id: int
    name: str
    leader_membership_id: int | None
    active: bool

    model_config = ConfigDict(from_attributes=True)
