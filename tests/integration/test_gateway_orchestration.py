import os
import uuid

import pytest
import requests

APP_URL = os.getenv("APP_URL", "http://localhost:8000")


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.xdist_group("full_pipeline")
def test_full_pipeline_simple_question(mock_external_apis):
    """
    Test: Complete flow from user input to final answer

    This test verifies:
    - App's /v1/chat/completions endpoint works end-to-end (mocked by default)
    - Response structure matches OpenAI format
    - Answer exists (don't validate exact content)

    Use --use-real-apis flag for real LLM calls (takes 30-60 seconds)
    """
    request_id = f"test-{uuid.uuid4().hex[:8]}"

    response = requests.post(
        f"{APP_URL}/v1/chat/completions",
        json={
            "model": "math-tutor",
            "messages": [{"role": "user", "content": "What is 2+2?"}],
        },
        headers={"X-Request-ID": request_id},
        timeout=360,
    )

    assert response.status_code == 200, f"App failed: {response.text}"
    data = response.json()

    # Check OpenAI format
    assert "id" in data
    assert "object" in data
    assert data["object"] == "chat.completion"
    assert "created" in data
    assert "model" in data
    assert "choices" in data

    # Check choices structure
    assert len(data["choices"]) > 0
    choice = data["choices"][0]
    assert "index" in choice
    assert "message" in choice
    assert "finish_reason" in choice

    # Check message structure
    message = choice["message"]
    assert "role" in message
    assert message["role"] == "assistant"
    assert "content" in message

    # Check answer exists (don't check exact content)
    answer = message["content"]
    assert len(answer) > 0

    # Check request_id in headers
    assert "X-Request-ID" in response.headers or "x-request-id" in response.headers

    print(f"\n  Full Pipeline:")
    print(f"  Request ID: {request_id}")
    print(f"  Question: What is 2+2?")
    print(f"  Answer length: {len(answer)} chars")
    print(f"  Finish reason: {choice['finish_reason']}")


@pytest.mark.integration
@pytest.mark.xdist_group("no_pod")
def test_request_id_propagation(mock_external_apis):
    """
    Test: Request ID is tracked within the consolidated app

    This test verifies:
    - Request ID is stored with logs when calling /v1/chat/completions
    - /track/{request_id} returns app logs for the request
    """
    request_id = f"test-{uuid.uuid4().hex[:8]}"

    # Make a request through the full pipeline
    response = requests.post(
        f"{APP_URL}/v1/chat/completions",
        json={
            "model": "math-tutor",
            "messages": [{"role": "user", "content": "test query for logging"}],
        },
        headers={"X-Request-ID": request_id},
        timeout=360,
    )

    assert response.status_code == 200, f"App failed: {response.text}"

    # Call /track/{request_id} on the app
    response = requests.get(f"{APP_URL}/track/{request_id}", timeout=10)

    assert response.status_code == 200, f"Track request failed: {response.text}"
    data = response.json()

    # Check response structure
    assert "request_id" in data
    assert data["request_id"] == request_id

    # The consolidated app tracks logs under "app"
    assert "services" in data
    assert "timeline" in data

    services = data["services"]
    timeline = data["timeline"]

    # We should have logs from the app service
    assert len(services) > 0, "Should have logs from at least one service"
    assert len(timeline) > 0, "Should have timeline entries"

    # Verify timeline structure
    for entry in timeline:
        assert "service" in entry
        assert "log" in entry
        assert len(entry["log"]) > 0

    print(f"\n  Request ID Propagation:")
    print(f"  Request ID: {request_id}")
    print(f"  Services with logs: {list(services.keys())}")
    print(f"  Total log entries: {len(timeline)}")

    for service_name in services:
        log_count = services[service_name]["log_count"]
        print(f"    - {service_name}: {log_count} logs")


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.xdist_group("full_pipeline")
def test_metrics_are_recorded(mock_external_apis):
    """
    Test: Prometheus metrics are recorded correctly

    This test verifies:
    - Request to App generates metrics (mocked by default)
    - /metrics endpoint returns Prometheus format
    - Expected metrics exist (cache, LLM calls, HTTP requests)

    Use --use-real-apis flag for real LLM calls (takes 30-60 seconds)
    """
    # Make a request to generate metrics
    response = requests.post(
        f"{APP_URL}/v1/chat/completions",
        json={
            "model": "math-tutor",
            "messages": [{"role": "user", "content": "What is 5+3?"}],
        },
        timeout=360,
    )

    assert response.status_code == 200, f"App failed: {response.text}"

    # Check /metrics endpoint
    response = requests.get(f"{APP_URL}/metrics", timeout=10)

    assert response.status_code == 200, "Metrics endpoint failed"
    metrics_text = response.text

    # Verify Prometheus format (starts with # HELP or metric names)
    assert len(metrics_text) > 0
    assert "# HELP" in metrics_text or "# TYPE" in metrics_text

    # Verify expected metrics exist
    has_cache_metric = (
        "gateway_cache_misses_total" in metrics_text
        or "gateway_cache_hits_total" in metrics_text
    )
    has_llm_metric = "gateway_llm_calls_total" in metrics_text
    has_http_metric = "http_requests_total" in metrics_text

    assert (
        has_cache_metric or has_llm_metric or has_http_metric
    ), "Expected metrics not found. Available metrics:\n" + "\n".join(
        [line for line in metrics_text.split("\n") if not line.startswith("#")][:20]
    )

    print(f"\n  Metrics Recording:")
    print(f"  Cache metrics: {'Yes' if has_cache_metric else 'No'}")
    print(f"  LLM metrics: {'Yes' if has_llm_metric else 'No'}")
    print(f"  HTTP metrics: {'Yes' if has_http_metric else 'No'}")

    # Print sample metrics (first 10 non-comment lines)
    metric_lines = [
        line for line in metrics_text.split("\n") if line and not line.startswith("#")
    ]
    print(f"  Sample metrics ({len(metric_lines)} total):")
    for line in metric_lines[:10]:
        print(f"    {line}")
