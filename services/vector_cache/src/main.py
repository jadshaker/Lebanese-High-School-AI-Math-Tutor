from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import AsyncQdrantClient
from src.config import Config
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

# Global repository instance
repo: QdrantRepository | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Async context manager for startup/shutdown"""
    global repo

    # Startup: Initialize Qdrant client and repository
    client = AsyncQdrantClient(host=Config.QDRANT.HOST, port=Config.QDRANT.PORT)
    repo = QdrantRepository(client)
    await repo.ensure_collections()

    yield

    # Shutdown: Close client
    await client.close()


app = FastAPI(title="Math Tutor Vector Cache Service", lifespan=lifespan)

# CORS for UI access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        return HealthResponse(
            status="healthy",
            service="vector_cache",
            qdrant_connected=True,
            collections=counts,
        )
    except Exception as e:
        return HealthResponse(
            status="unhealthy",
            service="vector_cache",
            qdrant_connected=False,
            collections={},
        )


# === Vector Search Operations ===


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    """Search for similar questions by embedding"""
    repository = get_repo()

    results = await repository.search_questions(
        embedding=request.embedding,
        top_k=request.top_k,
        threshold=request.threshold,
        filters=request.filters,
    )

    # Increment usage count for top result
    if results:
        await repository.increment_usage(results[0]["id"])

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
async def create_question(request: QuestionCreate) -> QuestionResponse:
    """Add a new question to the cache"""
    repository = get_repo()

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

    return _to_question_response(question)


@app.post("/questions/bulk", response_model=BulkCreateResponse, status_code=201)
async def bulk_create_questions(request: BulkCreateRequest) -> BulkCreateResponse:
    """Add multiple questions at once"""
    repository = get_repo()
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
    question_id: str, request: QuestionUpdate
) -> QuestionResponse:
    """Update a question"""
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
    return _to_question_response(question)


@app.delete("/questions/{question_id}", status_code=204)
async def delete_question(question_id: str) -> None:
    """Delete a question"""
    repository = get_repo()

    existing = await repository.get_question(question_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Question not found")

    await repository.delete_question(question_id)


@app.post("/questions/{question_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    question_id: str, request: FeedbackRequest
) -> FeedbackResponse:
    """Submit feedback for a question"""
    repository = get_repo()

    try:
        result = await repository.add_feedback(question_id, request.positive)
        return FeedbackResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# === Interaction Operations ===
# Interactions store (user_input, system_response) pairs
# Used for incremental caching of tutoring conversations


@app.post("/interactions", response_model=InteractionResponse, status_code=201)
async def create_interaction(request: InteractionCreate) -> InteractionResponse:
    """Create an interaction node (cache a tutoring exchange)"""
    repository = get_repo()

    # Validate question exists
    question = await repository.get_question(request.question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # Validate parent exists if specified
    if request.parent_id:
        parent = await repository.get_interaction(request.parent_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Parent interaction not found")

        # Check max depth
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
async def search_children(request: SearchChildrenRequest) -> SearchChildrenResponse:
    """Search for similar user inputs among children of a parent.

    If parent_id is None, searches direct children of the question (depth 1).
    Returns cache hit with matched interaction, or cache miss for new node creation.
    """
    repository = get_repo()

    # Validate question exists
    question = await repository.get_question(request.question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # Validate parent exists if specified
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

    matched_node = None
    if result.get("matched_node"):
        matched_node = _to_interaction_response(result["matched_node"])

    return SearchChildrenResponse(
        is_cache_hit=result["is_cache_hit"],
        match_score=result.get("match_score"),
        matched_node=matched_node,
        parent_id=result.get("parent_id"),
    )


@app.get(
    "/interactions/path/{question_id}", response_model=ConversationPathResponse
)
async def get_conversation_path(
    question_id: str, node_id: str | None = None
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
