from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# Module-level setup - load app and create client
@pytest.fixture(scope="module", autouse=True)
def setup_module(vector_cache_app):
    """Set up module-level client for vector cache service"""
    global client
    client = TestClient(vector_cache_app)


@pytest.mark.unit
def test_health_endpoint():
    """Test health check endpoint returns correct structure"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "vector-cache"
    assert "qdrant_connected" in data


@pytest.mark.unit
def test_search_endpoint_structure():
    """Test search endpoint returns correct structure"""
    with patch("src.main.repository") as mock_repo:
        # Mock the search results
        mock_repo.search_questions.return_value = [
            {
                "id": "test-id-1",
                "question": "What is 2+2?",
                "answer": "4",
                "similarity_score": 0.95,
            },
            {
                "id": "test-id-2",
                "question": "What is 3+3?",
                "answer": "6",
                "similarity_score": 0.85,
            },
        ]

        request_data = {
            "embedding": [0.1] * 1536,
            "top_k": 5,
        }

        response = client.post("/search", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "count" in data


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
    with patch("src.main.repository") as mock_repo:
        mock_repo.add_question.return_value = "test-question-id"

        request_data = {
            "question": "What is the derivative of x^2?",
            "answer": "The derivative is 2x",
            "embedding": [0.1] * 1536,
        }

        response = client.post("/questions", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "id" in data


@pytest.mark.unit
def test_add_question_missing_fields():
    """Test adding a question with missing fields"""
    response = client.post("/questions", json={"question": "test"})
    assert response.status_code == 422


@pytest.mark.unit
def test_add_interaction_endpoint():
    """Test adding a tutoring interaction"""
    with patch("src.main.repository") as mock_repo:
        mock_repo.add_interaction.return_value = "test-interaction-id"

        request_data = {
            "parent_id": "parent-node-id",
            "question_context": "What is derivative?",
            "user_response": "I don't understand",
            "tutor_response": "Let me explain...",
            "intent": "negative",
            "embedding": [0.1] * 1536,
        }

        response = client.post("/interactions", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "id" in data


@pytest.mark.unit
def test_search_interactions_endpoint():
    """Test searching tutoring interactions"""
    with patch("src.main.repository") as mock_repo:
        mock_repo.search_children.return_value = [
            {
                "id": "child-id-1",
                "user_response": "I understand now",
                "tutor_response": "Great!",
                "intent": "affirmative",
                "similarity_score": 0.92,
            }
        ]

        request_data = {
            "parent_id": "parent-node-id",
            "embedding": [0.1] * 1536,
            "top_k": 3,
        }

        response = client.post("/interactions/search", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "results" in data


@pytest.mark.unit
def test_get_conversation_path():
    """Test getting conversation path"""
    with patch("src.main.repository") as mock_repo:
        mock_repo.get_conversation_path.return_value = [
            {"id": "node-1", "depth": 0},
            {"id": "node-2", "depth": 1},
            {"id": "node-3", "depth": 2},
        ]

        response = client.get("/interactions/node-3/path")

        assert response.status_code == 200
        data = response.json()
        assert "path" in data
        assert len(data["path"]) == 3


@pytest.mark.unit
def test_metrics_endpoint():
    """Test metrics endpoint returns Prometheus format"""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")


@pytest.mark.unit
def test_search_results_sorted_by_similarity():
    """Test that search results are sorted by similarity score"""
    with patch("src.main.repository") as mock_repo:
        # Return results in sorted order (as they would be from Qdrant)
        mock_repo.search_questions.return_value = [
            {"id": "1", "question": "Q1", "answer": "A1", "similarity_score": 0.95},
            {"id": "2", "question": "Q2", "answer": "A2", "similarity_score": 0.85},
            {"id": "3", "question": "Q3", "answer": "A3", "similarity_score": 0.75},
        ]

        request_data = {"embedding": [0.1] * 1536, "top_k": 5}
        response = client.post("/search", json=request_data)

        assert response.status_code == 200
        data = response.json()
        scores = [r["similarity_score"] for r in data["results"]]
        assert scores == sorted(scores, reverse=True)
