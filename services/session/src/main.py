import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException
from fastapi import Request as FastAPIRequest
from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from src.config import Config
from src.logging_utils import (
    StructuredLogger,
    generate_request_id,
    get_logs_by_request_id,
)
from src.metrics import (
    http_request_duration_seconds,
    http_requests_total,
    session_duration_seconds,
    session_messages_total,
    session_phase_transitions,
    session_tutoring_depth,
    sessions_active_total,
    sessions_created_total,
    sessions_deleted_total,
    sessions_expired_total,
)
from src.models.schemas import (
    ConversationMessage,
    HealthResponse,
    MessageAddRequest,
    MessageHistoryResponse,
    MessageRole,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionData,
    SessionGetResponse,
    SessionPhase,
    SessionUpdateRequest,
    TutoringState,
    TutoringUpdateRequest,
)

# In-memory session storage
sessions: dict[str, SessionData] = {}
start_time: float = 0
cleanup_task: Optional[asyncio.Task] = None
logger = StructuredLogger("session")


async def cleanup_expired_sessions() -> None:
    """Background task to remove expired sessions"""
    while True:
        await asyncio.sleep(Config.CLEANUP.INTERVAL_SECONDS)
        now = datetime.now(timezone.utc)
        expired = []

        for sid, session in sessions.items():
            last_activity = session.last_activity
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)

            age = (now - last_activity).total_seconds()
            if age > Config.SESSION.TTL_SECONDS:
                expired.append(sid)

        for sid in expired:
            session = sessions.pop(sid, None)
            if session:
                sessions_expired_total.inc()
                sessions_active_total.dec()

                if session.tutoring.depth > 0:
                    session_tutoring_depth.observe(session.tutoring.depth)

                created = session.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                duration = (now - created).total_seconds()
                session_duration_seconds.observe(duration)

        if expired:
            logger.info(
                "Cleaned up expired sessions",
                context={"count": len(expired), "remaining": len(sessions)},
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup/shutdown"""
    global start_time, cleanup_task
    start_time = time.time()

    logger.info(
        "Starting session service",
        context={
            "ttl_seconds": Config.SESSION.TTL_SECONDS,
            "cleanup_interval": Config.CLEANUP.INTERVAL_SECONDS,
        },
    )

    cleanup_task = asyncio.create_task(cleanup_expired_sessions())

    yield

    logger.info("Shutting down session service")
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Math Tutor Session Service", lifespan=lifespan)


@app.middleware("http")
async def logging_and_metrics_middleware(request: FastAPIRequest, call_next):
    """Middleware to log all HTTP requests and record metrics"""
    incoming_request_id = request.headers.get("X-Request-ID")
    request_id = incoming_request_id if incoming_request_id else generate_request_id()
    start = time.time()

    is_metrics_endpoint = request.url.path == "/metrics"

    if not is_metrics_endpoint:
        logger.info(
            "Incoming request",
            context={
                "endpoint": request.url.path,
                "method": request.method,
                "client": request.client.host if request.client else "unknown",
            },
            request_id=request_id,
        )

    request.state.request_id = request_id

    try:
        response = await call_next(request)
        duration = time.time() - start

        if not is_metrics_endpoint:
            http_requests_total.labels(
                service="session",
                endpoint=request.url.path,
                method=request.method,
                status=response.status_code,
            ).inc()

            http_request_duration_seconds.labels(
                service="session",
                endpoint=request.url.path,
                method=request.method,
            ).observe(duration)

        if not (is_metrics_endpoint and response.status_code == 200):
            logger.info(
                "Request completed",
                context={
                    "endpoint": request.url.path,
                    "method": request.method,
                    "status_code": response.status_code,
                    "duration_seconds": round(duration, 3),
                },
                request_id=request_id,
            )

        response.headers["X-Request-ID"] = request_id
        return response

    except Exception as e:
        duration = time.time() - start

        if not is_metrics_endpoint:
            http_requests_total.labels(
                service="session",
                endpoint=request.url.path,
                method=request.method,
                status=500,
            ).inc()

            http_request_duration_seconds.labels(
                service="session",
                endpoint=request.url.path,
                method=request.method,
            ).observe(duration)

        logger.error(
            "Request failed",
            context={
                "endpoint": request.url.path,
                "method": request.method,
                "error": str(e),
                "duration_seconds": round(duration, 3),
            },
            request_id=request_id,
        )
        raise


# === Health Check ===


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        service="session",
        active_sessions=len(sessions),
        uptime_seconds=time.time() - start_time,
    )


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/logs/{request_id}")
async def get_logs(request_id: str):
    """Get logs for a specific request ID"""
    logs = get_logs_by_request_id(request_id)
    return {"request_id": request_id, "logs": logs, "count": len(logs)}


# === Session CRUD ===


@app.post("/sessions", response_model=SessionCreateResponse, status_code=201)
async def create_session(
    request: SessionCreateRequest, fastapi_request: FastAPIRequest
) -> SessionCreateResponse:
    """Create a new session"""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    session_id = f"sess_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc)

    session = SessionData(
        session_id=session_id,
        user_id=request.user_id,
        original_query=request.initial_query,
        created_at=now,
        last_activity=now,
    )

    if request.initial_query:
        session.messages.append(
            ConversationMessage(
                role=MessageRole.USER,
                content=request.initial_query,
                timestamp=now,
            )
        )
        session_messages_total.labels(role="user").inc()

    sessions[session_id] = session
    sessions_created_total.inc()
    sessions_active_total.inc()

    logger.info(
        "Session created",
        context={
            "session_id": session_id,
            "user_id": request.user_id,
            "has_initial_query": bool(request.initial_query),
        },
        request_id=request_id,
    )

    return SessionCreateResponse(
        session_id=session_id,
        created_at=now,
    )


@app.get("/sessions/{session_id}", response_model=SessionGetResponse)
async def get_session(session_id: str) -> SessionGetResponse:
    """Get session by ID"""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionGetResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        phase=session.phase,
        original_query=session.original_query,
        reformulated_query=session.reformulated_query,
        identified_lesson=session.identified_lesson,
        retrieved_answer=session.retrieved_answer,
        retrieval_score=session.retrieval_score,
        retrieval_source=session.retrieval_source,
        tutoring=session.tutoring,
        message_count=len(session.messages),
        created_at=session.created_at,
        last_activity=session.last_activity,
    )


@app.patch("/sessions/{session_id}", response_model=SessionGetResponse)
async def update_session(
    session_id: str, request: SessionUpdateRequest, fastapi_request: FastAPIRequest
) -> SessionGetResponse:
    """Update session state"""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    old_phase = session.phase

    if request.phase is not None:
        session.phase = request.phase
        if old_phase != request.phase:
            session_phase_transitions.labels(
                from_phase=old_phase.value, to_phase=request.phase.value
            ).inc()

    if request.original_query is not None:
        session.original_query = request.original_query
    if request.reformulated_query is not None:
        session.reformulated_query = request.reformulated_query
    if request.identified_lesson is not None:
        session.identified_lesson = request.identified_lesson
    if request.retrieved_answer is not None:
        session.retrieved_answer = request.retrieved_answer
    if request.retrieval_score is not None:
        session.retrieval_score = request.retrieval_score
    if request.retrieval_source is not None:
        session.retrieval_source = request.retrieval_source

    session.last_activity = datetime.now(timezone.utc)

    logger.info(
        "Session updated",
        context={
            "session_id": session_id,
            "phase": session.phase.value,
            "phase_changed": old_phase != session.phase,
        },
        request_id=request_id,
    )

    return await get_session(session_id)


@app.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, fastapi_request: FastAPIRequest) -> None:
    """Delete a session"""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions.pop(session_id)
    sessions_deleted_total.inc()
    sessions_active_total.dec()

    if session.tutoring.depth > 0:
        session_tutoring_depth.observe(session.tutoring.depth)

    logger.info(
        "Session deleted",
        context={"session_id": session_id, "phase": session.phase.value},
        request_id=request_id,
    )


# === Tutoring State ===


@app.get("/sessions/{session_id}/tutoring", response_model=TutoringState)
async def get_tutoring_state(session_id: str) -> TutoringState:
    """Get tutoring state for a session"""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.tutoring


@app.patch("/sessions/{session_id}/tutoring", response_model=TutoringState)
async def update_tutoring_state(
    session_id: str, request: TutoringUpdateRequest, fastapi_request: FastAPIRequest
) -> TutoringState:
    """Update tutoring state"""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if request.question_id is not None:
        session.tutoring.question_id = request.question_id
    if request.current_node_id is not None:
        session.tutoring.current_node_id = request.current_node_id
    if request.depth is not None:
        session.tutoring.depth = request.depth
    if request.add_to_path is not None:
        session.tutoring.traversal_path.append(request.add_to_path)
        session.tutoring.depth = len(session.tutoring.traversal_path)
    if request.is_new_branch is not None:
        session.tutoring.is_new_branch = request.is_new_branch

    session.last_activity = datetime.now(timezone.utc)

    logger.info(
        "Tutoring state updated",
        context={
            "session_id": session_id,
            "question_id": session.tutoring.question_id,
            "depth": session.tutoring.depth,
        },
        request_id=request_id,
    )

    return session.tutoring


@app.post("/sessions/{session_id}/tutoring/reset", response_model=TutoringState)
async def reset_tutoring_state(
    session_id: str, fastapi_request: FastAPIRequest
) -> TutoringState:
    """Reset tutoring state for a new question"""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.tutoring.depth > 0:
        session_tutoring_depth.observe(session.tutoring.depth)

    session.tutoring = TutoringState()
    session.phase = SessionPhase.INITIAL
    session.last_activity = datetime.now(timezone.utc)

    logger.info(
        "Tutoring state reset",
        context={"session_id": session_id},
        request_id=request_id,
    )

    return session.tutoring


# === Conversation History ===


@app.get("/sessions/{session_id}/messages", response_model=MessageHistoryResponse)
async def get_messages(
    session_id: str, limit: int = 50, offset: int = 0
) -> MessageHistoryResponse:
    """Get conversation history"""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = session.messages[offset : offset + limit]

    return MessageHistoryResponse(
        session_id=session_id,
        messages=messages,
        total_count=len(session.messages),
    )


@app.post("/sessions/{session_id}/messages", response_model=ConversationMessage)
async def add_message(
    session_id: str, request: MessageAddRequest, fastapi_request: FastAPIRequest
) -> ConversationMessage:
    """Add a message to conversation history"""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    message = ConversationMessage(
        role=request.role,
        content=request.content,
        timestamp=datetime.now(timezone.utc),
        metadata=request.metadata,
    )

    session.messages.append(message)
    session.last_activity = datetime.now(timezone.utc)

    session_messages_total.labels(role=request.role.value).inc()

    if len(session.messages) > Config.SESSION.MAX_HISTORY_LENGTH:
        session.messages = session.messages[-Config.SESSION.MAX_HISTORY_LENGTH :]

    logger.info(
        "Message added",
        context={
            "session_id": session_id,
            "role": request.role.value,
            "message_length": len(request.content),
            "total_messages": len(session.messages),
        },
        request_id=request_id,
    )

    return message


@app.get("/sessions/{session_id}/context")
async def get_context_for_llm(session_id: str, max_messages: int = 10) -> dict:
    """Get condensed context for LLM calls"""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    recent_messages = session.messages[-max_messages:]

    return {
        "session_id": session_id,
        "phase": session.phase.value,
        "original_query": session.original_query,
        "reformulated_query": session.reformulated_query,
        "lesson": session.identified_lesson,
        "retrieved_answer": session.retrieved_answer,
        "tutoring_depth": session.tutoring.depth,
        "current_node_id": session.tutoring.current_node_id,
        "conversation": [
            {"role": m.role.value, "content": m.content} for m in recent_messages
        ],
    }
