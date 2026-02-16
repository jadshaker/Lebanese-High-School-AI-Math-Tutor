from typing import Optional

from qdrant_client import AsyncQdrantClient

from src.config import Config
from src.logging_utils import StructuredLogger
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
    interaction_cache_hits_total,
    interaction_cache_misses_total,
    interaction_depth_histogram,
)
from src.models.schemas import SourceType
from src.services.vector_cache.repository import QdrantRepository

repo: Optional[QdrantRepository] = None
logger = StructuredLogger("vector_cache")


async def initialize(client: AsyncQdrantClient) -> None:
    """Initialize the vector cache with Qdrant client. Call from lifespan."""
    global repo
    repo = QdrantRepository(client)
    await repo.ensure_collections()

    counts = await repo.get_collection_counts()
    cache_questions_total.set(counts.get(Config.COLLECTIONS.QUESTIONS, 0))
    cache_interactions_total.set(counts.get(Config.COLLECTIONS.TUTORING_NODES, 0))

    logger.info("Vector cache initialized", context={"collections": counts})


def get_repo() -> QdrantRepository:
    """Get repository instance."""
    if repo is None:
        raise RuntimeError("Vector cache not initialized")
    return repo


async def search_questions(
    embedding: list[float],
    top_k: int,
    threshold: float = 0.5,
    request_id: str = "",
) -> list[dict]:
    """Search for similar questions by embedding."""
    repository = get_repo()

    logger.info(
        "Searching cache",
        context={
            "embedding_dims": len(embedding),
            "top_k": top_k,
            "threshold": threshold,
        },
        request_id=request_id,
    )

    cache_searches_total.inc()

    results = await repository.search_questions(
        embedding=embedding,
        top_k=top_k,
        threshold=threshold,
    )

    if results:
        cache_search_hits_total.inc()
        await repository.increment_usage(results[0]["id"])
        for r in results:
            cache_similarity_score.observe(r["score"])
    else:
        cache_search_misses_total.inc()

    return results


async def add_question(
    question_text: str,
    reformulated_text: str,
    answer_text: str,
    embedding: list[float],
    lesson: Optional[str] = None,
    source: SourceType = SourceType.API_LLM,
    confidence: float = 0.9,
    request_id: str = "",
) -> str:
    """Add a question to the cache."""
    repository = get_repo()

    cache_saves_total.inc()

    question_id = await repository.add_question(
        question_text=question_text,
        reformulated_text=reformulated_text,
        answer_text=answer_text,
        embedding=embedding,
        lesson=lesson,
        source=source,
        confidence=confidence,
    )

    cache_questions_total.inc()

    logger.info(
        "Question created",
        context={"question_id": question_id},
        request_id=request_id,
    )

    return question_id


async def search_children(
    question_id: str,
    parent_id: Optional[str],
    user_input_embedding: list[float],
    threshold: float = 0.7,
    request_id: str = "",
) -> dict:
    """Search for cached tutoring response among children of current node."""
    repository = get_repo()

    result = await repository.search_children(
        question_id=question_id,
        parent_id=parent_id,
        user_input_embedding=user_input_embedding,
        threshold=threshold,
    )

    if result["is_cache_hit"]:
        interaction_cache_hits_total.inc()
    else:
        interaction_cache_misses_total.inc()

    return result


async def add_interaction(
    question_id: str,
    parent_id: Optional[str],
    user_input: str,
    user_input_embedding: list[float],
    system_response: str,
    request_id: str = "",
) -> str:
    """Save a new tutoring interaction."""
    repository = get_repo()

    node_id = await repository.add_interaction(
        question_id=question_id,
        parent_id=parent_id,
        user_input=user_input,
        user_input_embedding=user_input_embedding,
        system_response=system_response,
    )

    cache_interactions_total.inc()
    node = await repository.get_interaction(node_id)
    if node:
        interaction_depth_histogram.observe(node["depth"])

    logger.info(
        "Interaction created",
        context={"node_id": node_id, "question_id": question_id},
        request_id=request_id,
    )

    return node_id


async def get_conversation_path(
    question_id: str,
    node_id: Optional[str] = None,
) -> dict:
    """Get the full conversation path."""
    repository = get_repo()
    return await repository.get_conversation_path(question_id, node_id)


async def add_feedback(
    question_id: str,
    positive: bool,
    request_id: str = "",
) -> dict:
    """Submit feedback for a question."""
    repository = get_repo()
    result = await repository.add_feedback(question_id, positive)

    if positive:
        feedback_positive_total.inc()
    else:
        feedback_negative_total.inc()

    return result


async def get_health() -> dict:
    """Get vector cache health status."""
    try:
        repository = get_repo()
        counts = await repository.get_collection_counts()
        cache_questions_total.set(counts.get(Config.COLLECTIONS.QUESTIONS, 0))
        cache_interactions_total.set(counts.get(Config.COLLECTIONS.TUTORING_NODES, 0))
        return {"qdrant_connected": True, "collections": counts}
    except Exception:
        return {"qdrant_connected": False, "collections": {}}
