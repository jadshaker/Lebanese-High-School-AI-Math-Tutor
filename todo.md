# Architecture Implementation Plan

## Service Ports

### External
- **3000** - UI (user-facing frontend)

### Internal Services
- **8000** - Gateway (orchestrator)
- **8001** - Large LLM (OpenAI GPT-4) ✅ *exists*
- **8002** - Embedding service
- **8003** - Cache service (vector storage + fine-tuned model integration)
- **8004** - Input Processor
- **8005** - Small LLM (Ollama/DeepSeek-R1) ✅ *exists*
- **8006** - Fine-tuned model (used internally by cache)
- **8007** - Reformulator

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
