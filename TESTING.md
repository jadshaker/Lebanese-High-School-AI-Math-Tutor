# Testing Guide

## Prerequisites

1. Start all services:
```bash
docker compose up --build
```

2. Ensure HPC SSH tunnel is active (for Small LLM and Fine-tuned Model):
```bash
ssh -L 0.0.0.0:11434:localhost:11434 username@octopus.aub.edu.lb -t ssh -L 11434:localhost:11434 node_name
```

---

## Layer 1: Individual Service Health Checks

Test each service is running and healthy:

```bash
# Phase 2 Services
curl http://localhost:8001/health  # Large LLM
curl http://localhost:8002/health  # Embedding
curl http://localhost:8003/health  # Cache
curl http://localhost:8005/health  # Small LLM
curl http://localhost:8006/health  # Fine-tuned Model

# Phase 1 Services
curl http://localhost:8004/health  # Input Processor
curl http://localhost:8007/health  # Reformulator

# Orchestrators
curl http://localhost:8008/health  # Answer Retrieval Service
curl http://localhost:8009/health  # Data Processing Service

# Gateway
curl http://localhost:8000/health  # Gateway
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

## Layer 3: Orchestrator Services

### Test Data Processing Service (8009)

```bash
curl -X POST http://localhost:8009/process-query \
  -H "Content-Type: application/json" \
  -d '{
    "input": "  what is derivative of x squared  ",
    "type": "text"
  }'
```

**Expected:**
```json
{
  "reformulated_query": "What is the derivative of x^2?",
  "original_input": "  what is derivative of x squared  ",
  "input_type": "text",
  "processing_metadata": {
    "input_processor": {...},
    "reformulator": {...}
  }
}
```

### Test Answer Retrieval Service (8008)

```bash
curl -X POST http://localhost:8008/retrieve-answer \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the derivative of x^2?"
  }'
```

**Expected:**
```json
{
  "answer": "The derivative is 2x",
  "source": "small_llm" | "large_llm",
  "used_cache": true | false
}
```

---

## Layer 4: End-to-End via Gateway ✅

**Gateway is now updated and orchestrates the complete pipeline!**

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
  "services": {
    "data_processing": {
      "status": "healthy",
      "details": {
        "dependencies": {
          "input_processor": "healthy",
          "reformulator": "healthy"
        }
      }
    },
    "answer_retrieval": {
      "status": "healthy",
      "details": {
        "dependencies": {
          "embedding": "healthy",
          "cache": "healthy",
          "small_llm": "healthy",
          "large_llm": "healthy"
        }
      }
    }
  }
}
```

### Complete Pipeline Flow

When you call Gateway `/query`, here's what happens:

1. **Phase 1 - Data Processing (8009)**:
   - Calls Input Processor (8004) → processes text/image
   - Calls Reformulator (8007) → improves question clarity
   - Returns reformulated query

2. **Phase 2 - Answer Retrieval (8008)**:
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
docker compose logs -f data-processing
docker compose logs -f answer-retrieval
docker compose logs -f gateway
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

1. If individual services work → Test orchestrators
2. If orchestrators work → Update Gateway (Task #85)
3. If Gateway works → Build UI (Task #77)
4. Full end-to-end testing with UI
