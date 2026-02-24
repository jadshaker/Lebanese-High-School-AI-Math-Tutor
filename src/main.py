import asyncio
import hashlib
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi import Request as FastAPIRequest
from qdrant_client import AsyncQdrantClient

from src.config import Config
from src.logging_utils import StructuredLogger, generate_request_id
from src.metrics import (
    gateway_errors_total,
    gateway_filtered_requests_total,
    gateway_tutoring_followups_total,
    http_request_duration_seconds,
    http_requests_total,
    service_health_status,
)
from src.models.schemas import (
    ChatCompletionChoice,
    ChatMessage,
    ChatCompletionMessageResponse,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Model,
    ModelListResponse,
    SessionPhase,
    TutoringRequest,
    TutoringResponse,
)
from src.orchestrators.answer_retrieval.service import retrieve_answer
from src.orchestrators.data_processing.service import process_user_input
from src.orchestrators.tutoring.service import handle_tutoring_interaction
from src.routes.admin import router as admin_router
from src.services.session import service as session_service
from src.services.vector_cache import service as vector_cache

logger = StructuredLogger("gateway")

# Open WebUI sends automated requests (title gen, tag gen, follow-up suggestions)
# through /v1/chat/completions. These must not enter the pipeline or pollute the cache.
_OPENWEBUI_JUNK_PREFIXES = (
    "### Task:\nSuggest",
    "### Task:\nGenerate a concise",
    "### Task:\nGenerate 1-3",
    "### Task: Suggest",
    "### Task: Generate a concise",
    "### Task: Generate 1-3",
)

_GREETING_WORDS = frozenset(
    {
        "hello",
        "hi",
        "hey",
        "good morning",
        "good evening",
        "good afternoon",
        "thanks",
        "thank you",
        "bye",
        "goodbye",
        "merci",
        "bonjour",
        "bonsoir",
        "salut",
    }
)


def _is_openwebui_system_request(user_message: str) -> bool:
    """Detect Open WebUI automated system requests."""
    return any(user_message.strip().startswith(p) for p in _OPENWEBUI_JUNK_PREFIXES)


def _is_simple_greeting(message: str) -> bool:
    """Detect simple greetings that don't need the full pipeline."""
    normalized = message.strip().lower().rstrip("!.,?")
    return normalized in _GREETING_WORDS


# Maps conversation key (hash of first user message) → session_id.
# Entries are cleaned up when the underlying session expires (see _cleanup_stale_conversations).
_conversation_sessions: dict[str, str] = {}


def _cleanup_stale_conversations() -> None:
    """Remove conversation keys whose sessions no longer exist."""
    stale = [
        key
        for key, sid in _conversation_sessions.items()
        if session_service.get_session(sid) is None
    ]
    for key in stale:
        del _conversation_sessions[key]
    if stale:
        logger.info(
            "Cleaned up stale conversation keys",
            context={"count": len(stale), "remaining": len(_conversation_sessions)},
        )


def _derive_conversation_key(messages: list[ChatMessage]) -> str:
    """Derive a stable key for this conversation from its first user message."""
    first_user_msg = next(
        (msg.content for msg in messages if msg.role == "user"), ""
    )
    return hashlib.sha256(first_user_msg.encode()).hexdigest()[:16]


def _count_user_messages(messages: list[ChatMessage]) -> int:
    """Count user messages in the conversation."""
    return sum(1 for msg in messages if msg.role == "user")


def _make_short_circuit_response(
    content: str, model: str
) -> ChatCompletionResponse:
    """Build a minimal ChatCompletionResponse without running the pipeline."""
    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
        created=int(time.time()),
        model=model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatCompletionMessageResponse(content=content),
                finish_reason="stop",
            )
        ],
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup, cleanup on shutdown."""
    logger.info("Starting app...")

    # Initialize Qdrant
    qdrant_client = AsyncQdrantClient(
        host=Config.QDRANT.HOST,
        port=Config.QDRANT.PORT,
        grpc_port=Config.QDRANT.GRPC_PORT,
        prefer_grpc=True,
    )
    await vector_cache.initialize(qdrant_client)

    # Start session cleanup
    session_service.start_cleanup()

    # Periodically clean up stale conversation keys
    async def _periodic_conversation_cleanup() -> None:
        while True:
            await asyncio.sleep(Config.CLEANUP.INTERVAL_SECONDS)
            _cleanup_stale_conversations()

    conversation_cleanup_task = asyncio.create_task(_periodic_conversation_cleanup())

    service_health_status.labels(service="app").set(2)
    logger.info("App ready")

    yield

    conversation_cleanup_task.cancel()

    # Shutdown
    logger.info("Shutting down...")
    session_service.stop_cleanup()
    await qdrant_client.close()
    service_health_status.labels(service="app").set(0)
    logger.info("App stopped")


app = FastAPI(title="Math Tutor API", lifespan=lifespan)

# Include admin routes
app.include_router(admin_router)


@app.middleware("http")
async def logging_and_metrics_middleware(request: FastAPIRequest, call_next):
    """Log requests and record HTTP metrics."""
    request_id = generate_request_id()
    start_time = time.time()

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
        duration = time.time() - start_time

        if not is_metrics_endpoint:
            http_requests_total.labels(
                service="app",
                endpoint=request.url.path,
                method=request.method,
                status=response.status_code,
            ).inc()

            http_request_duration_seconds.labels(
                service="app",
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
        duration = time.time() - start_time

        if not is_metrics_endpoint:
            http_requests_total.labels(
                service="app",
                endpoint=request.url.path,
                method=request.method,
                status=500,
            ).inc()

            http_request_duration_seconds.labels(
                service="app",
                endpoint=request.url.path,
                method=request.method,
            ).observe(duration)

            gateway_errors_total.labels(error_type=type(e).__name__).inc()

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


@app.get("/v1/models", response_model=ModelListResponse)
async def list_models():
    """OpenAI-compatible models list endpoint."""
    return ModelListResponse(
        data=[
            Model(
                id="math-tutor",
                created=int(time.time()),
                owned_by="lebanese-high-school-math-tutor",
            )
        ]
    )


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest, fastapi_request: FastAPIRequest
):
    """OpenAI-compatible chat completions endpoint — orchestrates the complete pipeline."""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    try:
        user_message = next(
            (msg.content for msg in reversed(request.messages) if msg.role == "user"),
            None,
        )

        if not user_message:
            logger.warning(
                "No user message in request",
                context={"messages_count": len(request.messages)},
                request_id=request_id,
            )
            raise HTTPException(
                status_code=400,
                detail="No user message found in request",
            )

        # ===== FILTER: Open WebUI system requests =====
        if _is_openwebui_system_request(user_message):
            logger.info(
                "Filtered Open WebUI system request",
                context={"message_prefix": user_message[:60]},
                request_id=request_id,
            )
            gateway_filtered_requests_total.labels(reason="openwebui_system").inc()
            return _make_short_circuit_response(
                "I'm a math tutor for Lebanese high school students. Ask me a math question!",
                request.model,
            )

        # ===== FILTER: Simple greetings =====
        if _is_simple_greeting(user_message):
            logger.info(
                "Handled greeting",
                context={"message": user_message[:60]},
                request_id=request_id,
            )
            gateway_filtered_requests_total.labels(reason="greeting").inc()
            return _make_short_circuit_response(
                "Hello! I'm your math tutor for the Lebanese high school curriculum. "
                "I can help with algebra, geometry, calculus, trigonometry, and more. "
                "What would you like to work on?",
                request.model,
            )

        # ===== CONVERSATION HISTORY =====
        # Extract prior user/assistant messages for reformulator context
        conversation_history = [
            msg
            for msg in request.messages
            if msg.role in ("user", "assistant")
        ]
        # Remove the last entry if it's the current user message
        if (
            conversation_history
            and conversation_history[-1].content == user_message
        ):
            conversation_history = conversation_history[:-1]
        # Pass None instead of empty list for cleaner downstream checks
        if not conversation_history:
            conversation_history = None

        # ===== ROUTING: First question vs tutoring follow-up =====
        conversation_key = _derive_conversation_key(request.messages)
        user_msg_count = _count_user_messages(request.messages)
        is_follow_up = (
            user_msg_count > 1
            and conversation_key in _conversation_sessions
        )

        if is_follow_up:
            # ===== TUTORING FOLLOW-UP =====
            session_id = _conversation_sessions[conversation_key]
            session = session_service.get_session(session_id)

            if session and session.tutoring.question_id:
                logger.info(
                    "Routing to tutoring follow-up",
                    context={
                        "session_id": session_id,
                        "question_id": session.tutoring.question_id,
                        "user_message": user_message[:100],
                        "depth": session.tutoring.depth,
                    },
                    request_id=request_id,
                )
                gateway_tutoring_followups_total.inc()

                result = await handle_tutoring_interaction(
                    session_id=session_id,
                    original_question=session.original_query or "",
                    original_answer=session.retrieved_answer or "",
                    question_id=session.tutoring.question_id,
                    user_response=user_message,
                    request_id=request_id,
                )

                answer = result["tutor_message"]

                logger.info(
                    "Tutoring follow-up completed",
                    context={
                        "session_id": session_id,
                        "intent": result["intent"],
                        "is_complete": result["is_complete"],
                        "cache_hit": result["cache_hit"],
                    },
                    request_id=request_id,
                )

                return ChatCompletionResponse(
                    id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
                    created=int(time.time()),
                    model=request.model,
                    choices=[
                        ChatCompletionChoice(
                            index=0,
                            message=ChatCompletionMessageResponse(
                                content=answer
                            ),
                            finish_reason="stop",
                        )
                    ],
                )

            # Session expired or missing question_id — fall through to Q&A
            logger.info(
                "Session expired or incomplete, falling through to Q&A",
                context={"session_id": session_id},
                request_id=request_id,
            )
            del _conversation_sessions[conversation_key]

        # ===== FIRST QUESTION: Full Q&A Pipeline =====
        logger.info(
            "Starting chat completion pipeline",
            context={
                "model": request.model,
                "user_message": user_message[:100],
                "message_count": len(request.messages),
            },
            request_id=request_id,
        )

        pipeline_start = time.time()

        # ===== DATA PROCESSING =====
        processing_result = await process_user_input(
            user_message, request_id, conversation_history=conversation_history
        )
        reformulated_query = processing_result["reformulated_query"]

        # ===== FILTER: Non-math content =====
        if not processing_result.get("is_math_related", True):
            logger.info(
                "Filtered non-math query",
                context={"user_message": user_message[:100]},
                request_id=request_id,
            )
            gateway_filtered_requests_total.labels(reason="non_math").inc()
            return _make_short_circuit_response(
                "I'm a math tutor specialized in the Lebanese high school curriculum. "
                "I can help with algebra, geometry, calculus, trigonometry, and other math topics. "
                "Please ask me a math question!",
                request.model,
            )

        # ===== ANSWER RETRIEVAL =====
        retrieval_result = await retrieve_answer(
            reformulated_query, request_id, original_query=user_message
        )
        answer = retrieval_result["answer"]
        source = retrieval_result["source"]
        question_id = retrieval_result.get("question_id", "")

        # ===== CREATE SESSION for tutoring follow-ups =====
        # Only create a session (and enable tutoring routing) when we have a
        # valid question_id.  Without one the tutoring system cannot function
        # (it needs the ID to search/store graph nodes in Qdrant).
        if question_id:
            session = session_service.create_session(
                initial_query=user_message, request_id=request_id
            )
            session_service.update_session(
                session.session_id,
                phase=SessionPhase.TUTORING,
                retrieved_answer=answer,
                retrieval_source=source,
                request_id=request_id,
            )
            session_service.update_tutoring_state(
                session.session_id,
                question_id=question_id,
                request_id=request_id,
            )
            _conversation_sessions[conversation_key] = session.session_id
        else:
            logger.warning(
                "No question_id from retrieval — tutoring follow-ups disabled for this conversation",
                request_id=request_id,
            )

        logger.info(
            "Session created for conversation",
            context={
                "session_id": session.session_id,
                "conversation_key": conversation_key,
                "question_id": question_id,
            },
            request_id=request_id,
        )

        # ===== LATENCY SUMMARY =====
        total_duration = round(time.time() - pipeline_start, 3)
        latency = {
            **processing_result.get("latency", {}),
            **retrieval_result.get("latency", {}),
            "total": total_duration,
        }

        breakdown = " | ".join(f"{k}: {v}s" for k, v in latency.items())
        logger.info(
            f"Latency breakdown: {breakdown}",
            context={"latency": latency},
            request_id=request_id,
        )

        logger.info(
            "Chat completion pipeline successful",
            context={
                "total_answer_length": len(answer),
                "source": source,
                "total_latency_s": total_duration,
            },
            request_id=request_id,
        )

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            created=int(time.time()),
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatCompletionMessageResponse(content=answer),
                    finish_reason="stop",
                )
            ],
        )

    except HTTPException:
        raise
    except KeyError as e:
        logger.error(
            "Unexpected response format",
            context={"missing_key": str(e)},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected response format from service: missing key {str(e)}",
        )
    except Exception as e:
        logger.error(
            "Internal error in chat completion",
            context={"error": str(e), "error_type": type(e).__name__},
            request_id=request_id,
        )
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.post("/tutoring", response_model=TutoringResponse)
async def tutoring_interaction(
    request: TutoringRequest, fastapi_request: FastAPIRequest
):
    """Handle tutoring interaction with the student."""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    try:
        logger.info(
            "Starting tutoring interaction",
            context={
                "session_id": request.session_id,
                "user_response": request.user_response[:100],
                "has_question_id": bool(request.question_id),
            },
            request_id=request_id,
        )

        # Get context from request or session
        original_question = request.original_question
        original_answer = request.original_answer or ""
        question_id = request.question_id or ""

        # If not provided, try to get from session
        if not original_question or not question_id:
            session_data = session_service.get_session(request.session_id)
            if session_data:
                if not original_question:
                    original_question = (
                        session_data.original_query or "the math problem being tutored"
                    )
                if not question_id:
                    question_id = session_data.tutoring.question_id or ""
                if not original_answer:
                    original_answer = session_data.retrieved_answer or ""

            if not original_question:
                original_question = "the math problem being tutored"

        result = await handle_tutoring_interaction(
            session_id=request.session_id,
            original_question=original_question,
            original_answer=original_answer,
            question_id=question_id,
            user_response=request.user_response,
            request_id=request_id,
        )

        logger.info(
            "Tutoring interaction completed",
            context={
                "session_id": request.session_id,
                "is_complete": result["is_complete"],
                "intent": result["intent"],
                "cache_hit": result["cache_hit"],
            },
            request_id=request_id,
        )

        return TutoringResponse(
            session_id=request.session_id,
            tutor_message=result["tutor_message"],
            is_complete=result["is_complete"],
            next_prompt=result["next_prompt"],
            intent=result["intent"],
            cache_hit=result["cache_hit"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Internal error in tutoring interaction",
            context={"error": str(e), "error_type": type(e).__name__},
            request_id=request_id,
        )
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
