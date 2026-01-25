import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Add service to path
service_path = Path(__file__).parent.parent.parent.parent / "services" / "large_llm"
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
    assert data["service"] == "large_llm"
    assert data["model"] == "gpt-4o-mini"
    assert "api_configured" in data


@pytest.mark.unit
@patch("src.main.client")
def test_chat_completions_success(mock_openai_client):
    """Test successful chat completion"""
    # Mock OpenAI response
    mock_message = MagicMock()
    mock_message.content = "The derivative of x^2 is 2x"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 15
    mock_usage.total_tokens = 25

    mock_response = MagicMock()
    mock_response.id = "chatcmpl-123"
    mock_response.created = 1234567890
    mock_response.model = "gpt-4o-mini"
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    mock_openai_client.chat.completions.create.return_value = mock_response

    request_data = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "What is the derivative of x^2?"}],
        "temperature": 0.7,
        "max_tokens": 500,
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "created" in data
    assert data["model"] == "gpt-4o-mini"
    assert len(data["choices"]) == 1
    assert data["choices"][0]["message"]["content"] == "The derivative of x^2 is 2x"


@pytest.mark.unit
@patch("src.main.client", None)
def test_chat_completions_no_api_key():
    """Test chat completion when API key not configured (fallback)"""
    request_data = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "What is the derivative of x^2?"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "dummy-fallback"
    assert "Dummy Response" in data["choices"][0]["message"]["content"]
    assert "derivative of x^2" in data["choices"][0]["message"]["content"]


@pytest.mark.unit
def test_chat_completions_missing_messages():
    """Test chat completion with missing messages field"""
    response = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini"})
    assert response.status_code == 422  # Validation error


@pytest.mark.unit
@patch("src.main.client")
def test_chat_completions_api_error(mock_openai_client):
    """Test chat completion when OpenAI API returns error"""
    mock_openai_client.chat.completions.create.side_effect = Exception("API Error")

    request_data = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "test"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 500
    assert "error" in response.json()["detail"].lower()


@pytest.mark.unit
@patch("src.main.client")
def test_chat_completions_multiple_messages(mock_openai_client):
    """Test chat completion with conversation history"""
    # Mock OpenAI response
    mock_message = MagicMock()
    mock_message.content = "Yes, that's correct!"
    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.id = "chatcmpl-123"
    mock_response.created = 1234567890
    mock_response.model = "gpt-4o-mini"
    mock_response.choices = [mock_choice]
    mock_response.usage = None

    mock_openai_client.chat.completions.create.return_value = mock_response

    request_data = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "Are you sure?"},
        ],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["message"]["content"] == "Yes, that's correct!"


@pytest.mark.unit
@patch("src.main.client")
def test_chat_completions_empty_response(mock_openai_client):
    """Test chat completion when API returns empty content"""
    # Mock OpenAI response with empty content
    mock_message = MagicMock()
    mock_message.content = None
    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.id = "chatcmpl-123"
    mock_response.created = 1234567890
    mock_response.model = "gpt-4o-mini"
    mock_response.choices = [mock_choice]
    mock_response.usage = None

    mock_openai_client.chat.completions.create.return_value = mock_response

    request_data = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "test"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["message"]["content"] == ""


@pytest.mark.unit
@patch("src.main.client")
def test_chat_completions_special_characters(mock_openai_client):
    """Test chat completion with special characters and unicode"""
    # Mock OpenAI response
    mock_message = MagicMock()
    mock_message.content = "∫ x² dx = x³/3 + C"
    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.id = "chatcmpl-123"
    mock_response.created = 1234567890
    mock_response.model = "gpt-4o-mini"
    mock_response.choices = [mock_choice]
    mock_response.usage = None

    mock_openai_client.chat.completions.create.return_value = mock_response

    request_data = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "∫ x² dx = ?"}],
    }

    response = client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert "∫" in data["choices"][0]["message"]["content"]
