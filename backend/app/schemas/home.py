"""Pydantic schemas for the homepage chart (spec §2A.4), matching `HomeChart` in
frontend/src/api/types.ts."""

from typing import Literal

from pydantic import BaseModel


class KpiRef(BaseModel):
    key: str
    label: str
    unit: str | None


class HomeChartPoint(BaseModel):
    month: str  # "YYYY-MM"
    value: float


class HomeChart(BaseModel):
    scope: Literal["team", "function", "all"]
    # The KPI plotted; None when nothing was picked and the function has no default.
    kpi: KpiRef | None
    # What the viewer may pick instead (their function's KPIs plus shared ones).
    availableKpis: list[KpiRef]
    title: str
    period: Literal["monthly"]
    # Empty when there is no KPI or no record in the window: the UI says "No data exists".
    points: list[HomeChartPoint]
