import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Add service to path
service_path = Path(__file__).parent.parent.parent.parent / "services" / "fine_tuned_model"
sys.path.insert(0, str(service_path))

# Mock StructuredLogger to avoid file system issues
with patch("src.logging_utils.StructuredLogger") as mock_logger:
    mock_logger_instance = MagicMock()
    mock_logger.return_value = mock_logger_instance
    from src.main import app

client = TestClient(app)


@pytest.mark.unit
@patch("src.main.urlopen")
def test_health_endpoint_healthy(mock_urlopen):
    """Test health check when Ollama is reachable and model available"""
    # Mock Ollama /api/tags response
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"models": [{"name": "tinyllama:latest"}]}'
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
    mock_response.model = "tinyllama:latest"
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage
    mock_response.model_dump.return_value = {
        "id": "chatcmpl-123",
        "created": 1234567890,
        "model": "tinyllama:latest",
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
        "model": "tinyllama:latest",
        "messages": [{"role": "user", "content": "What is 2+2?"}],
        "temperature": 0.7,
        "max_tokens": 500,
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "tinyllama:latest"
    assert len(data["choices"]) == 1
    assert data["choices"][0]["message"]["content"] == "The answer is 4"


@pytest.mark.unit
def test_chat_completions_missing_messages():
    """Test chat completion with missing messages field"""
    response = client.post("/v1/chat/completions", json={"model": "tinyllama:latest"})
    assert response.status_code == 422  # Validation error


@pytest.mark.unit
@patch("src.main.client")
def test_chat_completions_service_error(mock_openai_client):
    """Test chat completion when Ollama returns error"""
    mock_openai_client.chat.completions.create.side_effect = Exception("Connection error")

    request_data = {
        "model": "tinyllama:latest",
        "messages": [{"role": "user", "content": "test"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 503
    assert "error" in response.json()["detail"].lower()


@pytest.mark.unit
@patch("src.main.client")
def test_chat_completions_default_model(mock_openai_client):
    """Test chat completion uses default model when not specified"""
    # Mock Ollama response
    mock_message = MagicMock()
    mock_message.content = "Response"
    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.id = "chatcmpl-123"
    mock_response.created = 1234567890
    mock_response.model = "tinyllama:latest"
    mock_response.choices = [mock_choice]
    mock_response.usage = None
    mock_response.model_dump.return_value = {
        "id": "chatcmpl-123",
        "created": 1234567890,
        "model": "tinyllama:latest",
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
    mock_response.model = "tinyllama:latest"
    mock_response.choices = [mock_choice]
    mock_response.usage = None
    mock_response.model_dump.return_value = {
        "id": "chatcmpl-123",
        "created": 1234567890,
        "model": "tinyllama:latest",
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
        "model": "tinyllama:latest",
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
    mock_response.model = "tinyllama:latest"
    mock_response.choices = [mock_choice]
    mock_response.usage = None
    mock_response.model_dump.return_value = {
        "id": "chatcmpl-123",
        "created": 1234567890,
        "model": "tinyllama:latest",
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
        "model": "tinyllama:latest",
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
    mock_response.model = "tinyllama:latest"
    mock_response.choices = [mock_choice]
    mock_response.usage = None
    mock_response.model_dump.return_value = {
        "id": "chatcmpl-123",
        "created": 1234567890,
        "model": "tinyllama:latest",
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
        "model": "tinyllama:latest",
        "messages": [{"role": "user", "content": "test"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["message"]["content"] == ""
