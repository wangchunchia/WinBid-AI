from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.bid_agent import (
    AgentChatRequest,
    AgentChatResponse,
    AgentPlanRequest,
    AgentPlanResponse,
    BidProjectAgentDecision,
    ChatSessionView,
    ProjectPlanView,
    SolveRequest,
    SolveResponse,
    SolveStepRequest,
    SolveStepResponse,
)
from app.services.bid_project_agent_service import bid_project_agent_service
from app.services.chat_agent_service import chat_agent_service
from app.services.plan_and_solve_service import plan_and_solve_service
from app.services.project_service import project_service


router = APIRouter()


@router.get("/{project_id}/agent/next-action", response_model=BidProjectAgentDecision)
def get_next_action(project_id: str, db: Session = Depends(get_db)) -> BidProjectAgentDecision:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return bid_project_agent_service.get_next_action(db, project_id)


@router.get("/{project_id}/agent/chat", response_model=ChatSessionView)
def get_chat_session(project_id: str, session_id: str | None = None, db: Session = Depends(get_db)) -> ChatSessionView:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return chat_agent_service.get_session_view(db, project_id, session_id)


@router.post("/{project_id}/agent/chat", response_model=AgentChatResponse)
def chat_with_agent(
    project_id: str,
    payload: AgentChatRequest,
    db: Session = Depends(get_db),
) -> AgentChatResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return chat_agent_service.chat(db, project_id, payload)


@router.post("/{project_id}/agent/plan", response_model=AgentPlanResponse)
def create_project_plan(
    project_id: str,
    payload: AgentPlanRequest,
    db: Session = Depends(get_db),
) -> AgentPlanResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return plan_and_solve_service.create_plan(db, project_id, payload)


@router.get("/{project_id}/agent/plan", response_model=ProjectPlanView)
def get_project_plan(project_id: str, db: Session = Depends(get_db)) -> ProjectPlanView:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    plan = plan_and_solve_service.get_plan_view(db, project_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Project plan not found")
    return plan


@router.post("/{project_id}/agent/solve-step", response_model=SolveStepResponse)
def solve_project_plan_step(
    project_id: str,
    payload: SolveStepRequest,
    db: Session = Depends(get_db),
) -> SolveStepResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return plan_and_solve_service.solve_step(db, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/agent/solve", response_model=SolveResponse)
def solve_project_plan(
    project_id: str,
    payload: SolveRequest,
    db: Session = Depends(get_db),
) -> SolveResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return plan_and_solve_service.solve(db, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
