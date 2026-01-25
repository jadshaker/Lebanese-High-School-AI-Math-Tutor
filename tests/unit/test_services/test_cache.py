import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Add service to path
service_path = Path(__file__).parent.parent.parent.parent / "services" / "cache"
sys.path.insert(0, str(service_path))

# Mock StructuredLogger to avoid file system issues
with patch("src.logging_utils.StructuredLogger") as mock_logger:
    mock_logger_instance = MagicMock()
    mock_logger.return_value = mock_logger_instance
    from src.main import app

client = TestClient(app)


@pytest.mark.unit
def test_health_endpoint():
    """Test health check endpoint returns correct structure"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "cache"
    assert data["mode"] == "stub"


@pytest.mark.unit
def test_search_endpoint_success():
    """Test successful cache search (stub mode)"""
    request_data = {
        "embedding": [0.1] * 1536,
        "top_k": 3,
    }

    response = client.post("/search", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "count" in data
    assert data["count"] == 3
    assert len(data["results"]) == 3

    # Check first result structure
    first_result = data["results"][0]
    assert "question" in first_result
    assert "answer" in first_result
    assert "similarity_score" in first_result
    assert 0.0 <= first_result["similarity_score"] <= 1.0


@pytest.mark.unit
def test_search_endpoint_top_k_limit():
    """Test cache search respects top_k parameter"""
    request_data = {
        "embedding": [0.1] * 1536,
        "top_k": 2,
    }

    response = client.post("/search", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["results"]) == 2


@pytest.mark.unit
def test_search_endpoint_missing_embedding():
    """Test cache search with missing embedding field"""
    response = client.post("/search", json={"top_k": 3})
    assert response.status_code == 422  # Validation error


@pytest.mark.unit
def test_search_endpoint_invalid_top_k():
    """Test cache search with invalid top_k (negative)"""
    request_data = {
        "embedding": [0.1] * 1536,
        "top_k": -1,
    }

    response = client.post("/search", json=request_data)
    assert response.status_code == 422  # Validation error


@pytest.mark.unit
def test_save_endpoint_success():
    """Test successful cache save (stub mode)"""
    request_data = {
        "question": "What is the derivative of x^2?",
        "answer": "The derivative of x^2 is 2x",
        "embedding": [0.1] * 1536,
    }

    response = client.post("/save", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "message" in data
    assert "stub mode" in data["message"].lower()


@pytest.mark.unit
def test_save_endpoint_missing_fields():
    """Test cache save with missing required fields"""
    response = client.post("/save", json={"question": "test"})
    assert response.status_code == 422  # Validation error


@pytest.mark.unit
def test_save_endpoint_long_content():
    """Test cache save with very long question and answer"""
    request_data = {
        "question": "a" * 10000,
        "answer": "b" * 10000,
        "embedding": [0.1] * 1536,
    }

    response = client.post("/save", json=request_data)
    assert response.status_code == 200


@pytest.mark.unit
def test_tutoring_endpoint_success():
    """Test tutoring cache endpoint (stub - always returns not found)"""
    request_data = {"question": "What is the derivative of x^2?"}

    response = client.post("/tutoring", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert "found" in data
    assert data["found"] is False
    assert data["data"] is None


@pytest.mark.unit
def test_tutoring_endpoint_missing_question():
    """Test tutoring endpoint with missing question field"""
    response = client.post("/tutoring", json={})
    assert response.status_code == 422  # Validation error


@pytest.mark.unit
def test_search_endpoint_wrong_embedding_dimensions():
    """Test cache search with wrong embedding dimensions"""
    request_data = {
        "embedding": [0.1] * 512,  # Wrong size
        "top_k": 3,
    }

    # Stub mode doesn't validate dimensions, just accepts any list
    response = client.post("/search", json=request_data)
    assert response.status_code == 200


@pytest.mark.unit
def test_search_endpoint_similarity_scores_sorted():
    """Test that cache search results are sorted by similarity score"""
    request_data = {
        "embedding": [0.1] * 1536,
        "top_k": 3,
    }

    response = client.post("/search", json=request_data)

    assert response.status_code == 200
    data = response.json()
    scores = [result["similarity_score"] for result in data["results"]]

    # Check scores are in descending order
    assert scores == sorted(scores, reverse=True)
