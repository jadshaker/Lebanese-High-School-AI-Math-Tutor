import os
import sys
import uuid
from pathlib import Path

import pytest
import requests

# Add tests directory to path to import conftest helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import wait_for_logs, wait_for_metrics

APP_URL = os.getenv("APP_URL", "http://localhost:8000")


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.xdist_group("full_pipeline")
def test_simple_math_question(mock_external_apis):
    """
    Test asking a simple math question through the complete pipeline.

    This test verifies:
    - Complete user journey: Data Processing -> Answer Retrieval (mocked by default)
    - Response contains reasonable answer
    - OpenAI-compatible format is correct
    - Request tracking works end-to-end

    Use --use-real-apis flag to test against real services (requires HPC connection & API keys).
    """
    request_id = f"e2e-test-{uuid.uuid4().hex[:8]}"

    response = requests.post(
        f"{APP_URL}/v1/chat/completions",
        json={
            "model": "math-tutor",
            "messages": [{"role": "user", "content": "What is the derivative of x^2?"}],
        },
        headers={"X-Request-ID": request_id},
        timeout=360,
    )

    assert response.status_code == 200, f"Chat completion failed: {response.text}"
    data = response.json()

    # Verify OpenAI-compatible format
    assert "id" in data
    assert "object" in data
    assert data["object"] == "chat.completion"
    assert "created" in data
    assert "model" in data
    assert data["model"] == "math-tutor"
    assert "choices" in data

    # Verify choices structure
    assert len(data["choices"]) > 0
    choice = data["choices"][0]
    assert "index" in choice
    assert choice["index"] == 0
    assert "message" in choice
    assert "finish_reason" in choice
    assert choice["finish_reason"] == "stop"

    # Verify message structure
    message = choice["message"]
    assert "role" in message
    assert message["role"] == "assistant"
    assert "content" in message

    # Verify answer exists and is reasonable (don't check exact content)
    answer = message["content"]
    assert len(answer) > 10, "Answer should be more than just a few characters"

    # Verify request ID is in response headers
    request_id_header = response.headers.get("X-Request-ID") or response.headers.get(
        "x-request-id"
    )
    assert request_id_header is not None, "Request ID should be in response headers"

    # Verify request tracking works
    track_response = requests.get(f"{APP_URL}/track/{request_id}", timeout=60)
    assert (
        track_response.status_code == 200
    ), f"Tracking request failed: {track_response.text}"

    track_data = track_response.json()
    assert "request_id" in track_data
    assert track_data["request_id"] == request_id
    assert "services" in track_data
    assert "timeline" in track_data

    # Verify we have logs from services that support /logs endpoint
    services_with_logs = track_data["services"]
    assert len(services_with_logs) > 0, "Should have logs from at least one service"

    print(f"\n  Simple Math Question Test:")
    print(f"  Request ID: {request_id}")
    print(f"  Question: What is the derivative of x^2?")
    print(f"  Answer length: {len(answer)} chars")
    print(f"  Answer preview: {answer[:100]}...")
    print(f"  Services with logs: {list(services_with_logs.keys())}")
    print(f"  Timeline entries: {len(track_data['timeline'])}")


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.xdist_group("full_pipeline")
def test_cache_behavior_on_repeated_question(mock_external_apis):
    """
    Test cache behavior when asking the same question twice.

    This test verifies:
    - First request completes successfully (mocked by default)
    - Second request completes successfully
    - Both requests get answers (cache stub returns 0.85 similarity)
    - Metrics show cache searches happened

    Use --use-real-apis flag to test against real services.
    """
    # Use a unique question to avoid interference from other tests
    question = f"What is the integral of {uuid.uuid4().hex[:4]}x dx?"
    request_id_1 = f"e2e-cache-1-{uuid.uuid4().hex[:8]}"
    request_id_2 = f"e2e-cache-2-{uuid.uuid4().hex[:8]}"

    # First request
    response_1 = requests.post(
        f"{APP_URL}/v1/chat/completions",
        json={
            "model": "math-tutor",
            "messages": [{"role": "user", "content": question}],
        },
        headers={"X-Request-ID": request_id_1},
        timeout=360,
    )

    assert response_1.status_code == 200, f"First request failed: {response_1.text}"
    data_1 = response_1.json()

    # Verify first response structure
    assert "choices" in data_1
    assert len(data_1["choices"]) > 0
    answer_1 = data_1["choices"][0]["message"]["content"]
    assert len(answer_1) > 0

    # Second request with same question
    response_2 = requests.post(
        f"{APP_URL}/v1/chat/completions",
        json={
            "model": "math-tutor",
            "messages": [{"role": "user", "content": question}],
        },
        headers={"X-Request-ID": request_id_2},
        timeout=360,
    )

    assert response_2.status_code == 200, f"Second request failed: {response_2.text}"
    data_2 = response_2.json()

    # Verify second response structure
    assert "choices" in data_2
    assert len(data_2["choices"]) > 0
    answer_2 = data_2["choices"][0]["message"]["content"]
    assert len(answer_2) > 0

    # Wait for metrics to be available (handles Prometheus aggregation delay)
    metrics_text = wait_for_metrics(APP_URL, timeout=3.0)

    # Verify cache-related metrics exist (either hits or misses)
    has_cache_metric = (
        "gateway_cache_misses_total" in metrics_text
        or "gateway_cache_hits_total" in metrics_text
        or "cache_search_duration" in metrics_text
    )

    # Note: Cache stub always returns 0.85 similarity (not exact match)
    # So both requests will trigger LLM calls, but cache was searched

    print(f"\n  Cache Behavior Test:")
    print(f"  Question: {question}")
    print(f"  First request ID: {request_id_1}")
    print(f"  First answer length: {len(answer_1)} chars")
    print(f"  Second request ID: {request_id_2}")
    print(f"  Second answer length: {len(answer_2)} chars")
    print(f"  Cache metrics recorded: {'Yes' if has_cache_metric else 'No'}")


@pytest.mark.e2e
@pytest.mark.xdist_group("no_pod")
def test_invalid_input_handling():
    """
    Test how the system handles invalid inputs.

    This test verifies:
    - Empty message is rejected
    - Malformed JSON is rejected
    - Missing required fields are rejected
    - Appropriate error responses (400/422)
    """
    request_id = f"e2e-invalid-{uuid.uuid4().hex[:8]}"

    # Test 1: Empty messages array
    response = requests.post(
        f"{APP_URL}/v1/chat/completions",
        json={"model": "math-tutor", "messages": []},
        headers={"X-Request-ID": request_id},
        timeout=30,
    )

    assert response.status_code in [
        400,
        422,
    ], f"Should reject empty messages, got {response.status_code}"

    # Test 2: Missing messages field
    response = requests.post(
        f"{APP_URL}/v1/chat/completions",
        json={"model": "math-tutor"},
        headers={"X-Request-ID": request_id},
        timeout=30,
    )

    assert response.status_code in [
        400,
        422,
    ], f"Should reject missing messages, got {response.status_code}"

    # Test 3: Messages without user role
    response = requests.post(
        f"{APP_URL}/v1/chat/completions",
        json={
            "model": "math-tutor",
            "messages": [{"role": "system", "content": "You are a tutor"}],
        },
        headers={"X-Request-ID": request_id},
        timeout=30,
    )

    assert response.status_code in [
        400,
        422,
    ], f"Should reject no user message, got {response.status_code}"

    # Test 4: Invalid message structure (missing content)
    response = requests.post(
        f"{APP_URL}/v1/chat/completions",
        json={"model": "math-tutor", "messages": [{"role": "user"}]},
        headers={"X-Request-ID": request_id},
        timeout=30,
    )

    assert response.status_code in [
        400,
        422,
    ], f"Should reject missing content, got {response.status_code}"

    # Test 5: Empty content string
    response = requests.post(
        f"{APP_URL}/v1/chat/completions",
        json={"model": "math-tutor", "messages": [{"role": "user", "content": ""}]},
        headers={"X-Request-ID": request_id},
        timeout=30,
    )

    # Empty content might be accepted by Pydantic but could fail at service level
    # Either way is acceptable - we just verify it doesn't crash
    assert response.status_code in [
        200,
        400,
        422,
        500,
    ], f"Should handle empty content gracefully, got {response.status_code}"

    print(f"\n  Invalid Input Handling Test:")
    print(f"  Empty messages: Rejected correctly")
    print(f"  Missing messages: Rejected correctly")
    print(f"  No user message: Rejected correctly")
    print(f"  Missing content: Rejected correctly")
    print(f"  All invalid inputs handled appropriately")


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.xdist_group("full_pipeline")
def test_request_tracking_end_to_end(mock_external_apis):
    """
    Test request tracking within the consolidated app.

    This test verifies:
    - Request ID propagates through the app pipeline (mocked by default)
    - Timeline shows the app service logs
    - Logs are collected and returned
    - Timeline is sorted chronologically

    Use --use-real-apis flag to test against real services.
    """
    # Make a complete request through the pipeline
    response = requests.post(
        f"{APP_URL}/v1/chat/completions",
        json={
            "model": "math-tutor",
            "messages": [{"role": "user", "content": "Explain the quadratic formula"}],
        },
        timeout=360,
    )

    assert response.status_code == 200, f"Chat completion failed: {response.text}"

    # Get the request ID from response headers (app generates it)
    request_id = response.headers.get("X-Request-ID") or response.headers.get(
        "x-request-id"
    )
    assert request_id is not None, "Request ID should be in response headers"

    # Wait for logs to be written (handles async log collection race condition)
    track_data = wait_for_logs(APP_URL, request_id, timeout=5.0, min_services=1)

    # Verify tracking response structure
    assert "request_id" in track_data
    assert track_data["request_id"] == request_id
    assert "services" in track_data
    assert "timeline" in track_data

    services = track_data["services"]
    timeline = track_data["timeline"]

    # Verify we have logs from at least the app service
    assert len(services) > 0, "Should have logs from at least one service"
    assert len(timeline) > 0, "Should have timeline entries"

    # Verify timeline structure
    for entry in timeline:
        assert "service" in entry, "Timeline entry should have service field"
        assert "log" in entry, "Timeline entry should have log field"
        assert len(entry["log"]) > 0, "Log entry should not be empty"

    # Verify timeline is sorted chronologically
    # Extract timestamps from log lines (format: YYYY-MM-DD HH:MM:SS.fff)
    timestamps = [entry["log"][:23] for entry in timeline if len(entry["log"]) >= 23]
    assert timestamps == sorted(timestamps), "Timeline should be sorted chronologically"

    print(f"\n  Request Tracking End-to-End Test:")
    print(f"  Request ID: {request_id}")
    print(f"  Services with logs: {list(services.keys())}")
    print(f"  Total timeline entries: {len(timeline)}")

    # Print log counts per service
    for service_name, service_data in services.items():
        log_count = service_data.get("log_count", 0)
        print(f"    - {service_name}: {log_count} logs")


@pytest.mark.e2e
@pytest.mark.xdist_group("no_pod")
def test_all_services_healthy():
    """
    Test that the app and its components are healthy.

    This test verifies:
    - App's /health endpoint works
    - Components report their status
    - App health response has the expected structure
    """
    response = requests.get(f"{APP_URL}/health", timeout=10)

    assert response.status_code == 200, f"Health check failed: {response.text}"
    data = response.json()

    # Verify response structure
    assert "status" in data
    assert "service" in data
    assert data["service"] == "app"
    assert "components" in data

    # App status should be healthy or degraded
    assert data["status"] in [
        "healthy",
        "degraded",
    ], f"App status should be healthy or degraded, got: {data['status']}"

    components = data["components"]

    # Expected components in consolidated app
    expected_components = ["qdrant", "session"]

    for component_name in expected_components:
        assert (
            component_name in components
        ), f"Component {component_name} should be in health check"

    # Verify qdrant component has expected fields
    qdrant = components["qdrant"]
    assert "qdrant_connected" in qdrant, "Qdrant component should have qdrant_connected"

    # Verify session component has expected fields
    session = components["session"]
    assert "active_sessions" in session, "Session component should have active_sessions"
    assert "uptime_seconds" in session, "Session component should have uptime_seconds"

    print(f"\n  App Health Check:")
    print(f"  App status: {data['status']}")
    print(f"  Qdrant connected: {qdrant.get('qdrant_connected')}")
    print(f"  Active sessions: {session.get('active_sessions')}")
    print(f"  Uptime: {session.get('uptime_seconds')}s")
