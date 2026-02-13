from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# Module-level setup - load app and create client
@pytest.fixture(scope="module", autouse=True)
def setup_module(vector_cache_app):
    """Set up module-level client for vector cache service"""
    global client
    client = TestClient(vector_cache_app)


def _mock_repo():
    """Create a mock repository with async methods."""
    mock = MagicMock()
    mock.get_collection_counts = AsyncMock(
        return_value={"questions": 10, "tutoring_nodes": 5}
    )
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
    return mock


@pytest.mark.unit
def test_health_endpoint():
    """Test health check endpoint returns correct structure"""
    mock_repo = _mock_repo()
    with patch("src.main.get_repo", return_value=mock_repo):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "vector_cache"
        assert "qdrant_connected" in data


@pytest.mark.unit
def test_search_endpoint_structure():
    """Test search endpoint returns correct structure"""
    mock_repo = _mock_repo()
    mock_repo.search_questions = AsyncMock(
        return_value=[
            {
                "id": "test-id-1",
                "score": 0.95,
                "question_text": "What is 2+2?",
                "answer_text": "4",
                "lesson": None,
                "confidence": 0.9,
                "source": "api_llm",
                "usage_count": 0,
            },
        ]
    )

    with patch("src.main.get_repo", return_value=mock_repo):
        request_data = {
            "embedding": [0.1] * 1536,
            "top_k": 5,
        }

        response = client.post("/search", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total_found" in data


@pytest.mark.unit
def test_search_endpoint_missing_embedding():
    """Test search endpoint with missing embedding"""
    response = client.post("/search", json={"top_k": 3})
    assert response.status_code == 422


@pytest.mark.unit
def test_search_endpoint_invalid_top_k():
    """Test search endpoint with invalid top_k"""
    request_data = {
        "embedding": [0.1] * 1536,
        "top_k": -1,
    }
    response = client.post("/search", json=request_data)
    assert response.status_code == 422


@pytest.mark.unit
def test_add_question_endpoint():
    """Test adding a question to the cache"""
    mock_repo = _mock_repo()
    mock_repo.get_question = AsyncMock(
        return_value={
            "id": "test-question-id",
            "question_text": "What is the derivative of x^2?",
            "reformulated_text": "What is the derivative of x^2?",
            "answer_text": "The derivative is 2x",
            "lesson": None,
            "source": "api_llm",
            "confidence": 0.9,
            "usage_count": 0,
            "positive_feedback": 0,
            "negative_feedback": 0,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
    )

    with patch("src.main.get_repo", return_value=mock_repo):
        request_data = {
            "question_text": "What is the derivative of x^2?",
            "reformulated_text": "What is the derivative of x^2?",
            "answer_text": "The derivative is 2x",
            "embedding": [0.1] * 1536,
            "source": "api_llm",
            "confidence": 0.9,
        }

        response = client.post("/questions", json=request_data)

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "test-question-id"


@pytest.mark.unit
def test_add_question_missing_fields():
    """Test adding a question with missing fields"""
    response = client.post("/questions", json={"question_text": "test"})
    assert response.status_code == 422


@pytest.mark.unit
def test_add_interaction_endpoint():
    """Test adding a tutoring interaction"""
    mock_repo = _mock_repo()
    mock_repo.get_question = AsyncMock(return_value={"id": "q-1"})
    mock_repo.get_interaction = AsyncMock(
        return_value={
            "id": "test-interaction-id",
            "question_id": "q-1",
            "parent_id": None,
            "user_input": "I don't understand",
            "system_response": "Let me explain...",
            "depth": 1,
            "source": "api_llm",
            "created_at": "2025-01-01T00:00:00Z",
        }
    )

    with patch("src.main.get_repo", return_value=mock_repo):
        request_data = {
            "question_id": "q-1",
            "parent_id": None,
            "user_input": "I don't understand",
            "user_input_embedding": [0.1] * 1536,
            "system_response": "Let me explain...",
        }

        response = client.post("/interactions", json=request_data)

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "test-interaction-id"


@pytest.mark.unit
def test_search_interactions_endpoint():
    """Test searching tutoring interactions"""
    mock_repo = _mock_repo()
    mock_repo.get_question = AsyncMock(return_value={"id": "q-1"})
    mock_repo.get_interaction = AsyncMock(
        return_value={"id": "parent-node-id", "depth": 1}
    )
    mock_repo.search_children = AsyncMock(
        return_value={
            "is_cache_hit": True,
            "match_score": 0.92,
            "matched_node": {
                "id": "child-id-1",
                "user_input": "I understand now",
                "system_response": "Great!",
                "question_id": "q-1",
                "parent_id": "parent-node-id",
                "depth": 2,
                "source": "api_llm",
                "created_at": "2025-01-01T00:00:00Z",
            },
            "parent_id": "parent-node-id",
        }
    )

    with patch("src.main.get_repo", return_value=mock_repo):
        request_data = {
            "question_id": "q-1",
            "parent_id": "parent-node-id",
            "user_input_embedding": [0.1] * 1536,
        }

        response = client.post("/interactions/search", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["is_cache_hit"] is True


@pytest.mark.unit
def test_get_conversation_path():
    """Test getting conversation path"""
    mock_repo = _mock_repo()
    mock_repo.get_question = AsyncMock(return_value={"id": "q-1"})
    mock_repo.get_interaction = AsyncMock(return_value={"id": "n-2", "depth": 2})
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

    with patch("src.main.get_repo", return_value=mock_repo):
        response = client.get("/interactions/path/q-1?node_id=n-2")

        assert response.status_code == 200
        data = response.json()
        assert data["question_id"] == "q-1"
        assert len(data["path"]) == 2
        assert data["total_depth"] == 2


@pytest.mark.unit
def test_metrics_endpoint():
    """Test metrics endpoint returns Prometheus format"""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")


@pytest.mark.unit
def test_search_results_sorted_by_similarity():
    """Test that search results are sorted by similarity score"""
    mock_repo = _mock_repo()
    mock_repo.search_questions = AsyncMock(
        return_value=[
            {
                "id": "1",
                "score": 0.95,
                "question_text": "Q1",
                "answer_text": "A1",
                "lesson": None,
                "confidence": 0.9,
                "source": "api_llm",
                "usage_count": 0,
            },
            {
                "id": "2",
                "score": 0.85,
                "question_text": "Q2",
                "answer_text": "A2",
                "lesson": None,
                "confidence": 0.9,
                "source": "api_llm",
                "usage_count": 0,
            },
            {
                "id": "3",
                "score": 0.75,
                "question_text": "Q3",
                "answer_text": "A3",
                "lesson": None,
                "confidence": 0.9,
                "source": "api_llm",
                "usage_count": 0,
            },
        ]
    )

    with patch("src.main.get_repo", return_value=mock_repo):
        request_data = {"embedding": [0.1] * 1536, "top_k": 5}
        response = client.post("/search", json=request_data)

        assert response.status_code == 200
        data = response.json()
        scores = [r["score"] for r in data["results"]]
        assert scores == sorted(scores, reverse=True)
