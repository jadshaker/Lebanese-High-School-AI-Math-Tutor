from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# Module-level setup - load app and create client
@pytest.fixture(scope="module", autouse=True)
def setup_module(embedding_app):
    """Set up module-level client for embedding service"""
    global client
    client = TestClient(embedding_app)


@pytest.mark.unit
def test_health_endpoint():
    """Test health check endpoint returns correct structure"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "embedding"
    assert "model" in data
    assert "dimensions" in data
    assert "api_configured" in data


@pytest.mark.unit
@patch("src.main.client")
def test_embed_endpoint_success(mock_openai_client):
    """Test successful embedding generation"""
    # Mock OpenAI client response
    mock_embedding_obj = MagicMock()
    mock_embedding_obj.embedding = [0.1] * 1536
    mock_response = MagicMock()
    mock_response.data = [mock_embedding_obj]
    mock_response.model = "text-embedding-3-small"
    mock_openai_client.embeddings.create.return_value = mock_response

    response = client.post("/embed", json={"text": "test question"})

    assert response.status_code == 200
    data = response.json()
    assert "embedding" in data
    assert len(data["embedding"]) == 1536
    assert data["model"] == "text-embedding-3-small"
    assert data["dimensions"] == 1536


@pytest.mark.unit
def test_embed_endpoint_missing_text():
    """Test embed endpoint with missing text field"""
    response = client.post("/embed", json={})
    assert response.status_code == 422  # Validation error


@pytest.mark.unit
@patch("src.main.client", None)
def test_embed_endpoint_no_api_key():
    """Test embed endpoint when API key not configured (fallback)"""
    response = client.post("/embed", json={"text": "test question"})

    assert response.status_code == 200
    data = response.json()
    assert "embedding" in data
    assert len(data["embedding"]) == 1536
    assert data["model"] == "dummy-fallback"
    assert all(val == 0.0 for val in data["embedding"])


@pytest.mark.unit
@patch("src.main.client")
def test_embed_endpoint_api_error(mock_openai_client):
    """Test embed endpoint when OpenAI API returns error"""
    mock_openai_client.embeddings.create.side_effect = Exception("API Error")

    response = client.post("/embed", json={"text": "test question"})

    assert response.status_code == 500
    assert "error" in response.json()["detail"].lower()


@pytest.mark.unit
@patch("src.main.client")
def test_embed_endpoint_long_text(mock_openai_client):
    """Test embed endpoint with very long text"""
    # Mock OpenAI client response
    mock_embedding_obj = MagicMock()
    mock_embedding_obj.embedding = [0.1] * 1536
    mock_response = MagicMock()
    mock_response.data = [mock_embedding_obj]
    mock_response.model = "text-embedding-3-small"
    mock_openai_client.embeddings.create.return_value = mock_response

    long_text = "a" * 10000
    response = client.post("/embed", json={"text": long_text})

    assert response.status_code == 200
    data = response.json()
    assert len(data["embedding"]) == 1536


@pytest.mark.unit
@patch("src.main.client")
def test_embed_endpoint_special_characters(mock_openai_client):
    """Test embed endpoint with special characters and unicode"""
    # Mock OpenAI client response
    mock_embedding_obj = MagicMock()
    mock_embedding_obj.embedding = [0.1] * 1536
    mock_response = MagicMock()
    mock_response.data = [mock_embedding_obj]
    mock_response.model = "text-embedding-3-small"
    mock_openai_client.embeddings.create.return_value = mock_response

    special_text = "∫ x² dx = ? 你好 مرحبا"
    response = client.post("/embed", json={"text": special_text})

    assert response.status_code == 200
    data = response.json()
    assert len(data["embedding"]) == 1536
