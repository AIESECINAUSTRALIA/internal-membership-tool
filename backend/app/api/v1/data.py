"""Data page analytics endpoint (spec §2A.7, §6).

GET /api/v1/data/chart returns KPI summary rows and a monthly time-series
for a caller-chosen scope (team / function / lc / all) and date range.

Scope is validated against the caller's `analytics_report.view` grant: a
viewer may only request a scope at or narrower than their widest grant.
Whose data each scope covers (spec §6):
  team     — records logged against the actor's current team
  function — memberships in the actor's LC with the actor's function
  lc       — all memberships in the actor's LC
  all      — every LC; optionally narrowed to one by ?lc_id=
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.core.permissions import DataChartScope, resolve_widest_scope, scope_rank
from app.models.attribute import Attribute
from app.repositories.attribute import AttributeValidationError
from app.repositories.kpi import (
    list_home_chart_kpis,
    month_starts,
    monthly_totals,
    resolve_home_chart_kpi,
    sum_by_function,
    sum_by_lc,
    sum_by_team_in_function,
    sum_by_team_member,
)
from app.repositories.membership import build_membership_context
from app.schemas.data import DataChart, DataChartPoint, DataSummaryRow
from app.schemas.home import KpiRef

router = APIRouter(prefix="/data", tags=["data"])


def _kpi_ref(attribute: Attribute) -> KpiRef:
    return KpiRef(key=attribute.key, label=attribute.label, unit=attribute.unit)


@router.get("/chart", response_model=DataChart)
def get_data_chart(
    scope: DataChartScope = Query(..., description="team | function | lc | all"),
    start: date = Query(..., description="Range start date (inclusive), YYYY-MM-DD"),
    end: date = Query(..., description="Range end date (inclusive), YYYY-MM-DD"),
    kpi: str | None = Query(default=None, description="KPI key; omit for function default"),
    lc_id: int | None = Query(default=None, description="Narrow 'all' scope to one LC"),
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> DataChart:
    """Data page analytics: summary rows + monthly time-series (getDataChart)."""
    if actor.acting_membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You have not been allocated yet",
        )

    # Permission check: does the caller hold analytics_report.view at or wider than
    # the requested scope?
    contexts = [build_membership_context(db, m) for m in actor.active_memberships]
    widest = resolve_widest_scope(contexts, "analytics_report", "view")
    if widest is None or scope_rank(widest) < scope_rank(scope):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this scope",
        )

    if start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start must be on or before end",
        )

    acting_ctx = build_membership_context(db, actor.acting_membership)

    # Resolve the KPI to plot (same logic as the homepage chart).
    try:
        attribute = resolve_home_chart_kpi(
            db, function_id=acting_ctx.function_id, kpi_key=kpi
        )
    except AttributeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    available_kpis = [
        _kpi_ref(a)
        for a in list_home_chart_kpis(db, function_id=acting_ctx.function_id)
    ]

    if attribute is None:
        return DataChart(
            scope=scope,
            kpi=None,
            availableKpis=available_kpis,
            summaryRows=[],
            period="monthly",
            points=[],
        )

    # --- Summary rows --------------------------------------------------------
    summary_pairs: list[tuple[str, float]] = []
    if scope == "team":
        if acting_ctx.team_id is not None:
            summary_pairs = sum_by_team_member(
                db,
                attribute_id=attribute.id,
                team_id=acting_ctx.team_id,
                period_start=start,
                period_end=end,
            )
    elif scope == "function":
        if acting_ctx.function_id is not None:
            summary_pairs = sum_by_team_in_function(
                db,
                attribute_id=attribute.id,
                lc_id=acting_ctx.lc_id,
                function_id=acting_ctx.function_id,
                period_start=start,
                period_end=end,
            )
    elif scope == "lc":
        summary_pairs = [
            (row[1] or "No function", float(row[2]))
            for row in sum_by_function(
                db,
                lc_id=acting_ctx.lc_id,
                attribute_id=attribute.id,
                period_start=start,
                period_end=end,
            )
        ]
    else:  # all
        summary_pairs = sum_by_lc(
            db,
            attribute_id=attribute.id,
            period_start=start,
            period_end=end,
            filter_lc_id=lc_id,
        )

    summary_rows = [DataSummaryRow(label=label, value=value) for label, value in summary_pairs]

    # --- Monthly chart points ------------------------------------------------
    totals = monthly_totals(
        db,
        attribute_id=attribute.id,
        scope=scope,
        start=start,
        end=end,
        lc_id=acting_ctx.lc_id if scope != "all" else lc_id,
        function_id=acting_ctx.function_id,
        team_id=acting_ctx.team_id,
    )

    points: list[DataChartPoint] = []
    if totals:
        points = [
            DataChartPoint(month=month.strftime("%Y-%m"), value=totals.get(month, 0.0))
            for month in month_starts(start, end)
        ]

    return DataChart(
        scope=scope,
        kpi=_kpi_ref(attribute),
        availableKpis=available_kpis,
        summaryRows=summary_rows,
        period="monthly",
        points=points,
    )
