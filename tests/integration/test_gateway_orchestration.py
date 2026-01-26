import uuid

import pytest
import requests

# Service URLs for integration testing
GATEWAY_URL = "http://localhost:8000"
INPUT_PROCESSOR_URL = "http://localhost:8004"
REFORMULATOR_URL = "http://localhost:8007"
EMBEDDING_URL = "http://localhost:8002"
CACHE_URL = "http://localhost:8003"
SMALL_LLM_URL = "http://localhost:8005"
LARGE_LLM_URL = "http://localhost:8001"


@pytest.mark.integration
def test_data_processing_pipeline(mock_external_apis):
    """
    Test: Input Processor → Reformulator flow

    This test verifies:
    - HTTP calls to both services (mocked by default, use --use-real-apis for real APIs)
    - Request ID propagation through headers
    - Query reformulation improves the input
    """
    request_id = f"test-{uuid.uuid4().hex[:8]}"
    user_input = "what is 2+2"

    # Step 1: Call Input Processor
    response = requests.post(
        f"{INPUT_PROCESSOR_URL}/process",
        json={"input": user_input, "type": "text"},
        headers={"X-Request-ID": request_id},
        timeout=10,
    )

    assert response.status_code == 200, f"Input Processor failed: {response.text}"
    data = response.json()

    # Verify response structure
    assert "processed_input" in data
    assert "input_type" in data
    assert data["input_type"] == "text"

    processed_input = data["processed_input"]
    assert len(processed_input) > 0

    # Step 2: Call Reformulator with processed input
    response = requests.post(
        f"{REFORMULATOR_URL}/reformulate",
        json={"processed_input": processed_input, "input_type": "text"},
        headers={"X-Request-ID": request_id},
        timeout=30,
    )

    assert response.status_code == 200, f"Reformulator failed: {response.text}"
    data = response.json()

    # Verify response structure
    assert "reformulated_query" in data
    assert "original_input" in data
    assert "improvements_made" in data

    reformulated_query = data["reformulated_query"]
    assert len(reformulated_query) > 0

    # Verify reformulation improved the query (should be more structured)
    assert isinstance(data["improvements_made"], list)

    print(f"\n✓ Data Processing Pipeline:")
    print(f"  Original: {user_input}")
    print(f"  Processed: {processed_input}")
    print(f"  Reformulated: {reformulated_query}")
    print(f"  Improvements: {data['improvements_made']}")


@pytest.mark.integration
@pytest.mark.slow
def test_answer_retrieval_pipeline(mock_external_apis):
    """
    Test: Embed → Cache → Small LLM → Large LLM flow

    This test verifies:
    - Cache returns 0.85 similarity (not exact match)
    - Both Small LLM and Large LLM are called (mocked by default, use --use-real-apis for real APIs)
    - Answer is saved to cache
    """
    request_id = f"test-{uuid.uuid4().hex[:8]}"
    query = "Calculate the integral of 3x^2 dx"

    # Step 1: Embed the query
    response = requests.post(
        f"{EMBEDDING_URL}/embed",
        json={"text": query},
        headers={"X-Request-ID": request_id},
        timeout=10,
    )

    assert response.status_code == 200, f"Embedding failed: {response.text}"
    data = response.json()

    assert "embedding" in data
    embedding = data["embedding"]
    assert len(embedding) == 1536  # OpenAI text-embedding-3-small dimension

    # Step 2: Search cache
    response = requests.post(
        f"{CACHE_URL}/search",
        json={"embedding": embedding, "top_k": 5},
        headers={"X-Request-ID": request_id},
        timeout=10,
    )

    assert response.status_code == 200, f"Cache search failed: {response.text}"
    data = response.json()

    assert "results" in data
    results = data["results"]

    # Cache stub returns results with ~0.85 similarity (not exact match)
    if results:
        top_similarity = results[0]["similarity_score"]
        assert (
            top_similarity < 0.95
        ), "Cache should not return exact match for this test"

    # Step 3: Call Small LLM with cache context
    # Build messages format
    messages = [
        {"role": "system", "content": "You are a math tutor."},
        {"role": "user", "content": query},
    ]

    response = requests.post(
        f"{SMALL_LLM_URL}/v1/chat/completions",
        json={"model": "deepseek-r1:7b", "messages": messages},
        headers={"X-Request-ID": request_id},
        timeout=60,
    )

    assert response.status_code == 200, f"Small LLM failed: {response.text}"
    data = response.json()

    assert "choices" in data
    assert len(data["choices"]) > 0
    small_llm_answer = data["choices"][0]["message"]["content"]
    assert len(small_llm_answer) > 0

    # Step 4: Call Large LLM (since cache didn't have exact match)
    response = requests.post(
        f"{LARGE_LLM_URL}/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": messages},
        headers={"X-Request-ID": request_id},
        timeout=60,
    )

    assert response.status_code == 200, f"Large LLM failed: {response.text}"
    data = response.json()

    assert "choices" in data
    assert len(data["choices"]) > 0
    large_llm_answer = data["choices"][0]["message"]["content"]
    assert len(large_llm_answer) > 0

    # Step 5: Save to cache
    response = requests.post(
        f"{CACHE_URL}/save",
        json={"question": query, "answer": large_llm_answer, "embedding": embedding},
        headers={"X-Request-ID": request_id},
        timeout=10,
    )

    assert response.status_code == 200, f"Cache save failed: {response.text}"
    data = response.json()

    assert data.get("status") == "success"

    print(f"\n✓ Answer Retrieval Pipeline:")
    print(f"  Query: {query}")
    print(
        f"  Cache results: {len(results)} (top similarity: {results[0]['similarity_score']:.2f})"
        if results
        else "  Cache results: None"
    )
    print(f"  Small LLM answer length: {len(small_llm_answer)}")
    print(f"  Large LLM answer length: {len(large_llm_answer)}")
    print(f"  Saved to cache: Yes")


@pytest.mark.integration
@pytest.mark.slow
def test_full_pipeline_simple_question(mock_external_apis):
    """
    Test: Complete flow from user input to final answer

    This test verifies:
    - Gateway's /v1/chat/completions endpoint works end-to-end (mocked by default)
    - Response structure matches OpenAI format
    - Answer exists (don't validate exact content)

    Use --use-real-apis flag for real LLM calls (takes 30-60 seconds)
    """
    request_id = f"test-{uuid.uuid4().hex[:8]}"

    response = requests.post(
        f"{GATEWAY_URL}/v1/chat/completions",
        json={
            "model": "math-tutor",
            "messages": [{"role": "user", "content": "What is 2+2?"}],
        },
        headers={"X-Request-ID": request_id},
        timeout=120,  # Increased timeout for full pipeline
    )

    assert response.status_code == 200, f"Gateway failed: {response.text}"
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

    print(f"\n✓ Full Pipeline:")
    print(f"  Request ID: {request_id}")
    print(f"  Question: What is 2+2?")
    print(f"  Answer length: {len(answer)} chars")
    print(f"  Finish reason: {choice['finish_reason']}")


@pytest.mark.integration
def test_request_id_propagation(mock_external_apis):
    """
    Test: Request ID flows through services that support /logs endpoint

    This test verifies:
    - Request ID is propagated through the pipeline
    - Logs from services that support /logs endpoint are returned
    - Services WITHOUT /logs endpoint are skipped (Small LLM, Fine-Tuned Model, Reformulator)

    NOTE: We only check for logs from Gateway, Input Processor, Embedding, Cache, Large LLM
          because Ollama services (Small LLM, Fine-Tuned Model) and Reformulator don't have /logs endpoint
    Use --use-real-apis flag to test against real services.
    """
    request_id = f"test-{uuid.uuid4().hex[:8]}"

    # Make a request with custom request ID
    response = requests.post(
        f"{INPUT_PROCESSOR_URL}/process",
        json={"input": "test query for logging", "type": "text"},
        headers={"X-Request-ID": request_id},
        timeout=10,
    )

    assert response.status_code == 200, f"Input Processor failed: {response.text}"

    # Also make embedding request to generate more logs
    response = requests.post(
        f"{EMBEDDING_URL}/embed",
        json={"text": "test query for logging"},
        headers={"X-Request-ID": request_id},
        timeout=10,
    )

    assert response.status_code == 200, f"Embedding failed: {response.text}"

    # Call /track/{request_id} on Gateway
    response = requests.get(f"{GATEWAY_URL}/track/{request_id}", timeout=10)

    assert response.status_code == 200, f"Track request failed: {response.text}"
    data = response.json()

    # Check response structure
    assert "request_id" in data
    assert data["request_id"] == request_id
    assert "services" in data
    assert "timeline" in data

    services = data["services"]
    timeline = data["timeline"]

    # We should have logs from Input Processor and Embedding
    # (NOT from Small LLM, Fine-Tuned Model, or Reformulator - they don't have /logs endpoint)
    assert "input-processor" in services or len(services) > 0

    # Check that we have some logs
    assert len(timeline) > 0

    # Verify timeline structure
    for entry in timeline:
        assert "service" in entry
        assert "log" in entry
        assert len(entry["log"]) > 0

    print(f"\n✓ Request ID Propagation:")
    print(f"  Request ID: {request_id}")
    print(f"  Services with logs: {list(services.keys())}")
    print(f"  Total log entries: {len(timeline)}")

    # Print which services we got logs from
    for service_name in services:
        log_count = services[service_name]["log_count"]
        print(f"    - {service_name}: {log_count} logs")


@pytest.mark.integration
@pytest.mark.slow
def test_metrics_are_recorded(mock_external_apis):
    """
    Test: Prometheus metrics are recorded correctly

    This test verifies:
    - Request to Gateway generates metrics (mocked by default)
    - /metrics endpoint returns Prometheus format
    - Expected metrics exist (cache, LLM calls, HTTP requests)

    Use --use-real-apis flag for real LLM calls (takes 30-60 seconds)
    """
    # Make a request to generate metrics
    response = requests.post(
        f"{GATEWAY_URL}/v1/chat/completions",
        json={
            "model": "math-tutor",
            "messages": [{"role": "user", "content": "What is 5+3?"}],
        },
        timeout=120,
    )

    assert response.status_code == 200, f"Gateway failed: {response.text}"

    # Check Gateway's /metrics endpoint
    response = requests.get(f"{GATEWAY_URL}/metrics", timeout=10)

    assert response.status_code == 200, f"Metrics endpoint failed"
    metrics_text = response.text

    # Verify Prometheus format (starts with # HELP or metric names)
    assert len(metrics_text) > 0
    assert "# HELP" in metrics_text or "# TYPE" in metrics_text

    # Verify expected metrics exist
    # We should have at least one of these metrics
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

    print(f"\n✓ Metrics Recording:")
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
