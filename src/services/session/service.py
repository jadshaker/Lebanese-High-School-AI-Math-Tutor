import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from src.config import Config
from src.logging_utils import StructuredLogger
from src.metrics import (
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
    MessageRole,
    SessionData,
    SessionPhase,
    TutoringState,
)

# In-memory session storage
sessions: dict[str, SessionData] = {}
start_time: float = 0
cleanup_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
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
            session = sessions.pop(sid)
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


def start_cleanup() -> asyncio.Task:  # type: ignore[type-arg]
    """Start the background cleanup task. Call from lifespan."""
    global start_time, cleanup_task
    start_time = time.time()
    cleanup_task = asyncio.create_task(cleanup_expired_sessions())
    return cleanup_task


def stop_cleanup() -> None:
    """Stop the background cleanup task. Call from lifespan."""
    global cleanup_task
    if cleanup_task:
        cleanup_task.cancel()


# === Session Operations ===


def create_session(
    user_id: Optional[str] = None,
    initial_query: Optional[str] = None,
    request_id: str = "",
) -> SessionData:
    """Create a new session."""
    session_id = f"sess_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc)

    session = SessionData(
        session_id=session_id,
        user_id=user_id,
        original_query=initial_query,
        created_at=now,
        last_activity=now,
    )

    if initial_query:
        session.messages.append(
            ConversationMessage(
                role=MessageRole.USER,
                content=initial_query,
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
            "user_id": user_id,
            "has_initial_query": bool(initial_query),
        },
        request_id=request_id,
    )

    return session


def get_session(session_id: str) -> Optional[SessionData]:
    """Get session by ID."""
    return sessions.get(session_id)


def update_session(
    session_id: str,
    phase: Optional[SessionPhase] = None,
    original_query: Optional[str] = None,
    reformulated_query: Optional[str] = None,
    identified_lesson: Optional[str] = None,
    retrieved_answer: Optional[str] = None,
    retrieval_score: Optional[float] = None,
    retrieval_source: Optional[str] = None,
    request_id: str = "",
) -> Optional[SessionData]:
    """Update session state."""
    session = sessions.get(session_id)
    if not session:
        return None

    old_phase = session.phase

    if phase is not None:
        session.phase = phase
        if old_phase != phase:
            session_phase_transitions.labels(
                from_phase=old_phase.value, to_phase=phase.value
            ).inc()

    if original_query is not None:
        session.original_query = original_query
    if reformulated_query is not None:
        session.reformulated_query = reformulated_query
    if identified_lesson is not None:
        session.identified_lesson = identified_lesson
    if retrieved_answer is not None:
        session.retrieved_answer = retrieved_answer
    if retrieval_score is not None:
        session.retrieval_score = retrieval_score
    if retrieval_source is not None:
        session.retrieval_source = retrieval_source

    session.last_activity = datetime.now(timezone.utc)
    return session


def delete_session(session_id: str, request_id: str = "") -> bool:
    """Delete a session."""
    if session_id not in sessions:
        return False

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
    return True


# === Tutoring State ===


def get_tutoring_state(session_id: str) -> Optional[TutoringState]:
    """Get tutoring state for a session."""
    session = sessions.get(session_id)
    if not session:
        return None
    return session.tutoring


def update_tutoring_state(
    session_id: str,
    question_id: Optional[str] = None,
    current_node_id: Optional[str] = None,
    depth: Optional[int] = None,
    add_to_path: Optional[str] = None,
    is_new_branch: Optional[bool] = None,
    request_id: str = "",
) -> Optional[TutoringState]:
    """Update tutoring state."""
    session = sessions.get(session_id)
    if not session:
        return None

    if question_id is not None:
        session.tutoring.question_id = question_id
    if current_node_id is not None:
        session.tutoring.current_node_id = current_node_id
    if depth is not None:
        session.tutoring.depth = depth
    if add_to_path is not None:
        session.tutoring.traversal_path.append(add_to_path)
        session.tutoring.depth = len(session.tutoring.traversal_path)
    if is_new_branch is not None:
        session.tutoring.is_new_branch = is_new_branch

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


def reset_tutoring_state(
    session_id: str, request_id: str = ""
) -> Optional[TutoringState]:
    """Reset tutoring state for a new question."""
    session = sessions.get(session_id)
    if not session:
        return None

    if session.tutoring.depth > 0:
        session_tutoring_depth.observe(session.tutoring.depth)

    session.tutoring = TutoringState()
    session.phase = SessionPhase.INITIAL
    session.last_activity = datetime.now(timezone.utc)

    return session.tutoring


# === Messages ===


def add_message(
    session_id: str,
    role: MessageRole,
    content: str,
    metadata: Optional[dict] = None,
    request_id: str = "",
) -> Optional[ConversationMessage]:
    """Add a message to conversation history."""
    session = sessions.get(session_id)
    if not session:
        return None

    message = ConversationMessage(
        role=role,
        content=content,
        timestamp=datetime.now(timezone.utc),
        metadata=metadata,
    )

    session.messages.append(message)
    session.last_activity = datetime.now(timezone.utc)
    session_messages_total.labels(role=role.value).inc()

    if len(session.messages) > Config.SESSION.MAX_HISTORY_LENGTH:
        session.messages = session.messages[-Config.SESSION.MAX_HISTORY_LENGTH :]

    return message


def get_messages(
    session_id: str, limit: int = 50, offset: int = 0
) -> Optional[list[ConversationMessage]]:
    """Get conversation history."""
    session = sessions.get(session_id)
    if not session:
        return None
    return session.messages[offset : offset + limit]


def get_context_for_llm(session_id: str, max_messages: int = 10) -> Optional[dict]:
    """Get condensed context for LLM calls."""
    session = sessions.get(session_id)
    if not session:
        return None

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


def get_active_session_count() -> int:
    """Get count of active sessions."""
    return len(sessions)


def get_uptime() -> float:
    """Get service uptime in seconds."""
    return time.time() - start_time
