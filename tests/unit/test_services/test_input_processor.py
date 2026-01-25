import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Add service to path
service_path = Path(__file__).parent.parent.parent.parent / "services" / "input_processor"
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
    assert data["service"] == "input_processor"
    assert "message" in data


@pytest.mark.unit
def test_process_text_success():
    """Test successful text processing"""
    request_data = {
        "input": "  What is the derivative of x^2?  ",
        "type": "text",
    }

    response = client.post("/process", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["processed_input"] == "What is the derivative of x^2?"
    assert data["input_type"] == "text"
    assert "metadata" in data
    assert "preprocessing_applied" in data["metadata"]


@pytest.mark.unit
def test_process_text_normalizes_spacing():
    """Test that text processing normalizes multiple spaces"""
    request_data = {
        "input": "What   is    the    derivative?",
        "type": "text",
    }

    response = client.post("/process", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["processed_input"] == "What is the derivative?"


@pytest.mark.unit
def test_process_text_empty_input():
    """Test processing empty text returns error"""
    request_data = {
        "input": "   ",
        "type": "text",
    }

    response = client.post("/process", json=request_data)

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


@pytest.mark.unit
def test_process_text_too_long():
    """Test processing text that exceeds maximum length"""
    request_data = {
        "input": "a" * 100000,  # Very long input
        "type": "text",
    }

    response = client.post("/process", json=request_data)

    assert response.status_code == 400
    assert "maximum length" in response.json()["detail"].lower()


@pytest.mark.unit
def test_process_image_stub():
    """Test image processing (stub mode)"""
    request_data = {
        "input": "base64_encoded_image_data_here",
        "type": "image",
    }

    response = client.post("/process", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["input_type"] == "image"
    assert "not yet implemented" in data["metadata"]["note"]


@pytest.mark.unit
def test_process_invalid_type():
    """Test processing with invalid input type"""
    request_data = {
        "input": "test",
        "type": "audio",
    }

    response = client.post("/process", json=request_data)

    assert response.status_code == 400
    assert "invalid input type" in response.json()["detail"].lower()


@pytest.mark.unit
def test_process_missing_fields():
    """Test processing with missing required fields"""
    response = client.post("/process", json={"input": "test"})
    assert response.status_code == 422  # Validation error


@pytest.mark.unit
def test_process_special_characters():
    """Test processing text with special characters and unicode"""
    request_data = {
        "input": "  ∫ x² dx = ? 你好 مرحبا  ",
        "type": "text",
    }

    response = client.post("/process", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert "∫" in data["processed_input"]
    assert "²" in data["processed_input"]
    assert "你好" in data["processed_input"]


@pytest.mark.unit
def test_process_metadata_includes_lengths():
    """Test that metadata includes original and processed lengths"""
    request_data = {
        "input": "  test  ",
        "type": "text",
    }

    response = client.post("/process", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["original_length"] == 8
    assert data["metadata"]["processed_length"] == 4


@pytest.mark.unit
def test_process_already_clean_text():
    """Test processing text that's already clean"""
    request_data = {
        "input": "What is the derivative of x^2?",
        "type": "text",
    }

    response = client.post("/process", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["processed_input"] == "What is the derivative of x^2?"


@pytest.mark.unit
def test_process_text_with_newlines():
    """Test processing text with newlines"""
    request_data = {
        "input": "What is\nthe derivative\nof x^2?",
        "type": "text",
    }

    response = client.post("/process", json=request_data)

    assert response.status_code == 200
    data = response.json()
    # Newlines should be normalized to spaces
    assert "\n" not in data["processed_input"]
