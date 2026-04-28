from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.session import get_db
from app.schemas.bid_agent import (
    AgentChatRequest,
    AgentChatResponse,
    AgentMessageView,
    AgentPlanRequest,
    AgentPlanResponse,
    AgentStreamStartResponse,
    AgentTaskView,
    BidProjectAgentDecision,
    ChatSessionView,
    ProjectPlanView,
    SolveRequest,
    SolveResponse,
    SolveStepRequest,
    SolveStepResponse,
)
from app.services.agent_stream_service import agent_stream_service
from app.services.chat_agent_service import chat_agent_service
from app.services.multi_agent_service import multi_agent_service
from app.services.plan_and_solve_service import plan_and_solve_service
from app.services.project_service import project_service


router = APIRouter()


def _stream_url(project_id: str, stream_id: str) -> str:
    return f"/api/v1/projects/{project_id}/agent/stream/{stream_id}"


def _run_in_stream(project_id: str, stream_id: str, operation) -> None:
    db = SessionLocal()
    try:
        agent_stream_service.publish(stream_id, "run_started", {"project_id": project_id, "stream_id": stream_id})
        result = operation(db, lambda event, data: agent_stream_service.publish(stream_id, event, data))
        agent_stream_service.finish(stream_id, "result", result.model_dump(mode="json"))
    except Exception as exc:
        db.rollback()
        agent_stream_service.finish(stream_id, "run_error", {"message": str(exc)})
    finally:
        db.close()


@router.get("/{project_id}/agent/next-action", response_model=BidProjectAgentDecision)
def get_next_action(project_id: str, db: Session = Depends(get_db)) -> BidProjectAgentDecision:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return multi_agent_service.coordinate_next_action(db, project_id)


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
    return multi_agent_service.attach_trace_to_chat(db, chat_agent_service.chat(db, project_id, payload))


@router.post("/{project_id}/agent/chat/stream", response_model=AgentStreamStartResponse)
def start_chat_stream(
    project_id: str,
    payload: AgentChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> AgentStreamStartResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    stream = agent_stream_service.create_stream(project_id)
    background_tasks.add_task(
        _run_in_stream,
        project_id,
        stream.stream_id,
        lambda run_db, progress: multi_agent_service.attach_trace_to_chat(
            run_db,
            chat_agent_service.chat(run_db, project_id, payload, progress_callback=progress),
        ),
    )
    return AgentStreamStartResponse(project_id=project_id, stream_id=stream.stream_id, stream_url=_stream_url(project_id, stream.stream_id))


@router.post("/{project_id}/agent/plan", response_model=AgentPlanResponse)
def create_project_plan(
    project_id: str,
    payload: AgentPlanRequest,
    db: Session = Depends(get_db),
) -> AgentPlanResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return multi_agent_service.coordinate_plan(db, project_id, payload)


@router.post("/{project_id}/agent/plan/stream", response_model=AgentStreamStartResponse)
def start_project_plan_stream(
    project_id: str,
    payload: AgentPlanRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> AgentStreamStartResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    stream = agent_stream_service.create_stream(project_id)
    background_tasks.add_task(
        _run_in_stream,
        project_id,
        stream.stream_id,
        lambda run_db, progress: multi_agent_service.coordinate_plan(
            run_db,
            project_id,
            payload,
            progress_callback=progress,
        ),
    )
    return AgentStreamStartResponse(project_id=project_id, stream_id=stream.stream_id, stream_url=_stream_url(project_id, stream.stream_id))


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
        return multi_agent_service.coordinate_solve_step(db, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/agent/solve-step/stream", response_model=AgentStreamStartResponse)
def start_solve_project_plan_step_stream(
    project_id: str,
    payload: SolveStepRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> AgentStreamStartResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    stream = agent_stream_service.create_stream(project_id)
    background_tasks.add_task(
        _run_in_stream,
        project_id,
        stream.stream_id,
        lambda run_db, progress: multi_agent_service.coordinate_solve_step(
            run_db,
            project_id,
            payload,
            progress_callback=progress,
        ),
    )
    return AgentStreamStartResponse(project_id=project_id, stream_id=stream.stream_id, stream_url=_stream_url(project_id, stream.stream_id))


@router.post("/{project_id}/agent/solve", response_model=SolveResponse)
def solve_project_plan(
    project_id: str,
    payload: SolveRequest,
    db: Session = Depends(get_db),
) -> SolveResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return multi_agent_service.coordinate_solve(db, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/agent/solve/stream", response_model=AgentStreamStartResponse)
def start_solve_project_plan_stream(
    project_id: str,
    payload: SolveRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> AgentStreamStartResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    stream = agent_stream_service.create_stream(project_id)
    background_tasks.add_task(
        _run_in_stream,
        project_id,
        stream.stream_id,
        lambda run_db, progress: multi_agent_service.coordinate_solve(
            run_db,
            project_id,
            payload,
            progress_callback=progress,
        ),
    )
    return AgentStreamStartResponse(project_id=project_id, stream_id=stream.stream_id, stream_url=_stream_url(project_id, stream.stream_id))


@router.get("/{project_id}/agent/stream/{stream_id}")
async def stream_agent_run(project_id: str, stream_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    stream = agent_stream_service.get_stream(stream_id)
    if stream is None or stream.project_id != project_id:
        raise HTTPException(status_code=404, detail="Agent stream not found")
    return StreamingResponse(
        agent_stream_service.stream_events(stream_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{project_id}/agent/tasks", response_model=list[AgentTaskView])
def list_agent_tasks(
    project_id: str,
    session_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[AgentTaskView]:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return multi_agent_service.list_tasks(db, project_id, session_id)


@router.get("/{project_id}/agent/messages", response_model=list[AgentMessageView])
def list_agent_messages(
    project_id: str,
    session_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[AgentMessageView]:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return multi_agent_service.list_messages(db, project_id, session_id)
