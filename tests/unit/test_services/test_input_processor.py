import pytest
from fastapi import HTTPException

from tests.unit.test_services.conftest import _ensure_env, _ensure_path, _mock_logging

_ensure_env()
_ensure_path()
_mock_logging()

from src.services.input_processor.service import process_input


@pytest.mark.unit
def test_process_text_success():
    """Test successful text processing strips whitespace and normalizes spacing."""
    result = process_input("  What is the derivative of x^2?  ", "text", "req-1")

    assert result.processed_input == "What is the derivative of x^2?"
    assert result.input_type == "text"
    assert "preprocessing_applied" in result.metadata


@pytest.mark.unit
def test_process_text_normalizes_spacing():
    """Test that multiple spaces are collapsed to a single space."""
    result = process_input("What   is    the    derivative?", "text", "req-2")

    assert result.processed_input == "What is the derivative?"


@pytest.mark.unit
def test_process_text_empty_input():
    """Test that empty (whitespace-only) input raises HTTPException 400."""
    with pytest.raises(HTTPException) as exc_info:
        process_input("   ", "text", "req-3")

    assert exc_info.value.status_code == 400
    assert "empty" in exc_info.value.detail.lower()


@pytest.mark.unit
def test_process_text_too_long():
    """Test that input exceeding max length raises HTTPException 400."""
    with pytest.raises(HTTPException) as exc_info:
        process_input("a" * 100_000, "text", "req-4")

    assert exc_info.value.status_code == 400
    assert "maximum length" in exc_info.value.detail.lower()


@pytest.mark.unit
def test_process_image_stub():
    """Test image processing stub returns expected structure."""
    result = process_input("base64_encoded_image_data_here", "image", "req-5")

    assert result.input_type == "image"
    assert "not yet implemented" in result.metadata["note"]
    assert "planned_features" in result.metadata


@pytest.mark.unit
def test_process_invalid_type():
    """Test that an unsupported input type raises HTTPException 400."""
    with pytest.raises(HTTPException) as exc_info:
        process_input("test", "audio", "req-6")

    assert exc_info.value.status_code == 400
    assert "invalid input type" in exc_info.value.detail.lower()


@pytest.mark.unit
def test_process_special_characters():
    """Test that unicode and special characters are preserved."""
    result = process_input(
        "  \u222b x\u00b2 dx = ? \u4f60\u597d \u0645\u0631\u062d\u0628\u0627  ",
        "text",
        "req-7",
    )

    assert "\u222b" in result.processed_input
    assert "\u00b2" in result.processed_input
    assert "\u4f60\u597d" in result.processed_input
    assert "\u0645\u0631\u062d\u0628\u0627" in result.processed_input


@pytest.mark.unit
def test_process_metadata_includes_lengths():
    """Test that metadata contains original_length and processed_length."""
    result = process_input("  test  ", "text", "req-8")

    assert result.metadata["original_length"] == 8
    assert result.metadata["processed_length"] == 4


@pytest.mark.unit
def test_process_already_clean_text():
    """Test that already-clean text passes through unchanged."""
    clean = "What is the derivative of x^2?"
    result = process_input(clean, "text", "req-9")

    assert result.processed_input == clean


@pytest.mark.unit
def test_process_text_with_newlines():
    """Test that newlines are normalized to spaces."""
    result = process_input("What is\nthe derivative\nof x^2?", "text", "req-10")

    assert "\n" not in result.processed_input
    assert result.processed_input == "What is the derivative of x^2?"
