import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Add service to path
service_path = Path(__file__).parent.parent.parent.parent / "services" / "gateway"
sys.path.insert(0, str(service_path))

# Mock StructuredLogger to avoid file system issues
with patch("src.logging_utils.StructuredLogger") as mock_logger:
    mock_logger_instance = MagicMock()
    mock_logger.return_value = mock_logger_instance
    from src.main import app

client = TestClient(app)


@pytest.mark.unit
@patch("src.main.urlopen")
def test_health_endpoint_all_healthy(mock_urlopen):
    """Test health check when all services are healthy"""
    # Mock all service health checks
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"status": "healthy", "service": "test"}'
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "gateway"
    assert "services" in data


@pytest.mark.unit
@patch("src.main.urlopen")
def test_health_endpoint_degraded(mock_urlopen):
    """Test health check when some services are unhealthy"""
    # Mock service health checks with one failure
    def mock_health_side_effect(*args, **kwargs):
        mock_response = MagicMock()
        # Simulate one service failing
        if "large_llm" in str(args[0]):
            raise Exception("Service unavailable")
        mock_response.read.return_value = b'{"status": "healthy"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    mock_urlopen.side_effect = mock_health_side_effect

    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert "services" in data


@pytest.mark.unit
def test_models_endpoint():
    """Test /v1/models endpoint returns correct model list"""
    response = client.get("/v1/models")

    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert len(data["data"]) > 0
    assert data["data"][0]["id"] == "math-tutor"
    assert data["data"][0]["owned_by"] == "lebanese-high-school-math-tutor"


@pytest.mark.unit
@patch("src.main.process_user_input")
@patch("src.main.retrieve_answer")
def test_chat_completions_success(mock_retrieve, mock_process):
    """Test successful chat completion through full pipeline"""
    # Mock processing phase
    mock_process.return_value = AsyncMock(
        return_value={"reformulated_query": "What is the derivative of x^2?"}
    )()

    # Mock retrieval phase
    mock_retrieve.return_value = AsyncMock(
        return_value={"answer": "The derivative of x^2 is 2x", "source": "small_llm"}
    )()

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
    """Test chat completion with no user message"""
    request_data = {
        "model": "math-tutor",
        "messages": [{"role": "system", "content": "You are a tutor"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 400
    assert "no user message" in response.json()["detail"].lower()


@pytest.mark.unit
def test_chat_completions_missing_messages():
    """Test chat completion with missing messages field"""
    response = client.post("/v1/chat/completions", json={"model": "math-tutor"})
    assert response.status_code == 422  # Validation error


@pytest.mark.unit
@patch("src.main.process_user_input")
@patch("src.main.retrieve_answer")
def test_chat_completions_extracts_last_user_message(mock_retrieve, mock_process):
    """Test that chat completion extracts the last user message from conversation"""
    # Mock processing phase
    mock_process.return_value = AsyncMock(
        return_value={"reformulated_query": "Is 4 correct?"}
    )()

    # Mock retrieval phase
    mock_retrieve.return_value = AsyncMock(
        return_value={"answer": "Yes, 4 is correct", "source": "small_llm"}
    )()

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
    # Verify that process_user_input was called with the last user message
    mock_process.assert_called_once()
    call_args = mock_process.call_args[0]
    assert call_args[0] == "Is that correct?"


@pytest.mark.unit
@patch("src.main.process_user_input")
def test_chat_completions_processing_error(mock_process):
    """Test chat completion when processing phase fails"""
    mock_process.side_effect = Exception("Processing failed")

    request_data = {
        "model": "math-tutor",
        "messages": [{"role": "user", "content": "test"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 500
    assert "error" in response.json()["detail"].lower()


@pytest.mark.unit
@patch("src.main.process_user_input")
@patch("src.main.retrieve_answer")
def test_chat_completions_retrieval_error(mock_retrieve, mock_process):
    """Test chat completion when retrieval phase fails"""
    # Mock processing phase success
    mock_process.return_value = AsyncMock(
        return_value={"reformulated_query": "test"}
    )()

    # Mock retrieval phase failure
    mock_retrieve.side_effect = Exception("Retrieval failed")

    request_data = {
        "model": "math-tutor",
        "messages": [{"role": "user", "content": "test"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 500


@pytest.mark.unit
@patch("src.main.process_user_input")
@patch("src.main.retrieve_answer")
def test_chat_completions_missing_answer_key(mock_retrieve, mock_process):
    """Test chat completion when retrieval returns unexpected format"""
    # Mock processing phase success
    mock_process.return_value = AsyncMock(
        return_value={"reformulated_query": "test"}
    )()

    # Mock retrieval phase with missing key
    mock_retrieve.return_value = AsyncMock(return_value={"source": "small_llm"})()

    request_data = {
        "model": "math-tutor",
        "messages": [{"role": "user", "content": "test"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 502
    assert "missing key" in response.json()["detail"].lower()


@pytest.mark.unit
def test_track_request_endpoint():
    """Test /track/{id} endpoint returns trace structure"""
    request_id = "test-request-123"

    response = client.get(f"/track/{request_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == request_id
    assert "services" in data
    assert "timeline" in data


@pytest.mark.unit
@patch("src.main.process_user_input")
@patch("src.main.retrieve_answer")
def test_chat_completions_special_characters(mock_retrieve, mock_process):
    """Test chat completion with special characters and unicode"""
    # Mock processing phase
    mock_process.return_value = AsyncMock(
        return_value={"reformulated_query": "What is ∫ x² dx?"}
    )()

    # Mock retrieval phase
    mock_retrieve.return_value = AsyncMock(
        return_value={"answer": "∫ x² dx = x³/3 + C", "source": "large_llm"}
    )()

    request_data = {
        "model": "math-tutor",
        "messages": [{"role": "user", "content": "What is ∫ x² dx?"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert "∫" in data["choices"][0]["message"]["content"]


@pytest.mark.unit
@patch("src.main.process_user_input")
@patch("src.main.retrieve_answer")
def test_chat_completions_long_message(mock_retrieve, mock_process):
    """Test chat completion with very long user message"""
    # Mock processing phase
    mock_process.return_value = AsyncMock(
        return_value={"reformulated_query": "long query"}
    )()

    # Mock retrieval phase
    mock_retrieve.return_value = AsyncMock(
        return_value={"answer": "answer", "source": "small_llm"}
    )()

    long_message = "a" * 10000
    request_data = {
        "model": "math-tutor",
        "messages": [{"role": "user", "content": long_message}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200


@pytest.mark.unit
@patch("src.main.process_user_input")
@patch("src.main.retrieve_answer")
def test_chat_completions_response_structure(mock_retrieve, mock_process):
    """Test that chat completion response has correct OpenAI-compatible structure"""
    # Mock processing phase
    mock_process.return_value = AsyncMock(
        return_value={"reformulated_query": "test"}
    )()

    # Mock retrieval phase
    mock_retrieve.return_value = AsyncMock(
        return_value={"answer": "test answer", "source": "small_llm"}
    )()

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
