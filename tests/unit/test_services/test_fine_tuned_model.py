from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from services.fine_tuned_model.src.config import Config

MODEL_NAME = Config.FINE_TUNED_MODEL_NAME


# Module-level setup - load app and create client
@pytest.fixture(scope="module", autouse=True)
def setup_module(fine_tuned_model_app):
    """Set up module-level client for fine_tuned_model service"""
    global client
    client = TestClient(fine_tuned_model_app)


@pytest.mark.unit
@patch("src.main.urlopen")
def test_health_endpoint_healthy(mock_urlopen):
    """Test health check when Ollama is reachable and model available"""
    # Mock Ollama /api/tags response
    mock_response = MagicMock()
    mock_response.read.return_value = (
        f'{{"models": [{{"name": "{MODEL_NAME}"}}]}}'.encode()
    )
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "fine_tuned_model"
    assert data["ollama_reachable"] is True
    assert data["model_available"] is True
    assert "configured_model" in data


@pytest.mark.unit
@patch("src.main.urlopen")
def test_health_endpoint_degraded(mock_urlopen):
    """Test health check when Ollama is unreachable"""
    mock_urlopen.side_effect = Exception("Connection refused")

    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["ollama_reachable"] is False
    assert data["model_available"] is False


@pytest.mark.unit
@patch("src.main.client")
def test_chat_completions_success(mock_openai_client):
    """Test successful chat completion via Ollama"""
    # Mock Ollama response
    mock_message = MagicMock()
    mock_message.content = "The answer is 4"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 5

    mock_response = MagicMock()
    mock_response.id = "chatcmpl-123"
    mock_response.created = 1234567890
    mock_response.model = MODEL_NAME
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage
    mock_response.model_dump.return_value = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": MODEL_NAME,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "The answer is 4"},
                "finish_reason": "stop",
            }
        ],
    }

    mock_openai_client.chat.completions.create.return_value = mock_response

    request_data = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": "What is 2+2?"}],
        "temperature": 0.7,
        "max_tokens": 500,
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["model"] == MODEL_NAME
    assert len(data["choices"]) == 1
    assert data["choices"][0]["message"]["content"] == "The answer is 4"


@pytest.mark.unit
def test_chat_completions_missing_messages():
    """Test chat completion with missing messages field"""
    response = client.post("/v1/chat/completions", json={"model": MODEL_NAME})
    assert response.status_code == 422  # Validation error


@pytest.mark.unit
@patch("src.main.client")
def test_chat_completions_service_error(mock_openai_client):
    """Test chat completion when Ollama returns error"""
    mock_openai_client.chat.completions.create.side_effect = Exception(
        "Connection error"
    )

    request_data = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": "test"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 503
    assert "error" in response.json()["detail"].lower()


@pytest.mark.unit
@patch("src.main.client")
def test_chat_completions_default_model(mock_openai_client):
    """Test chat completion with explicit model (model field is required)"""
    # Mock Ollama response
    mock_message = MagicMock()
    mock_message.content = "Response"
    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.id = "chatcmpl-123"
    mock_response.created = 1234567890
    mock_response.model = MODEL_NAME
    mock_response.choices = [mock_choice]
    mock_response.usage = None
    mock_response.model_dump.return_value = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": MODEL_NAME,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Response"},
                "finish_reason": "stop",
            }
        ],
    }

    mock_openai_client.chat.completions.create.return_value = mock_response

    request_data = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": "test"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200


@pytest.mark.unit
@patch("src.main.client")
def test_chat_completions_multiple_messages(mock_openai_client):
    """Test chat completion with conversation history"""
    # Mock Ollama response
    mock_message = MagicMock()
    mock_message.content = "Yes, that's right"
    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.id = "chatcmpl-123"
    mock_response.created = 1234567890
    mock_response.model = MODEL_NAME
    mock_response.choices = [mock_choice]
    mock_response.usage = None
    mock_response.model_dump.return_value = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": MODEL_NAME,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Yes, that's right"},
                "finish_reason": "stop",
            }
        ],
    }

    mock_openai_client.chat.completions.create.return_value = mock_response

    request_data = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "Are you sure?"},
        ],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["message"]["content"] == "Yes, that's right"


@pytest.mark.unit
@patch("src.main.client")
def test_chat_completions_special_characters(mock_openai_client):
    """Test chat completion with special characters and unicode"""
    # Mock Ollama response
    mock_message = MagicMock()
    mock_message.content = "√16 = 4"
    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.id = "chatcmpl-123"
    mock_response.created = 1234567890
    mock_response.model = MODEL_NAME
    mock_response.choices = [mock_choice]
    mock_response.usage = None
    mock_response.model_dump.return_value = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": MODEL_NAME,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "√16 = 4"},
                "finish_reason": "stop",
            }
        ],
    }

    mock_openai_client.chat.completions.create.return_value = mock_response

    request_data = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": "What is √16?"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert "√" in data["choices"][0]["message"]["content"]


@pytest.mark.unit
@patch("src.main.client")
def test_chat_completions_empty_response(mock_openai_client):
    """Test chat completion when model returns empty content"""
    # Mock Ollama response with empty content
    mock_message = MagicMock()
    mock_message.content = ""
    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.id = "chatcmpl-123"
    mock_response.created = 1234567890
    mock_response.model = MODEL_NAME
    mock_response.choices = [mock_choice]
    mock_response.usage = None
    mock_response.model_dump.return_value = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": MODEL_NAME,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": ""},
                "finish_reason": "stop",
            }
        ],
    }

    mock_openai_client.chat.completions.create.return_value = mock_response

    request_data = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": "test"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["message"]["content"] == ""
