import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from src.config import Config
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
cleanup_task: asyncio.Task | None = None


async def cleanup_expired_sessions() -> None:
    """Background task to remove expired sessions"""
    while True:
        await asyncio.sleep(Config.CLEANUP.INTERVAL_SECONDS)
        now = datetime.now(timezone.utc)
        expired = []
        for sid, session in sessions.items():
            age = (now - session.last_activity.replace(tzinfo=timezone.utc)).seconds
            if age > Config.SESSION.TTL_SECONDS:
                expired.append(sid)
        for sid in expired:
            del sessions[sid]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup/shutdown"""
    global start_time, cleanup_task
    start_time = time.time()

    # Start background cleanup
    cleanup_task = asyncio.create_task(cleanup_expired_sessions())

    yield

    # Cancel cleanup on shutdown
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Math Tutor Session Service", lifespan=lifespan)

# CORS for UI access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# === Session CRUD ===


@app.post("/sessions", response_model=SessionCreateResponse, status_code=201)
async def create_session(request: SessionCreateRequest) -> SessionCreateResponse:
    """Create a new session"""
    session_id = f"sess_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc)

    session = SessionData(
        session_id=session_id,
        user_id=request.user_id,
        original_query=request.initial_query,
        created_at=now,
        last_activity=now,
    )

    # Add initial message if query provided
    if request.initial_query:
        session.messages.append(
            ConversationMessage(
                role=MessageRole.USER,
                content=request.initial_query,
                timestamp=now,
            )
        )

    sessions[session_id] = session

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
    session_id: str, request: SessionUpdateRequest
) -> SessionGetResponse:
    """Update session state"""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Update fields if provided
    if request.phase is not None:
        session.phase = request.phase
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

    return await get_session(session_id)


@app.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str) -> None:
    """Delete a session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    del sessions[session_id]


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
    session_id: str, request: TutoringUpdateRequest
) -> TutoringState:
    """Update tutoring state"""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if request.question_id is not None:
        session.tutoring.question_id = request.question_id
    if request.current_node_id is not None:
        session.tutoring.current_node_id = request.current_node_id
    if request.add_to_path is not None:
        session.tutoring.traversal_path.append(request.add_to_path)
        session.tutoring.depth = len(session.tutoring.traversal_path)

    session.last_activity = datetime.now(timezone.utc)

    return session.tutoring


@app.post("/sessions/{session_id}/tutoring/reset", response_model=TutoringState)
async def reset_tutoring_state(session_id: str) -> TutoringState:
    """Reset tutoring state for a new question"""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.tutoring = TutoringState()
    session.phase = SessionPhase.INITIAL
    session.last_activity = datetime.now(timezone.utc)

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
    session_id: str, request: MessageAddRequest
) -> ConversationMessage:
    """Add a message to conversation history"""
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

    # Trim history if too long
    if len(session.messages) > Config.SESSION.MAX_HISTORY_LENGTH:
        session.messages = session.messages[-Config.SESSION.MAX_HISTORY_LENGTH :]

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
