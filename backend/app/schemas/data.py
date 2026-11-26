"""Pydantic schemas for the Data page analytics endpoint (spec §2A.7, §6),
matching DataChart / DataSummaryRow in frontend/src/api/types.ts."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.home import KpiRef


class DataSummaryRow(BaseModel):
    label: str
    value: float


class DataChartPoint(BaseModel):
    month: str  # "YYYY-MM"
    value: float


class DataChart(BaseModel):
    scope: Literal["team", "function", "lc", "all"]
    kpi: KpiRef | None
    availableKpis: list[KpiRef]
    summaryRows: list[DataSummaryRow]
    period: Literal["monthly"]
    points: list[DataChartPoint]
