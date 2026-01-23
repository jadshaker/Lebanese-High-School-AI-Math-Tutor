# Architecture Implementation Plan

## Service Ports

### External
- **3000** - UI (user-facing frontend)

### Internal Services
- **8000** - Gateway (orchestrator)
- **8001** - Large LLM (OpenAI GPT-4) ✅ *exists*
- **8002** - Embedding service ✅ *exists*
- **8003** - Cache service (vector storage + fine-tuned model integration) ✅ *exists (stub)*
- **8004** - Input Processor
- **8005** - Small LLM (Ollama/DeepSeek-R1) ✅ *exists*
- **8006** - Fine-tuned model (used internally by cache) ✅ *exists*
- **8007** - Reformulator
- **8008** - Answer Retrieval Service (orchestrates Phase 2)

---

## Implementation Order

### Main Tasks (In Order)
1. **Setup Final Answer Retrieval** (#76) - Foundation services
2. **Setup Data Processing** (#75) - Input pipeline
3. **Update Gateway** (#85) - Orchestrate full flow
4. **Implement Full Cache** - Vector storage with fine-tuned model
5. **Use vllm instead of ollama** (#69) - Performance optimization
6. **Setup Kubernetes** (#74) - Production deployment

---

## Current Task: Setup Final Answer Retrieval (#76)

### Sub-Issues (In Order)

**Start with (parallel):**
1. ✅ **#83 - Check Small LLM**
   - Verify small_llm service works correctly
   - Test with sample math queries
   - Ensure Ollama/DeepSeek-R1 connection is stable

2. ✅ **#84 - Check Large LLM**
   - Verify large_llm service works correctly
   - Test OpenAI GPT-4 integration
   - Confirm API key and responses

**Then:**
3. **#80 - Setup Embedding Service**
   - Create embedding service (port 8002)
   - OpenAI text-embedding-3-small integration
   - Health check endpoint
   - Embed endpoint for text → vector conversion

4. **#81 - Cache Service (Stub Version)**
   - Create cache service (port 8003)
   - Stub responses for similarity search
   - Stub responses for save operations
   - Health check endpoint
   - Interface for embedding integration (not fully functional yet)

**Skip for now (will do in Task 4):**
5. **#82 - Setup Fine-tuned Model**
   - Deferred to full cache implementation

**Final Step:**
6. **Create Answer Retrieval Orchestration Endpoint**
   - New service: Answer Retrieval Service (port 8008)
   - Orchestrates the complete Phase 2 flow
   - See detailed plan below

---

## Answer Retrieval Service (Port 8008)

**Purpose:** Orchestrates Phase 2 (Final Answer Retrieval) by coordinating Embedding → Cache → Small LLM → Large LLM.

### Endpoint: `/retrieve-answer`

**Request Format:**
```json
{
  "query": "What is the derivative of x^2?"
}
```

**Response Format:**
```json
{
  "answer": "The derivative is 2x",
  "source": "small_llm" | "large_llm",
  "used_cache": true | false
}
```

### Flow Implementation

**Input:** User query (text)

1. **Embed Query**
   - Call: `POST /embed` to Embedding Service (8002)
   - Input: `{ "text": "query text" }`
   - Output: Vector embedding `[0.123, -0.456, ...]`

2. **Search Cache**
   - Call: `POST /similarity-search` to Cache Service (8003)
   - Input: `{ "embedding": [...], "k": 5 }`
   - Output: Top-k similar Q&A pairs
   - **Note:** k=5 (make this configurable in config)

3. **Try Small LLM**
   - Call: `POST /query` to Small LLM (8005)
   - Input: `{ "query": "original query", "cached_results": [...] }`
   - Output: `{ "answer": "..." | null, "confidence": 0.0-1.0, "is_exact_match": true/false }`
   - **IMPORTANT:** Small LLM service needs to be updated to return this format

4. **Decision Point**
   ```
   IF is_exact_match == true AND answer is not null:
       - Return Small LLM answer
       - Set source = "small_llm"
       - Set used_cache = true
   ELSE:
       - Go to step 5 (Large LLM)
   ```

5. **Call Large LLM** (if no exact match)
   - Call: `POST /query` to Large LLM (8001)
   - Input: `{ "query": "original query" }`
   - Instruction: Ask for final answer only
   - Output: `{ "answer": "..." }`

6. **Save to Cache** (after Large LLM)
   - Generate embedding for the answer
   - Call: `POST /save` to Cache Service (8003)
   - Input: `{ "query": "...", "answer": "...", "embedding": [...] }`
   - Set source = "large_llm"
   - Set used_cache = false

7. **Return Response**
   - Return final answer with metadata

### Configuration

```python
class Config:
    CACHE_TOP_K = int(os.getenv("CACHE_TOP_K", "5"))

    class SERVICES:
        EMBEDDING_URL = os.getenv("EMBEDDING_SERVICE_URL", "http://embedding:8002")
        CACHE_URL = os.getenv("CACHE_SERVICE_URL", "http://cache:8003")
        SMALL_LLM_URL = os.getenv("SMALL_LLM_SERVICE_URL", "http://small-llm:8005")
        LARGE_LLM_URL = os.getenv("LARGE_LLM_SERVICE_URL", "http://large-llm:8001")
```

### Dependencies

**Must be completed first:**
- ✅ Embedding Service (8002)
- ✅ Cache Service (8003) - stub version is fine
- ✅ Small LLM (8005)
- ✅ Large LLM (8001)

**Must be updated:**
- ⚠️ Small LLM service needs to accept `cached_results` and return `{ answer, confidence, is_exact_match }`

### Notes for Implementation

- Use Python's `urllib` for inter-service communication (per CLAUDE.md)
- Add health check endpoint
- Follow service structure pattern
- Handle errors gracefully (service unavailable, timeout, etc.)
- Add logging for debugging the flow

---

## Phase 1: Data Processing

**Flow:** UI → Gateway → Input Processor → Reformulator → processed input

### Components
1. **UI Service (3000)**
   - User interface for inputting questions
   - Sends requests to Gateway

2. **Input Processor (8004)**
   - Text input processor
   - Image processor (stub: returns sample response acknowledging image)
   - Outputs: processed user input

3. **Reformulator (8007)**
   - Reformulates user questions for better understanding
   - Outputs: reformulated query

---

## Phase 2: Final Answer Retrieval

**Flow:** processed input → Embedding → Cache (similarity search) → Small LLM → [conditional] → Large LLM

### Components
1. **Embedding Service (8002)**
   - Converts text to embeddings
   - Used for cache similarity search
   - Used for saving new answers to vector cache

2. **Cache Service (8003)**
   - Vector storage with cosine similarity search
   - Returns top-k similar previous answers
   - Integrates with fine-tuned model (8006)
   - **For now:** Returns stub/dummy responses (not fully functional)

3. **Fine-tuned Model (8006)**
   - Used internally by cache service
   - Assists with cache operations

4. **Small LLM (8005)** ✅
   - First attempt at answering with cached results
   - Determines if exact match found

5. **Large LLM (8001)** ✅
   - Called only if no exact match from small LLM
   - Generates final answer
   - Answer saved to cache + vector cache

### Decision Points
- **2.1 Exact Match:** Save final answer in conversation context
- **2.2 No Exact Match:**
  - Call Large LLM for final answer
  - Save answer to cache
  - Generate embedding and save to vector cache

---

## Phase 3: Tutoring Cache


**Status:** Stub implementation only

### Components
- Endpoint on Cache Service (8003)
- Returns false/no data response (cache not populated yet)
- Full implementation planned for later

---

## Gateway Updates (8000)

**Status:** Existing service requires major refactor

### Required Changes
1. **New endpoints/flow:**
   - Accept requests from UI (3000)
   - Route to Input Processor (8004)
   - Route to Reformulator (8007)
   - Orchestrate Embedding (8002) → Cache (8003) → Small LLM (8005)
   - Conditionally call Large LLM (8001) based on match results

2. **Decision logic:**
   - Evaluate if Small LLM found exact match
   - Route to Large LLM if no exact match
   - Manage conversation context storage

3. **Cache integration:**
   - Send final answers to Cache service for storage
   - Trigger embedding generation for vector cache
   - Handle Tutoring Cache endpoint calls

---

## Implementation Notes

- Large LLM and Small LLM services already implemented
- Focus on creating new services with stub/sample responses first
- Cache service returns dummy data for now
- All new services need health check endpoints
- Follow service structure pattern from CLAUDE.md
