from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module", autouse=True)
def setup_module(app):
    """Set up module-level client for app service with lifespan mocks."""
    global client
    with (
        patch("src.main.AsyncQdrantClient"),
        patch("src.main.vector_cache.initialize", new_callable=AsyncMock),
        patch("src.main.session_service.start_cleanup"),
        patch("src.main.session_service.stop_cleanup"),
    ):
        client = TestClient(app)
        yield


@pytest.mark.unit
def test_models_endpoint():
    """Test /v1/models endpoint returns correct model list."""
    response = client.get("/v1/models")

    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert len(data["data"]) > 0
    assert data["data"][0]["id"] == "math-tutor"
    assert data["data"][0]["owned_by"] == "lebanese-high-school-math-tutor"


@pytest.mark.unit
@patch("src.main.process_user_input", new_callable=AsyncMock)
@patch("src.main.retrieve_answer", new_callable=AsyncMock)
def test_chat_completions_success(mock_retrieve, mock_process):
    """Test successful chat completion through full pipeline."""
    mock_process.return_value = {"reformulated_query": "What is the derivative of x^2?"}
    mock_retrieve.return_value = {
        "answer": "The derivative of x^2 is 2x",
        "source": "small_llm",
    }

    request_data = {
        "model": "math-tutor",
        "messages": [{"role": "user", "content": "What is the derivative of x^2?"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "created" in data
    assert data["model"] == "math-tutor"
    assert len(data["choices"]) == 1
    assert "derivative" in data["choices"][0]["message"]["content"].lower()


@pytest.mark.unit
def test_chat_completions_no_user_message():
    """Test chat completion with no user message."""
    request_data = {
        "model": "math-tutor",
        "messages": [{"role": "system", "content": "You are a tutor"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 400
    assert "no user message" in response.json()["detail"].lower()


@pytest.mark.unit
def test_chat_completions_missing_messages():
    """Test chat completion with missing messages field."""
    response = client.post("/v1/chat/completions", json={"model": "math-tutor"})
    assert response.status_code == 422


@pytest.mark.unit
@patch("src.main.process_user_input", new_callable=AsyncMock)
@patch("src.main.retrieve_answer", new_callable=AsyncMock)
def test_chat_completions_extracts_last_user_message(mock_retrieve, mock_process):
    """Test that chat completion extracts the last user message from conversation."""
    mock_process.return_value = {"reformulated_query": "Is 4 correct?"}
    mock_retrieve.return_value = {"answer": "Yes, 4 is correct", "source": "small_llm"}

    request_data = {
        "model": "math-tutor",
        "messages": [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "Is that correct?"},
        ],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200
    mock_process.assert_called_once()
    call_args = mock_process.call_args[0]
    assert call_args[0] == "Is that correct?"


@pytest.mark.unit
@patch("src.main.process_user_input", new_callable=AsyncMock)
def test_chat_completions_processing_error(mock_process):
    """Test chat completion when processing phase fails."""
    mock_process.side_effect = Exception("Processing failed")

    request_data = {
        "model": "math-tutor",
        "messages": [{"role": "user", "content": "test"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 500
    assert "error" in response.json()["detail"].lower()


@pytest.mark.unit
@patch("src.main.process_user_input", new_callable=AsyncMock)
@patch("src.main.retrieve_answer", new_callable=AsyncMock)
def test_chat_completions_retrieval_error(mock_retrieve, mock_process):
    """Test chat completion when retrieval phase fails."""
    mock_process.return_value = {"reformulated_query": "test"}
    mock_retrieve.side_effect = Exception("Retrieval failed")

    request_data = {
        "model": "math-tutor",
        "messages": [{"role": "user", "content": "test"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 500


@pytest.mark.unit
@patch("src.main.process_user_input", new_callable=AsyncMock)
@patch("src.main.retrieve_answer", new_callable=AsyncMock)
def test_chat_completions_missing_answer_key(mock_retrieve, mock_process):
    """Test chat completion when retrieval returns unexpected format."""
    mock_process.return_value = {"reformulated_query": "test"}
    mock_retrieve.return_value = {"source": "small_llm"}

    request_data = {
        "model": "math-tutor",
        "messages": [{"role": "user", "content": "test"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 502
    assert "missing key" in response.json()["detail"].lower()


@pytest.mark.unit
def test_track_request_endpoint():
    """Test /track/{id} endpoint returns trace structure."""
    request_id = "test-request-123"

    response = client.get(f"/track/{request_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == request_id
    assert "services" in data
    assert "app" in data["services"]
    assert "log_count" in data["services"]["app"]
    assert "logs" in data["services"]["app"]
    assert "timeline" in data


@pytest.mark.unit
@patch("src.main.process_user_input", new_callable=AsyncMock)
@patch("src.main.retrieve_answer", new_callable=AsyncMock)
def test_chat_completions_special_characters(mock_retrieve, mock_process):
    """Test chat completion with special characters and unicode."""
    mock_process.return_value = {"reformulated_query": "What is \u222b x\u00b2 dx?"}
    mock_retrieve.return_value = {
        "answer": "\u222b x\u00b2 dx = x\u00b3/3 + C",
        "source": "large_llm",
    }

    request_data = {
        "model": "math-tutor",
        "messages": [{"role": "user", "content": "What is \u222b x\u00b2 dx?"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert "\u222b" in data["choices"][0]["message"]["content"]


@pytest.mark.unit
@patch("src.main.process_user_input", new_callable=AsyncMock)
@patch("src.main.retrieve_answer", new_callable=AsyncMock)
def test_chat_completions_long_message(mock_retrieve, mock_process):
    """Test chat completion with very long user message."""
    mock_process.return_value = {"reformulated_query": "long query"}
    mock_retrieve.return_value = {"answer": "answer", "source": "small_llm"}

    long_message = "a" * 10000
    request_data = {
        "model": "math-tutor",
        "messages": [{"role": "user", "content": long_message}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200


@pytest.mark.unit
@patch("src.main.process_user_input", new_callable=AsyncMock)
@patch("src.main.retrieve_answer", new_callable=AsyncMock)
def test_chat_completions_response_structure(mock_retrieve, mock_process):
    """Test that chat completion response has correct OpenAI-compatible structure."""
    mock_process.return_value = {"reformulated_query": "test"}
    mock_retrieve.return_value = {"answer": "test answer", "source": "small_llm"}

    request_data = {
        "model": "math-tutor",
        "messages": [{"role": "user", "content": "test"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200
    data = response.json()

    # Verify OpenAI-compatible structure
    assert "id" in data
    assert "object" in data
    assert data["object"] == "chat.completion"
    assert "created" in data
    assert "model" in data
    assert "choices" in data
    assert isinstance(data["choices"], list)
    assert len(data["choices"]) > 0

    # Verify choice structure
    choice = data["choices"][0]
    assert "index" in choice
    assert choice["index"] == 0
    assert "message" in choice
    assert "role" in choice["message"]
    assert choice["message"]["role"] == "assistant"
    assert "content" in choice["message"]
    assert "finish_reason" in choice


@pytest.mark.unit
@patch("src.routes.admin.vector_cache.get_health", new_callable=AsyncMock)
@patch("src.routes.admin.session_service")
def test_health_endpoint(mock_session, mock_get_health):
    """Test /health endpoint returns components structure."""
    mock_get_health.return_value = {"qdrant_connected": True, "collections": {}}
    mock_session.get_active_session_count.return_value = 2
    mock_session.get_uptime.return_value = 123.456

    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "app"
    assert "components" in data
    assert "qdrant" in data["components"]
    assert data["components"]["qdrant"]["qdrant_connected"] is True
    assert "session" in data["components"]
    assert data["components"]["session"]["active_sessions"] == 2
