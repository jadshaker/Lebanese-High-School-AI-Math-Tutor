from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.unit.test_services.conftest import _ensure_env, _ensure_path, _mock_logging

_ensure_env()
_ensure_path()
_mock_logging()

from src.services.vector_cache import service as vector_cache


@pytest.fixture(autouse=True)
def mock_repo():
    mock = MagicMock()
    mock.search_questions = AsyncMock(return_value=[])
    mock.add_question = AsyncMock(return_value="test-question-id")
    mock.get_question = AsyncMock(return_value=None)
    mock.increment_usage = AsyncMock()
    mock.add_interaction = AsyncMock(return_value="test-interaction-id")
    mock.get_interaction = AsyncMock(return_value=None)
    mock.search_children = AsyncMock(
        return_value={
            "is_cache_hit": False,
            "match_score": None,
            "matched_node": None,
            "parent_id": None,
        }
    )
    mock.get_conversation_path = AsyncMock(
        return_value={
            "question_id": "q-1",
            "question_text": "Q",
            "answer_text": "A",
            "path": [],
            "total_depth": 0,
        }
    )
    mock.get_collection_counts = AsyncMock(
        return_value={"questions": 10, "tutoring_nodes": 5}
    )
    vector_cache.repo = mock
    yield mock
    vector_cache.repo = None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_questions_returns_results(mock_repo):
    """Test search_questions returns results from repository."""
    mock_repo.search_questions = AsyncMock(
        return_value=[
            {
                "id": "q-1",
                "score": 0.92,
                "question_text": "What is 2+2?",
                "answer_text": "4",
                "lesson": None,
                "confidence": 0.9,
                "source": "api_llm",
                "usage_count": 1,
            }
        ]
    )

    results = await vector_cache.search_questions(
        embedding=[0.1] * 1536,
        top_k=5,
        threshold=0.5,
        request_id="test-req-1",
    )

    assert len(results) == 1
    assert results[0]["id"] == "q-1"
    assert results[0]["score"] == 0.92
    mock_repo.search_questions.assert_awaited_once()
    mock_repo.increment_usage.assert_awaited_once_with("q-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_questions_empty(mock_repo):
    """Test search_questions returns empty list when no results."""
    mock_repo.search_questions = AsyncMock(return_value=[])

    results = await vector_cache.search_questions(
        embedding=[0.1] * 1536,
        top_k=5,
        threshold=0.5,
        request_id="test-req-2",
    )

    assert results == []
    mock_repo.increment_usage.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_question(mock_repo):
    """Test add_question stores a question and returns its ID."""
    mock_repo.add_question = AsyncMock(return_value="test-id")

    question_id = await vector_cache.add_question(
        question_text="What is 2+2?",
        reformulated_text="What is the sum of 2 and 2?",
        answer_text="4",
        embedding=[0.1] * 1536,
        request_id="test-req-3",
    )

    assert question_id == "test-id"
    mock_repo.add_question.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_children_cache_hit(mock_repo):
    """Test search_children when a cache hit is found."""
    mock_repo.search_children = AsyncMock(
        return_value={
            "is_cache_hit": True,
            "match_score": 0.92,
            "matched_node": {
                "id": "node-1",
                "user_input": "I understand",
                "system_response": "Great!",
            },
            "parent_id": "parent-1",
        }
    )

    result = await vector_cache.search_children(
        question_id="q-1",
        parent_id="parent-1",
        user_input_embedding=[0.1] * 1536,
        threshold=0.7,
        request_id="test-req-4",
    )

    assert result["is_cache_hit"] is True
    assert result["match_score"] == 0.92
    assert result["matched_node"]["id"] == "node-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_children_cache_miss(mock_repo):
    """Test search_children when no cache hit is found."""
    mock_repo.search_children = AsyncMock(
        return_value={
            "is_cache_hit": False,
            "match_score": None,
            "matched_node": None,
            "parent_id": None,
        }
    )

    result = await vector_cache.search_children(
        question_id="q-1",
        parent_id=None,
        user_input_embedding=[0.1] * 1536,
        threshold=0.7,
        request_id="test-req-5",
    )

    assert result["is_cache_hit"] is False
    assert result["match_score"] is None
    assert result["matched_node"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_interaction(mock_repo):
    """Test add_interaction stores an interaction and returns node ID."""
    mock_repo.add_interaction = AsyncMock(return_value="node-42")
    mock_repo.get_interaction = AsyncMock(return_value={"id": "node-42", "depth": 2})

    node_id = await vector_cache.add_interaction(
        question_id="q-1",
        parent_id="parent-1",
        user_input="I don't understand",
        user_input_embedding=[0.1] * 1536,
        system_response="Let me explain differently...",
        request_id="test-req-6",
    )

    assert node_id == "node-42"
    mock_repo.add_interaction.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_conversation_path(mock_repo):
    """Test get_conversation_path returns the full path."""
    mock_repo.get_conversation_path = AsyncMock(
        return_value={
            "question_id": "q-1",
            "question_text": "What is x?",
            "answer_text": "A variable",
            "path": [
                {"id": "n-1", "user_input": "?", "system_response": "!", "depth": 1},
                {
                    "id": "n-2",
                    "user_input": "ok",
                    "system_response": "good",
                    "depth": 2,
                },
            ],
            "total_depth": 2,
        }
    )

    result = await vector_cache.get_conversation_path(
        question_id="q-1",
        node_id="n-2",
    )

    assert result["question_id"] == "q-1"
    assert len(result["path"]) == 2
    assert result["total_depth"] == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_health_connected(mock_repo):
    """Test get_health when Qdrant is connected."""
    mock_repo.get_collection_counts = AsyncMock(
        return_value={"questions": 10, "tutoring_nodes": 5}
    )

    result = await vector_cache.get_health()

    assert result["qdrant_connected"] is True
    assert result["collections"]["questions"] == 10
    assert result["collections"]["tutoring_nodes"] == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_health_disconnected():
    """Test get_health when Qdrant is not initialized (repo is None)."""
    vector_cache.repo = None

    result = await vector_cache.get_health()

    assert result["qdrant_connected"] is False
    assert result["collections"] == {}
