"""Pydantic schemas for the attribute catalog endpoints."""

from pydantic import BaseModel, ConfigDict

from app.models.attribute import AttributeAppliesTo, AttributeDataType


class AttributeCreate(BaseModel):
    key: str
    label: str
    applies_to: AttributeAppliesTo
    data_type: AttributeDataType
    unit: str | None = None
    enum_options: list[str] | None = None
    validation: dict[str, object] | None = None
    function_id: int | None = None


class AttributeUpdate(BaseModel):
    """Partial update — only fields sent in the request are applied, so sending
    `null` clears `unit`, `enum_options`, `validation` or `function_id`.

    The defaults on `label`, `data_type` and `active` are never used (the endpoint
    reads `exclude_unset`); those three just can't be `null`. `key` and `applies_to`
    are fixed at creation, so sending them is refused as an unknown field.
    """

    label: str = ""
    data_type: AttributeDataType = AttributeDataType.TEXT
    unit: str | None = None
    enum_options: list[str] | None = None
    validation: dict[str, object] | None = None
    function_id: int | None = None
    active: bool = True

    model_config = ConfigDict(extra="forbid")


class AttributeResponse(BaseModel):
    id: int
    key: str
    label: str
    applies_to: AttributeAppliesTo
    data_type: AttributeDataType
    unit: str | None
    enum_options: list[str] | None
    validation: dict[str, object] | None
    function_id: int | None
    active: bool
    # True once any value references this attribute, which locks `data_type`.
    in_use: bool = False

    model_config = ConfigDict(from_attributes=True)
