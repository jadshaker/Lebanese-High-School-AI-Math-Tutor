import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException
from fastapi import Request as FastAPIRequest
from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from qdrant_client import AsyncQdrantClient
from src.config import Config
from src.logging_utils import (
    StructuredLogger,
    generate_request_id,
    get_logs_by_request_id,
)
from src.metrics import (
    cache_interactions_total,
    cache_questions_total,
    cache_saves_total,
    cache_search_hits_total,
    cache_search_misses_total,
    cache_searches_total,
    cache_similarity_score,
    feedback_negative_total,
    feedback_positive_total,
    http_request_duration_seconds,
    http_requests_total,
    interaction_cache_hits_total,
    interaction_cache_misses_total,
    interaction_depth_histogram,
)
from src.models.schemas import (
    BulkCreateRequest,
    BulkCreateResponse,
    ConversationPathNode,
    ConversationPathResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    InteractionCreate,
    InteractionResponse,
    QuestionCreate,
    QuestionResponse,
    QuestionUpdate,
    SearchChildrenRequest,
    SearchChildrenResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SourceType,
)
from src.repository import QdrantRepository

repo: Optional[QdrantRepository] = None
logger = StructuredLogger("vector_cache")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Async context manager for startup/shutdown"""
    global repo

    logger.info(
        "Starting vector cache service",
        context={"qdrant_host": Config.QDRANT.HOST, "qdrant_port": Config.QDRANT.PORT},
    )

    client = AsyncQdrantClient(host=Config.QDRANT.HOST, port=Config.QDRANT.PORT)
    repo = QdrantRepository(client)
    await repo.ensure_collections()

    counts = await repo.get_collection_counts()
    cache_questions_total.set(counts.get(Config.COLLECTIONS.QUESTIONS, 0))
    cache_interactions_total.set(counts.get(Config.COLLECTIONS.TUTORING_NODES, 0))

    logger.info(
        "Vector cache service started",
        context={"collections": counts},
    )

    yield

    logger.info("Shutting down vector cache service")
    await client.close()


app = FastAPI(title="Math Tutor Vector Cache Service", lifespan=lifespan)


@app.middleware("http")
async def logging_and_metrics_middleware(request: FastAPIRequest, call_next):
    """Middleware to log all HTTP requests and responses, and record metrics"""
    incoming_request_id = request.headers.get("X-Request-ID")
    request_id = incoming_request_id if incoming_request_id else generate_request_id()
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
                service="vector_cache",
                endpoint=request.url.path,
                method=request.method,
                status=response.status_code,
            ).inc()

            http_request_duration_seconds.labels(
                service="vector_cache",
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
                service="vector_cache",
                endpoint=request.url.path,
                method=request.method,
                status=500,
            ).inc()

            http_request_duration_seconds.labels(
                service="vector_cache",
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


def get_repo() -> QdrantRepository:
    """Get repository instance"""
    if repo is None:
        raise HTTPException(status_code=503, detail="Repository not initialized")
    return repo


# === Health Check ===


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint"""
    try:
        repository = get_repo()
        counts = await repository.get_collection_counts()

        cache_questions_total.set(counts.get(Config.COLLECTIONS.QUESTIONS, 0))
        cache_interactions_total.set(counts.get(Config.COLLECTIONS.TUTORING_NODES, 0))

        return HealthResponse(
            status="healthy",
            service="vector_cache",
            qdrant_connected=True,
            collections=counts,
        )
    except Exception:
        return HealthResponse(
            status="unhealthy",
            service="vector_cache",
            qdrant_connected=False,
            collections={},
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


# === Vector Search Operations ===


@app.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest, fastapi_request: FastAPIRequest
) -> SearchResponse:
    """Search for similar questions by embedding"""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())
    repository = get_repo()

    logger.info(
        "Searching cache",
        context={
            "embedding_dims": len(request.embedding),
            "top_k": request.top_k,
            "threshold": request.threshold,
        },
        request_id=request_id,
    )

    cache_searches_total.inc()

    results = await repository.search_questions(
        embedding=request.embedding,
        top_k=request.top_k,
        threshold=request.threshold,
        filters=request.filters,
    )

    if results:
        cache_search_hits_total.inc()
        await repository.increment_usage(results[0]["id"])

        for r in results:
            cache_similarity_score.observe(r["score"])

        logger.info(
            "Cache search hit",
            context={
                "results_count": len(results),
                "top_score": results[0]["score"],
                "top_question_id": results[0]["id"],
            },
            request_id=request_id,
        )
    else:
        cache_search_misses_total.inc()
        logger.info(
            "Cache search miss",
            context={"threshold": request.threshold},
            request_id=request_id,
        )

    items = [
        SearchResultItem(
            id=r["id"],
            score=r["score"],
            question_text=r["question_text"],
            answer_text=r["answer_text"],
            lesson=r.get("lesson"),
            confidence=r["confidence"],
            source=SourceType(r["source"]),
            usage_count=r.get("usage_count", 0),
        )
        for r in results
    ]

    return SearchResponse(results=items, total_found=len(items))


# === Question CRUD Operations ===


@app.post("/questions", response_model=QuestionResponse, status_code=201)
async def create_question(
    request: QuestionCreate, fastapi_request: FastAPIRequest
) -> QuestionResponse:
    """Add a new question to the cache"""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())
    repository = get_repo()

    logger.info(
        "Creating question",
        context={
            "question_length": len(request.question_text),
            "lesson": request.lesson,
            "source": request.source.value,
        },
        request_id=request_id,
    )

    cache_saves_total.inc()

    question_id = await repository.add_question(
        question_text=request.question_text,
        reformulated_text=request.reformulated_text,
        answer_text=request.answer_text,
        embedding=request.embedding,
        lesson=request.lesson,
        source=request.source,
        confidence=request.confidence,
    )

    question = await repository.get_question(question_id)
    if not question:
        raise HTTPException(status_code=500, detail="Failed to create question")

    cache_questions_total.inc()

    logger.info(
        "Question created",
        context={"question_id": question_id},
        request_id=request_id,
    )

    return _to_question_response(question)


@app.post("/questions/bulk", response_model=BulkCreateResponse, status_code=201)
async def bulk_create_questions(
    request: BulkCreateRequest, fastapi_request: FastAPIRequest
) -> BulkCreateResponse:
    """Add multiple questions at once"""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())
    repository = get_repo()

    logger.info(
        "Bulk creating questions",
        context={"count": len(request.questions)},
        request_id=request_id,
    )

    ids = []
    for q in request.questions:
        question_id = await repository.add_question(
            question_text=q.question_text,
            reformulated_text=q.reformulated_text,
            answer_text=q.answer_text,
            embedding=q.embedding,
            lesson=q.lesson,
            source=q.source,
            confidence=q.confidence,
        )
        ids.append(question_id)
        cache_saves_total.inc()
        cache_questions_total.inc()

    logger.info(
        "Bulk creation completed",
        context={"created_count": len(ids)},
        request_id=request_id,
    )

    return BulkCreateResponse(created_count=len(ids), ids=ids)


@app.get("/questions/{question_id}", response_model=QuestionResponse)
async def get_question(question_id: str) -> QuestionResponse:
    """Get a question by ID"""
    repository = get_repo()
    question = await repository.get_question(question_id)

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    return _to_question_response(question)


@app.patch("/questions/{question_id}", response_model=QuestionResponse)
async def update_question(
    question_id: str, request: QuestionUpdate, fastapi_request: FastAPIRequest
) -> QuestionResponse:
    """Update a question"""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())
    repository = get_repo()

    existing = await repository.get_question(question_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Question not found")

    await repository.update_question(
        question_id=question_id,
        answer_text=request.answer_text,
        confidence=request.confidence,
        lesson=request.lesson,
    )

    question = await repository.get_question(question_id)
    if not question:
        raise HTTPException(
            status_code=500, detail="Failed to retrieve updated question"
        )

    logger.info(
        "Question updated",
        context={"question_id": question_id},
        request_id=request_id,
    )

    return _to_question_response(question)


@app.delete("/questions/{question_id}", status_code=204)
async def delete_question(question_id: str, fastapi_request: FastAPIRequest) -> None:
    """Delete a question"""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())
    repository = get_repo()

    existing = await repository.get_question(question_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Question not found")

    await repository.delete_question(question_id)
    cache_questions_total.dec()

    logger.info(
        "Question deleted",
        context={"question_id": question_id},
        request_id=request_id,
    )


@app.post("/questions/{question_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    question_id: str, request: FeedbackRequest, fastapi_request: FastAPIRequest
) -> FeedbackResponse:
    """Submit feedback for a question"""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())
    repository = get_repo()

    try:
        result = await repository.add_feedback(question_id, request.positive)

        if request.positive:
            feedback_positive_total.inc()
        else:
            feedback_negative_total.inc()

        logger.info(
            "Feedback submitted",
            context={
                "question_id": question_id,
                "positive": request.positive,
                "feedback_score": result["feedback_score"],
            },
            request_id=request_id,
        )

        return FeedbackResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# === Interaction Operations ===


@app.post("/interactions", response_model=InteractionResponse, status_code=201)
async def create_interaction(
    request: InteractionCreate, fastapi_request: FastAPIRequest
) -> InteractionResponse:
    """Create an interaction node (cache a tutoring exchange)"""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())
    repository = get_repo()

    question = await repository.get_question(request.question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    if request.parent_id:
        parent = await repository.get_interaction(request.parent_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Parent interaction not found")

        if parent.get("depth", 0) >= Config.GRAPH.MAX_DEPTH:
            raise HTTPException(
                status_code=400,
                detail=f"Max depth {Config.GRAPH.MAX_DEPTH} exceeded",
            )

    node_id = await repository.add_interaction(
        question_id=request.question_id,
        parent_id=request.parent_id,
        user_input=request.user_input,
        user_input_embedding=request.user_input_embedding,
        system_response=request.system_response,
    )

    node = await repository.get_interaction(node_id)
    if not node:
        raise HTTPException(status_code=500, detail="Failed to create interaction")

    cache_interactions_total.inc()
    interaction_depth_histogram.observe(node["depth"])

    logger.info(
        "Interaction created",
        context={
            "node_id": node_id,
            "question_id": request.question_id,
            "depth": node["depth"],
        },
        request_id=request_id,
    )

    return _to_interaction_response(node)


@app.get("/interactions/{node_id}", response_model=InteractionResponse)
async def get_interaction(node_id: str) -> InteractionResponse:
    """Get an interaction by ID"""
    repository = get_repo()
    node = await repository.get_interaction(node_id)

    if not node:
        raise HTTPException(status_code=404, detail="Interaction not found")

    return _to_interaction_response(node)


@app.post("/interactions/search", response_model=SearchChildrenResponse)
async def search_children(
    request: SearchChildrenRequest, fastapi_request: FastAPIRequest
) -> SearchChildrenResponse:
    """Search for similar user inputs among children of a parent."""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())
    repository = get_repo()

    question = await repository.get_question(request.question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    if request.parent_id:
        parent = await repository.get_interaction(request.parent_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Parent interaction not found")

    result = await repository.search_children(
        question_id=request.question_id,
        parent_id=request.parent_id,
        user_input_embedding=request.user_input_embedding,
        threshold=request.threshold,
    )

    if result["is_cache_hit"]:
        interaction_cache_hits_total.inc()
        logger.info(
            "Interaction cache hit",
            context={
                "question_id": request.question_id,
                "match_score": result["match_score"],
            },
            request_id=request_id,
        )
    else:
        interaction_cache_misses_total.inc()
        logger.info(
            "Interaction cache miss",
            context={"question_id": request.question_id},
            request_id=request_id,
        )

    matched_node = None
    if result.get("matched_node"):
        matched_node = _to_interaction_response(result["matched_node"])

    return SearchChildrenResponse(
        is_cache_hit=result["is_cache_hit"],
        match_score=result.get("match_score"),
        matched_node=matched_node,
        parent_id=result.get("parent_id"),
    )


@app.get("/interactions/path/{question_id}", response_model=ConversationPathResponse)
async def get_conversation_path(
    question_id: str, node_id: Optional[str] = None
) -> ConversationPathResponse:
    """Get full conversation path from question to current node"""
    repository = get_repo()

    question = await repository.get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    if node_id:
        node = await repository.get_interaction(node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Interaction not found")

    result = await repository.get_conversation_path(question_id, node_id)

    return ConversationPathResponse(
        question_id=result["question_id"],
        question_text=result["question_text"],
        answer_text=result["answer_text"],
        path=[
            ConversationPathNode(
                id=n["id"],
                user_input=n["user_input"],
                system_response=n["system_response"],
                depth=n["depth"],
            )
            for n in result["path"]
        ],
        total_depth=result["total_depth"],
    )


# === Helper Functions ===


def _to_question_response(q: dict) -> QuestionResponse:
    """Convert dict to QuestionResponse"""
    return QuestionResponse(
        id=q["id"],
        question_text=q["question_text"],
        reformulated_text=q["reformulated_text"],
        answer_text=q["answer_text"],
        lesson=q.get("lesson"),
        source=SourceType(q["source"]),
        confidence=q["confidence"],
        usage_count=q.get("usage_count", 0),
        positive_feedback=q.get("positive_feedback", 0),
        negative_feedback=q.get("negative_feedback", 0),
        created_at=q["created_at"],
        updated_at=q["updated_at"],
    )


def _to_interaction_response(n: dict) -> InteractionResponse:
    """Convert dict to InteractionResponse"""
    return InteractionResponse(
        id=n["id"],
        question_id=n["question_id"],
        parent_id=n.get("parent_id"),
        user_input=n["user_input"],
        system_response=n["system_response"],
        depth=n["depth"],
        source=SourceType(n["source"]),
        created_at=n["created_at"],
    )
