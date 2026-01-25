# Testing Guide

This guide covers testing practices for the Lebanese High School AI Math Tutor project.

## Testing Philosophy

### Why We Test

- **Confidence**: Tests verify that code works as intended and continues to work after changes
- **Maintainability**: Tests document expected behavior and catch regressions
- **Documentation**: Tests serve as executable examples of how the code should be used

### Test Pyramid

We follow the test pyramid approach:

```
    /\
   /E2E\      Few end-to-end tests (slow, fragile, high value)
  /-----\
 /INTEG \     Some integration tests (medium speed, medium value)
/---------\
/   UNIT   \  Many unit tests (fast, stable, focused)
-----------
```

- **Many unit tests**: Fast, isolated, mock everything external
- **Fewer integration tests**: Test service interactions, require Docker
- **Few E2E tests**: Full pipeline validation, require HPC connection

---

## Running Tests

### Quick Start

**Run all tests:**
```bash
python3.14 cli.py test
```

**Run specific test types:**
```bash
# Unit tests only (fast, no external dependencies)
python3.14 cli.py test -- -m unit

# Integration tests (requires all services running via Docker)
python3.14 cli.py test -- -m integration

# E2E tests (requires full stack + HPC connection)
python3.14 cli.py test -- -m e2e
```

**Run tests with coverage:**
```bash
# Coverage for all services
python3.14 cli.py test -- --cov=services --cov-report=html

# View coverage report
open htmlcov/index.html
```

**Run specific test file:**
```bash
python3.14 cli.py test -- tests/unit/test_services/test_gateway.py
```

**Run tests matching a pattern:**
```bash
# Run all tests with "embedding" in the name
python3.14 cli.py test -- -k embedding

# Run all tests in a specific module
python3.14 cli.py test -- tests/unit/test_services/test_embedding.py::TestEmbeddingService
```

### Test Markers

Tests are marked with pytest markers to categorize them:

- `@pytest.mark.unit`: Fast, isolated unit tests with mocked dependencies
- `@pytest.mark.integration`: Tests requiring Docker services
- `@pytest.mark.e2e`: Full pipeline tests requiring HPC connection

---

## Prerequisites for Different Test Types

### Unit Tests

**No external dependencies required.**

Unit tests mock all external services and APIs, so they can run anywhere without Docker or HPC access.

### Integration Tests

**Requirements:**

1. Start all services:
```bash
docker compose up --build
```

2. Ensure services are healthy:
```bash
curl http://localhost:8000/health
```

### E2E Tests

**Requirements:**

1. Start all services (same as integration tests)

2. Ensure HPC SSH tunnel is active (for Small LLM and Fine-tuned Model):
```bash
ssh -L 0.0.0.0:11434:localhost:11434 username@octopus.aub.edu.lb -t ssh -L 11434:localhost:11434 node_name
```

3. Verify models are loaded on HPC:
```bash
# On the HPC node
module load ollama
ollama run deepseek-r1:7b --keepalive -1m
ollama run tinyllama:latest --keepalive -1m
```

---

## Unit Testing Guidelines

### What to Test in Unit Tests

Unit tests should focus on:

- **Business logic**: Validate algorithms, data transformations, decision-making
- **Request/response handling**: Ensure endpoints parse inputs and format outputs correctly
- **Error handling**: Verify that invalid inputs raise appropriate exceptions
- **Edge cases**: Test boundary conditions, empty inputs, unusual values

### How to Mock External Dependencies

Unit tests should mock ALL external dependencies:

- **OpenAI API calls**: Mock `openai.ChatCompletion.create()` or `openai.Embedding.create()`
- **Ollama API calls**: Mock `openai.ChatCompletion.create()` (for Ollama's OpenAI-compatible API)
- **Inter-service calls**: Mock `urllib.request.urlopen()` or use `unittest.mock.patch()`
- **Environment variables**: Mock `os.getenv()` or use `monkeypatch` fixture

### Example Unit Test Walkthrough

**File**: `tests/unit/test_services/test_embedding.py`

```python
import pytest
from unittest.mock import patch, MagicMock

@pytest.mark.unit
def test_embed_endpoint_success():
    """Test that /embed endpoint returns correct response"""
    # Mock OpenAI API
    with patch('openai.Embedding.create') as mock_create:
        # Configure mock to return fake embedding
        mock_create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1, 0.2, 0.3])]
        )

        # Make request to endpoint
        from services.embedding.src.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)

        response = client.post("/embed", json={"text": "test query"})

        # Assert response
        assert response.status_code == 200
        assert "embedding" in response.json()
        assert len(response.json()["embedding"]) == 3
```

**Key points:**
- Uses `@pytest.mark.unit` marker
- Mocks external OpenAI API call
- Tests only the endpoint logic, not actual API behavior
- Fast (no network calls)

---

## Integration Testing Guidelines

### When to Write Integration Tests

Write integration tests to verify:

- **Service-to-service communication**: Does Gateway correctly call Embedding service?
- **End-to-end flows**: Does the full pipeline work with real services?
- **Data flow**: Are requests and responses correctly transformed across services?

### Docker Setup Requirements

Integration tests require all services running in Docker:

```bash
# Start all services
docker compose up --build -d

# Verify services are healthy
curl http://localhost:8000/health
```

### HPC Connection Requirements for Ollama Services

Integration tests that use `small_llm` or `fine_tuned_model` services require:

1. **SSH tunnel to HPC** (see Prerequisites section above)
2. **Models loaded in Ollama** on the HPC node

**Alternative**: Mock Ollama responses in integration tests to avoid HPC dependency.

### Example Integration Test

**File**: `tests/integration/test_gateway_pipeline.py`

```python
import pytest
import requests

@pytest.mark.integration
def test_gateway_query_endpoint():
    """Test Gateway /query endpoint with real services"""
    # Make request to Gateway (assumes Docker services are running)
    response = requests.post(
        "http://localhost:8000/query",
        json={"input": "what is derivative of x^2", "type": "text"}
    )

    # Assert response structure
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "source" in data
    assert "metadata" in data
```

**Key points:**
- Uses `@pytest.mark.integration` marker
- Makes real HTTP requests to Docker services
- Tests actual service communication
- Slower than unit tests (network calls)

---

## E2E Testing Guidelines

### When E2E Tests Are Appropriate

Write E2E tests for:

- **Critical user journeys**: Full pipeline from input to answer
- **High-value scenarios**: Common question types, edge cases
- **Regression protection**: Verify that major features continue to work

### Full Stack Requirements

E2E tests require:

1. All services running in Docker
2. HPC SSH tunnel active
3. Ollama models loaded on HPC
4. Valid OpenAI API key

### Note About HPC SSH Tunnel Requirement

E2E tests are the only test type that require HPC access because they test the full pipeline including Ollama models. Unit and integration tests can run without HPC by mocking Ollama responses.

### Example E2E Test

**File**: `tests/e2e/test_full_pipeline.py`

```python
import pytest
import requests

@pytest.mark.e2e
def test_full_pipeline_with_reformulation():
    """Test complete pipeline: Input Processor -> Reformulator -> Embedding -> Cache -> LLM"""
    # Make request with messy input (tests reformulation)
    response = requests.post(
        "http://localhost:8000/query",
        json={
            "input": "  whats   derivative   of x   squared  ",
            "type": "text"
        }
    )

    # Assert successful response
    assert response.status_code == 200
    data = response.json()

    # Validate full pipeline metadata
    assert "metadata" in data
    assert "processing" in data["metadata"]
    assert "phase1" in data["metadata"]["processing"]
    assert "phase2" in data["metadata"]["processing"]

    # Validate reformulation happened
    assert "reformulated_query" in data["metadata"]
    assert "x²" in data["metadata"]["reformulated_query"] or "x^2" in data["metadata"]["reformulated_query"]
```

**Key points:**
- Uses `@pytest.mark.e2e` marker
- Tests full pipeline with real services and HPC
- Validates complete request/response cycle
- Slowest test type (multiple service calls + LLM inference)

---

## Common Testing Patterns

### Mocking OpenAI API

```python
from unittest.mock import patch, MagicMock

@pytest.mark.unit
def test_with_mocked_openai():
    with patch('openai.ChatCompletion.create') as mock_create:
        # Configure mock response
        mock_create.return_value = MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(content="The derivative is 2x")
                )
            ]
        )

        # Your test code here
        # ...
```

### Mocking Ollama (OpenAI-compatible API)

Ollama uses the OpenAI-compatible API, so mock it the same way:

```python
from unittest.mock import patch, MagicMock

@pytest.mark.unit
def test_with_mocked_ollama():
    with patch('openai.ChatCompletion.create') as mock_create:
        # Configure mock response
        mock_create.return_value = MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(content="<think>reasoning</think>\nAnswer: 2x")
                )
            ]
        )

        # Your test code here
        # ...
```

### Mocking Inter-Service Calls

```python
from unittest.mock import patch, MagicMock
import json

@pytest.mark.unit
def test_with_mocked_service_call():
    with patch('urllib.request.urlopen') as mock_urlopen:
        # Configure mock response
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "processed_input": "test",
            "input_type": "text"
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Your test code here
        # ...
```

### Testing Async Endpoints

```python
import pytest
from fastapi.testclient import TestClient
from services.gateway.src.main import app

@pytest.mark.unit
def test_async_endpoint():
    client = TestClient(app)
    response = client.post("/query", json={"input": "test", "type": "text"})
    assert response.status_code == 200
```

**Note**: `TestClient` handles async endpoints automatically.

---

## Troubleshooting

### Common Test Failures and Fixes

**1. `ModuleNotFoundError: No module named 'src'`**

**Cause**: Python can't find the service source code.

**Fix**: Ensure you're running tests from the project root:
```bash
cd /path/to/Lebanese-High-School-AI-Math-Tutor
python3.14 cli.py test
```

**2. `Connection refused` errors in integration tests**

**Cause**: Docker services are not running.

**Fix**: Start services before running integration tests:
```bash
docker compose up --build -d
python3.14 cli.py test -- -m integration
```

**3. `Timeout` errors when testing Small LLM or Fine-tuned Model**

**Cause**: HPC SSH tunnel is not active or Ollama is not running.

**Fix**:
```bash
# Check SSH tunnel
lsof -i :11434

# Re-establish tunnel if needed
ssh -L 0.0.0.0:11434:localhost:11434 username@octopus.aub.edu.lb -t ssh -L 11434:localhost:11434 node_name

# Verify Ollama is responding
curl http://localhost:11434/api/tags
```

**4. `OpenAI API key not found` in unit tests**

**Cause**: Unit tests should mock OpenAI, but mock is not configured.

**Fix**: Add mock for OpenAI API:
```python
with patch('openai.ChatCompletion.create') as mock_create:
    # Configure mock
    # ...
```

**5. Tests pass locally but fail in CI**

**Cause**: CI doesn't have access to Docker or HPC.

**Fix**: Only run unit tests in CI (see `.github/workflows/pre-merge-checks.yml`):
```bash
python3.14 cli.py test -- -m unit
```

### HPC Connection Issues

**Symptom**: Tests timeout when calling Small LLM or Fine-tuned Model.

**Diagnosis**:
```bash
# Check if tunnel is active
lsof -i :11434

# Test Ollama directly
curl http://localhost:11434/api/tags

# Expected output: List of loaded models
```

**Fix**:
- Ensure SSH tunnel is running with `0.0.0.0` binding (not `localhost`)
- Verify Ollama is running on HPC node
- Check that models are loaded with `--keepalive -1m`

### Docker Networking Issues

**Symptom**: Services can't communicate with each other.

**Diagnosis**:
```bash
# Check if all services are running
docker compose ps

# Check service logs
docker compose logs gateway
docker compose logs embedding

# Test inter-service communication
docker compose exec gateway curl http://embedding:8002/health
```

**Fix**:
- Ensure all services are in the same Docker network (`math-tutor-network`)
- Verify service URLs use internal Docker names (e.g., `http://embedding:8002`)
- Restart services: `docker compose restart`

---

## Layer 1: Individual Service Health Checks

Test each service is running and healthy:

```bash
# Gateway
curl http://localhost:8000/health  # Gateway (orchestrates all services)

# LLM Services
curl http://localhost:8001/health  # Large LLM
curl http://localhost:8005/health  # Small LLM
curl http://localhost:8006/health  # Fine-tuned Model

# Supporting Services
curl http://localhost:8002/health  # Embedding
curl http://localhost:8003/health  # Cache
curl http://localhost:8004/health  # Input Processor
curl http://localhost:8007/health  # Reformulator
```

**Expected:** All return `{"status": "healthy", ...}`

---

## Layer 2: Individual Service Functionality

### Test Input Processor (8004)

**Text input:**
```bash
curl -X POST http://localhost:8004/process \
  -H "Content-Type: application/json" \
  -d '{
    "input": "  what is   derivative of x squared  ",
    "type": "text"
  }'
```

**Expected:**
```json
{
  "processed_input": "what is derivative of x squared",
  "input_type": "text",
  "metadata": {
    "original_length": 40,
    "processed_length": 33,
    "preprocessing_applied": ["strip_whitespace", "normalize_spacing"]
  }
}
```

**Image input (stub):**
```bash
curl -X POST http://localhost:8004/process \
  -H "Content-Type: application/json" \
  -d '{
    "input": "base64_image_data_here",
    "type": "image"
  }'
```

**Expected:**
```json
{
  "processed_input": "Image input received",
  "input_type": "image",
  "metadata": {
    "note": "Image processing not yet implemented",
    ...
  }
}
```

### Test Reformulator (8007)

```bash
curl -X POST http://localhost:8007/reformulate \
  -H "Content-Type: application/json" \
  -d '{
    "processed_input": "what is derivative of x squared",
    "input_type": "text"
  }'
```

**Expected:**
```json
{
  "reformulated_query": "What is the derivative of x^2?",
  "original_input": "what is derivative of x squared",
  "improvements_made": ["standardized notation", "added clarity", ...]
}
```

### Test Embedding Service (8002)

```bash
curl -X POST http://localhost:8002/embed \
  -H "Content-Type: application/json" \
  -d '{
    "text": "What is the derivative of x^2?"
  }'
```

**Expected:**
```json
{
  "embedding": [0.0234, -0.0521, ...],  // Array of 1536 floats
  "model": "text-embedding-3-small",
  "dimensions": 1536
}
```

### Test Cache Service (8003)

**Similarity search (stub):**
```bash
curl -X POST http://localhost:8003/similarity-search \
  -H "Content-Type: application/json" \
  -d '{
    "embedding": [0.1, 0.2, 0.3, ...],
    "k": 5
  }'
```

**Expected:** Stub response with top-k similar results

### Test Small LLM (8005)

```bash
curl -X POST http://localhost:8005/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the derivative of x^2?",
    "cached_results": []
  }'
```

**Expected:**
```json
{
  "answer": "...",
  "confidence": 0.85,
  "is_exact_match": true
}
```

### Test Large LLM (8001)

```bash
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the derivative of x^2?"
  }'
```

**Expected:**
```json
{
  "answer": "The derivative of x^2 is 2x. This is found using the power rule..."
}
```

---

## Layer 3: End-to-End via Gateway ✅

**Gateway orchestrates the complete two-phase pipeline directly!**

### Test 1: Simple Math Question (Text Input)

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "input": "what is derivative of x squared",
    "type": "text"
  }'
```

**Expected:**
```json
{
  "answer": "The derivative of x^2 is 2x...",
  "source": "small_llm" or "large_llm",
  "used_cache": true or false,
  "metadata": {
    "input_type": "text",
    "original_input": "what is derivative of x squared",
    "reformulated_query": "What is the derivative of x^2?",
    "processing": {
      "phase1": {
        "input_processor": {
          "preprocessing_applied": ["strip_whitespace", "normalize_spacing"]
        },
        "reformulator": {
          "improvements_made": ["standardized notation", "added clarity"]
        }
      },
      "phase2": {
        "cache_similarity": 0.95,
        "llm_used": "small_llm"
      }
    }
  }
}
```

### Test 2: Complex Math Question

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "input": "solve the integral of sin(x) dx",
    "type": "text"
  }'
```

### Test 3: Messy Input (Tests Reformulation)

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "input": "  whats  the   limit    of 1/x   as x approaches   infinity  ",
    "type": "text"
  }'
```

**This tests:**
- Input Processor cleans up extra whitespace
- Reformulator improves question structure
- Full pipeline returns clean answer

### Test 4: Gateway Health Check

```bash
curl http://localhost:8000/health
```

**Expected:**
```json
{
  "status": "healthy",
  "service": "gateway",
  "dependencies": {
    "input_processor": "healthy",
    "reformulator": "healthy",
    "embedding": "healthy",
    "cache": "healthy",
    "small_llm": "healthy",
    "large_llm": "healthy"
  }
}
```

### Complete Pipeline Flow

When you call Gateway `/query`, here's what happens:

1. **Phase 1 - Data Processing** (Gateway orchestrates directly):
   - Calls Input Processor (8004) → processes text/image
   - Calls Reformulator (8007) → improves question clarity

2. **Phase 2 - Answer Retrieval** (Gateway orchestrates directly):
   - Calls Embedding (8002) → creates vector embedding
   - Calls Cache (8003) → searches for similar Q&A pairs
   - Calls Small LLM (8005) → attempts answer with cache context
   - If confidence < 0.95, calls Large LLM (8001) → gets fresh answer
   - Saves new answer to cache

3. **Gateway combines results**:
   - Merges metadata from both phases
   - Returns complete response with full traceability

---

## Debugging Tips

### View service logs:
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f gateway
docker compose logs -f small-llm
docker compose logs -f embedding
```

### Check service status:
```bash
docker compose ps
```

### Restart a service:
```bash
docker compose restart <service-name>
```

### View real-time container stats:
```bash
docker stats
```

---

## Common Issues

1. **Service not responding:**
   - Check if container is running: `docker compose ps`
   - Check logs: `docker compose logs <service-name>`
   - Verify port is exposed in docker-compose.yml

2. **Small LLM/Fine-tuned Model timeout:**
   - Verify SSH tunnel is active
   - Check Ollama is running on HPC: `curl http://localhost:11434/api/tags`
   - Verify models are loaded

3. **Inter-service communication fails:**
   - Services must use internal Docker network names (e.g., `http://embedding:8002`)
   - Check docker-compose.yml network configuration

4. **OpenAI API errors (Large LLM/Embedding):**
   - Verify OPENAI_API_KEY in .env file
   - Check API quota/limits

---

## Next Steps After Testing

1. If individual services work → Test Gateway end-to-end
2. If Gateway works → Build UI (Task #77)
3. Full end-to-end testing with UI
