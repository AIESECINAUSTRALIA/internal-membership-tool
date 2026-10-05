"""Membership endpoints for Spec §2A.5."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.repositories import membership as repo
from app.schemas.membership import (
    ActionResult,
    AddMemberInput,
    AddMemberResult,
    ExtendTermInput,
    MemberQuery,
    MembershipDetail,
    MemberSummaryRow,
    MoveToTeamInput,
    Page,
)

router = APIRouter(prefix="/members", tags=["members"])


@router.post("/summary", response_model=Page[MemberSummaryRow])
def list_members(
    query: MemberQuery,
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> Page[MemberSummaryRow]:
    """Summary list of current members matching Spec §2A.5 (listMembers)."""
    actor_contexts = [
        repo.build_membership_context(db, m) for m in actor.active_memberships
    ]

    filter_lc_id = int(query.lcId) if query.lcId and query.lcId.isdigit() else None

    result = repo.list_members_summary(
        db,
        actor_contexts,
        search=query.search,
        sort_field=query.sortField,
        sort_direction=query.sortDirection,
        page=query.page,
        page_size=query.pageSize,
        filter_lc_id=filter_lc_id,
    )

    return Page[MemberSummaryRow](
        items=result["rows"],
        total=result["total"],
        page=query.page,
        pageSize=query.pageSize,
    )


@router.post("", response_model=AddMemberResult)
def add_member(
    payload: AddMemberInput,
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> AddMemberResult:
    """Add a member per Spec §2A.5, §3.4, §3.6, and §5.1 (addMember)."""
    actor_contexts = [
        repo.build_membership_context(db, m) for m in actor.active_memberships
    ]

    res = repo.add_member(
        db,
        actor_contexts,
        email=payload.email,
        lc_id=payload.lcId,
        position_key=payload.positionKey,
        start_date=payload.startDate,
        end_date=payload.endDate,
        first_name=payload.firstName,
        last_name=payload.lastName,
        function_key=payload.functionKey,
        team_id=payload.teamId,
        term_id=payload.termId,
        confirmed_existing=payload.confirmedExisting,
    )

    if res["status"] == "created":
        db.commit()

    return AddMemberResult(status=res["status"], message=res.get("message"))


@router.get("/{membership_id}", response_model=MembershipDetail)
def get_membership_detail(
    membership_id: int,
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> MembershipDetail:
    """Fetch detail payload for the Manage Membership dialog per Spec §2A.5."""
    actor_contexts = [
        repo.build_membership_context(db, m) for m in actor.active_memberships
    ]

    detail = repo.get_membership_detail(db, actor_contexts, membership_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found"
        )

    return MembershipDetail(**detail)


@router.post("/{membership_id}/extend-term", response_model=ActionResult)
def extend_term(
    membership_id: int,
    payload: ExtendTermInput,
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> ActionResult:
    """Extend term for membership per Spec §2A.5 and §3.4 (extendTerm)."""
    actor_contexts = [
        repo.build_membership_context(db, m) for m in actor.active_memberships
    ]

    res = repo.extend_term(db, actor_contexts, membership_id, payload.newEndDate)
    if res["status"] == "ok":
        db.commit()

    return ActionResult(status=res["status"], message=res.get("message"))


@router.post("/{membership_id}/move-to-team", response_model=ActionResult)
def move_to_team(
    membership_id: int,
    payload: MoveToTeamInput,
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> ActionResult:
    """Move member to another team per Spec §2A.5 and §5.1 (moveToTeam)."""
    actor_contexts = [
        repo.build_membership_context(db, m) for m in actor.active_memberships
    ]

    res = repo.move_to_team(db, actor_contexts, membership_id, payload.teamId)
    if res["status"] == "ok":
        db.commit()

    return ActionResult(status=res["status"], message=res.get("message"))
