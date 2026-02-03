# Merge Plan: Main + Branch 35 + Small LLM Optimization

## Executive Summary

This document outlines how to merge the strengths of both branches and optimize the system with intelligent Small LLM routing.

**Goal**: Create a production-ready system with:
- Real vector caching (Qdrant)
- Stateful tutoring sessions
- Cost-optimized LLM routing (Small LLM first, Large LLM fallback)
- Full observability and testing

---

## Part 1: What to Keep from Each Branch

### From Main Branch (Keep)

| Component | Reason |
|-----------|--------|
| **Observability stack** | Prometheus, Grafana, structured logging - production-ready |
| **Testing framework** | 93 tests (unit + integration + E2E) |
| **Input Processor service** | Text/image preprocessing (expandable for OCR) |
| **Fine-Tuned Model service** | Specialized math model (TinyLlama) |
| **OpenAI-compatible API** | `/v1/chat/completions` - works with Open WebUI |
| **CI/CD workflows** | `pre-merge-checks.yml`, `run-tests.yml` |
| **Request ID tracing** | Cross-service debugging |
| **Middleware patterns** | Logging + metrics middleware template |

### From Branch 35 (Port Over)

| Component | Reason |
|-----------|--------|
| **Vector Cache + Qdrant** | Real vector storage with interaction graphs |
| **Session service** | Stateful multi-turn conversations |
| **Intent Classifier service** | Skip detection, understanding classification |
| **Confidence routing** | 4-tier system for cache/LLM selection |
| **Tutoring flow** | Socratic dialogue with incremental caching |
| **Context summarization** | Two-step reformulation with context |

### Discard

| Component | Reason |
|-----------|--------|
| Cache stub (Main) | Replace with real Qdrant implementation |
| Custom UI (Branch 35) | Use Open WebUI instead |
| `.env` committed (Branch 35) | Security issue |

---

## Part 2: Merged Architecture

### Services (11 total)

| Service | Port | Source | Description |
|---------|------|--------|-------------|
| **Gateway** | 8000 | Merged | OpenAI-compatible + session-aware + tutoring |
| **Large LLM** | 8001 | Main | OpenAI GPT-4o-mini (complex/final answers) |
| **Embedding** | 8002 | Main | OpenAI text-embedding-3-small |
| **Vector Cache** | 8003 | Branch 35 | Qdrant-backed with interaction graphs |
| **Input Processor** | 8004 | Main | Text/image preprocessing |
| **Small LLM** | 8005 | Main | Ollama DeepSeek-R1 (fast/cheap inference) |
| **Fine-Tuned Model** | 8006 | Main | Ollama TinyLlama (domain-specific) |
| **Reformulator** | 8007 | Merged | Query improvement + context summarization |
| **Session** | 8008 | Branch 35 | Stateful conversation management |
| **Intent Classifier** | 8009 | Branch 35 | Rule + LLM hybrid classification |
| **Qdrant** | 6333 | Branch 35 | Vector database container |

### Infrastructure

| Component | Source |
|-----------|--------|
| Prometheus | Main |
| Grafana | Main |
| Open WebUI | Main |
| Qdrant | Branch 35 |

---

## Part 3: Optimized Pipeline with Small LLM

### Key Insight

**Small LLM (DeepSeek-R1:7b)** is:
- ~10x faster than Large LLM
- Free (runs on HPC)
- Good enough for 70%+ of tasks

**Large LLM (GPT-4o-mini)** should only be used for:
- Complex multi-step problems
- Final validation of uncertain answers
- New content generation for caching

### Optimized Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PHASE 1: DATA PROCESSING                           │
└─────────────────────────────────────────────────────────────────────────────┘

User Query
    │
    ├──→ [Input Processor] ─────→ Cleaned text
    │        (Port 8004)
    │
    └──→ [Session Service] ─────→ Create/Get session
             (Port 8008)           Store original_query
                │
                ▼
         [Reformulator] ────────→ Reformulated query + lesson
           (Port 8007)
                │
                │  ┌─────────────────────────────────────────────┐
                └──│  USES: Small LLM (Port 8005)                │
                   │  - Context summarization (if follow-up)     │
                   │  - Query reformulation                       │
                   │  - Lesson identification                     │
                   └─────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                        PHASE 2: ANSWER RETRIEVAL                            │
└─────────────────────────────────────────────────────────────────────────────┘

Reformulated Query
    │
    ├──→ [Embedding Service] ───→ 1536-dim vector
    │        (Port 8002)
    │
    └──→ [Vector Cache] ────────→ Search results (top-3)
           (Port 8003)
                │
                ▼
    ┌───────────────────────────────────────────────────────────────────────┐
    │                    CONFIDENCE ROUTING (NEW)                           │
    │                                                                       │
    │  ┌─────────────────────────────────────────────────────────────────┐ │
    │  │  TIER 1: EXACT MATCH (score ≥ 0.95)                             │ │
    │  │  ────────────────────────────────────────────────────────────── │ │
    │  │  → Return cached answer directly                                │ │
    │  │  → Source: "cache"                                              │ │
    │  │  → LLM calls: 0                                                 │ │
    │  └─────────────────────────────────────────────────────────────────┘ │
    │                                                                       │
    │  ┌─────────────────────────────────────────────────────────────────┐ │
    │  │  TIER 2: HIGH CONFIDENCE (0.85 ≤ score < 0.95)                  │ │
    │  │  ────────────────────────────────────────────────────────────── │ │
    │  │  → Small LLM validates/adapts cached answer                     │ │
    │  │  → Prompt: "User asked X. Similar Q had answer Y. Adapt."       │ │
    │  │  → Source: "small_llm"                                          │ │
    │  │  → LLM calls: 1 (Small)                                         │ │
    │  └─────────────────────────────────────────────────────────────────┘ │
    │                                                                       │
    │  ┌─────────────────────────────────────────────────────────────────┐ │
    │  │  TIER 3: MEDIUM CONFIDENCE (0.70 ≤ score < 0.85)                │ │
    │  │  ────────────────────────────────────────────────────────────── │ │
    │  │  → Small LLM generates with cache context                       │ │
    │  │  → Prompt: "Use context from similar Q&A to answer."            │ │
    │  │  → Source: "small_llm"                                          │ │
    │  │  → LLM calls: 1 (Small)                                         │ │
    │  └─────────────────────────────────────────────────────────────────┘ │
    │                                                                       │
    │  ┌─────────────────────────────────────────────────────────────────┐ │
    │  │  TIER 4: LOW CONFIDENCE (0.50 ≤ score < 0.70)                   │ │
    │  │  ────────────────────────────────────────────────────────────── │ │
    │  │  → Try Fine-Tuned Model first (domain-specific)                 │ │
    │  │  → If confidence low → escalate to Large LLM                    │ │
    │  │  → Source: "fine_tuned" or "large_llm"                          │ │
    │  │  → LLM calls: 1-2                                               │ │
    │  └─────────────────────────────────────────────────────────────────┘ │
    │                                                                       │
    │  ┌─────────────────────────────────────────────────────────────────┐ │
    │  │  TIER 5: NO MATCH (score < 0.50)                                │ │
    │  │  ────────────────────────────────────────────────────────────── │ │
    │  │  → Large LLM generates fresh answer                             │ │
    │  │  → Cache result for future                                      │ │
    │  │  → Source: "large_llm"                                          │ │
    │  │  → LLM calls: 1 (Large)                                         │ │
    │  └─────────────────────────────────────────────────────────────────┘ │
    └───────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         PHASE 3: TUTORING (OPTIONAL)                        │
└─────────────────────────────────────────────────────────────────────────────┘

If tutoring enabled AND question_id exists:
    │
    ├──→ [Intent Classifier] ───→ Classify user response
    │        (Port 8009)
    │             │
    │             │  ┌─────────────────────────────────────────────┐
    │             └──│  USES: Small LLM (Port 8005) as fallback    │
    │                │  - Rule-based patterns first (fast)         │
    │                │  - LLM only if rules uncertain              │
    │                └─────────────────────────────────────────────┘
    │
    └──→ [Tutoring Response Generation]
              │
              │  ┌─────────────────────────────────────────────────────────┐
              └──│  TIERED LLM USAGE:                                      │
                 │                                                         │
                 │  Simple hints (depth 1-2):                              │
                 │    → Small LLM generates quick guidance                 │
                 │    → "Give ONE hint about [concept]"                    │
                 │                                                         │
                 │  Complex explanations (depth 3-4):                      │
                 │    → Large LLM for detailed step-by-step               │
                 │    → "Explain [concept] thoroughly"                     │
                 │                                                         │
                 │  Always cache interaction for reuse                     │
                 └─────────────────────────────────────────────────────────┘
```

---

## Part 4: Small LLM Usage Summary

### Where Small LLM is Used (Optimized)

| Component | Task | Why Small LLM |
|-----------|------|---------------|
| **Reformulator** | Query improvement | Simple transformation, speed critical |
| **Reformulator** | Context summarization | Compress history, not generate |
| **Reformulator** | Lesson identification | Classification task |
| **Intent Classifier** | Fallback classification | Simple categorization |
| **Tier 2 Routing** | Validate cached answer | Minor adaptation needed |
| **Tier 3 Routing** | Context-based answer | Good context = simpler task |
| **Tutoring (depth 1-2)** | Simple hints | One-step guidance |

### Where Large LLM is Used

| Component | Task | Why Large LLM |
|-----------|------|---------------|
| **Tier 4 Routing** | Complex generation | Fine-tuned fallback failed |
| **Tier 5 Routing** | Fresh generation | No cache context at all |
| **Tutoring (depth 3-4)** | Detailed explanations | Multi-step reasoning |
| **Final validation** | Confidence < 0.7 | Ensure quality |

### Where Fine-Tuned Model is Used

| Component | Task | Why Fine-Tuned |
|-----------|------|----------------|
| **Tier 4 Routing** | Domain-specific Q&A | Math-specialized model |
| **Tutoring hints** | Math-specific guidance | Trained on curriculum |

---

## Part 5: Cost/Latency Optimization

### Expected Distribution (After Optimization)

```
┌─────────────────────────────────────────────────────────────────┐
│                    LLM CALL DISTRIBUTION                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Tier 1 (Exact Cache Hit):     ~20% of queries                 │
│  ├── LLM calls: 0                                              │
│  └── Latency: ~100ms                                           │
│                                                                 │
│  Tier 2 (Small LLM Validate):  ~25% of queries                 │
│  ├── LLM calls: 1 Small                                        │
│  └── Latency: ~500ms                                           │
│                                                                 │
│  Tier 3 (Small LLM Context):   ~25% of queries                 │
│  ├── LLM calls: 1 Small                                        │
│  └── Latency: ~800ms                                           │
│                                                                 │
│  Tier 4 (Fine-Tuned First):    ~20% of queries                 │
│  ├── LLM calls: 1-2 (Fine-Tuned, maybe Large)                  │
│  └── Latency: ~1-2s                                            │
│                                                                 │
│  Tier 5 (Large LLM Fresh):     ~10% of queries                 │
│  ├── LLM calls: 1 Large                                        │
│  └── Latency: ~2-3s                                            │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  RESULT:                                                        │
│  ├── 70% of queries use Small LLM or cache only                │
│  ├── 20% use Fine-Tuned (free, on HPC)                         │
│  └── Only 10-30% need Large LLM (paid API)                     │
│                                                                 │
│  ESTIMATED COST REDUCTION: 60-70% vs current Branch 35         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Part 6: Implementation Steps

### Step 1: Port Vector Cache from Branch 35

```bash
# Files to copy:
services/vector_cache/
├── Dockerfile
├── requirements.txt  # Add qdrant-client
└── src/
    ├── __init__.py
    ├── main.py       # Adapt: add observability middleware
    ├── config.py     # Add: Config class pattern from Main
    ├── repository.py # Keep as-is
    ├── logging_utils.py  # Copy from Main
    ├── metrics.py        # Create: cache-specific metrics
    └── models/
        └── schemas.py    # Keep as-is
```

**Changes needed:**
- Add structured logging middleware
- Add Prometheus metrics (searches, saves, hits, misses)
- Add `/metrics` and `/logs/{request_id}` endpoints
- Update Config to match Main's pattern

### Step 2: Port Session Service from Branch 35

```bash
# Files to copy:
services/session/
├── Dockerfile
├── requirements.txt
└── src/
    ├── __init__.py
    ├── main.py       # Adapt: add observability middleware
    ├── config.py     # Add: Config class pattern
    ├── logging_utils.py  # Copy from Main
    ├── metrics.py        # Create: session metrics
    └── models/
        └── schemas.py    # Keep as-is
```

**Changes needed:**
- Add structured logging middleware
- Add Prometheus metrics (active_sessions, created, expired)
- Add `/metrics` and `/logs/{request_id}` endpoints

### Step 3: Port Intent Classifier from Branch 35

```bash
# Files to copy:
services/intent_classifier/
├── Dockerfile
├── requirements.txt
└── src/
    ├── __init__.py
    ├── main.py       # Adapt: use Small LLM service URL
    ├── config.py     # Update: point to Small LLM
    ├── logging_utils.py  # Copy from Main
    ├── metrics.py        # Create: classification metrics
    └── models/
        └── schemas.py    # Keep as-is
```

**Changes needed:**
- Point to Small LLM service instead of direct Ollama
- Add observability middleware
- Add Prometheus metrics (classifications by intent, method)

### Step 4: Update Gateway with Merged Logic

**New Gateway Structure:**
```bash
services/gateway/src/
├── main.py                    # OpenAI-compatible + tutoring endpoints
├── config.py                  # Add: session, intent_classifier URLs
├── orchestrators/
│   ├── __init__.py
│   ├── data_processing.py     # Keep + add context summarization
│   ├── answer_retrieval.py    # Rewrite: 5-tier confidence routing
│   └── tutoring.py            # NEW: tutoring flow from Branch 35
├── clients/
│   ├── __init__.py
│   ├── http_client.py         # Keep
│   ├── session_client.py      # NEW: session service calls
│   └── cache_client.py        # UPDATE: interaction graph support
└── models/
    └── schemas.py             # Merge: add tutoring schemas
```

### Step 5: Update Reformulator with Context Summarization

**Merge logic:**
- Keep Main's structure (logging, metrics)
- Add Branch 35's two-step process:
  1. Context summarization (if follow-up query)
  2. Query reformulation with lesson detection

### Step 6: Update docker-compose.yml

```yaml
services:
  # ... existing services ...

  # NEW: Qdrant Vector Database
  qdrant:
    image: qdrant/qdrant:latest
    container_name: math-tutor-qdrant
    ports:
      - '6333:6333'
      - '6334:6334'
    volumes:
      - qdrant_data:/qdrant/storage
    networks:
      - math-tutor-network

  # REPLACE: vector-cache instead of cache
  vector-cache:
    build:
      context: services/vector_cache
      dockerfile: Dockerfile
    container_name: math-tutor-vector-cache
    ports:
      - '8003:8003'
    env_file:
      - .env
    environment:
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
    depends_on:
      - qdrant
    volumes:
      - ./.logs/vector_cache:/app/logs
    networks:
      - math-tutor-network

  # NEW: Session Service
  session:
    build:
      context: services/session
      dockerfile: Dockerfile
    container_name: math-tutor-session
    ports:
      - '8008:8008'
    env_file:
      - .env
    volumes:
      - ./.logs/session:/app/logs
    networks:
      - math-tutor-network

  # NEW: Intent Classifier Service
  intent-classifier:
    build:
      context: services/intent_classifier
      dockerfile: Dockerfile
    container_name: math-tutor-intent-classifier
    ports:
      - '8009:8009'
    env_file:
      - .env
    environment:
      - SMALL_LLM_SERVICE_URL=http://small-llm:8005
    depends_on:
      - small-llm
    volumes:
      - ./.logs/intent_classifier:/app/logs
    networks:
      - math-tutor-network

volumes:
  qdrant_data:  # NEW
```

### Step 7: Add Tests for New Services

```bash
tests/
├── unit/
│   └── test_services/
│       ├── test_vector_cache.py   # NEW
│       ├── test_session.py        # NEW
│       └── test_intent_classifier.py  # NEW
├── integration/
│   └── test_tutoring_flow.py      # NEW
└── e2e/
    └── test_tutoring_pipeline.py  # NEW
```

### Step 8: Update Grafana Dashboards

Add panels for:
- Vector cache hit rate by tier
- Session active count
- Intent classification distribution
- Small vs Large LLM call ratio
- Tutoring depth distribution

---

## Part 7: Configuration Changes

### New Environment Variables

```bash
# .env additions

# Session Service
SESSION_TTL_SECONDS=3600
SESSION_MAX_HISTORY=50
SESSION_CLEANUP_INTERVAL=300

# Vector Cache (Qdrant)
QDRANT_HOST=qdrant
QDRANT_PORT=6333
VECTOR_DIMENSIONS=1536

# Confidence Thresholds (NEW 5-tier system)
CONFIDENCE_TIER_1_THRESHOLD=0.95  # Exact match
CONFIDENCE_TIER_2_THRESHOLD=0.85  # Small LLM validate
CONFIDENCE_TIER_3_THRESHOLD=0.70  # Small LLM context
CONFIDENCE_TIER_4_THRESHOLD=0.50  # Fine-tuned first
# Below 0.50 = Tier 5 (Large LLM)

# Tutoring
TUTORING_ENABLED=true
TUTORING_MAX_DEPTH=4
TUTORING_INTERACTION_THRESHOLD=0.70

# Intent Classifier
INTENT_RULE_CONFIDENCE_THRESHOLD=0.80
INTENT_USE_LLM_FALLBACK=true
```

---

## Part 8: Migration Checklist

### Pre-Migration
- [ ] Backup current Main branch
- [ ] Document current test coverage
- [ ] Export any cached data (if any)

### Service Porting
- [ ] Port vector_cache service
  - [ ] Add observability middleware
  - [ ] Add Prometheus metrics
  - [ ] Write unit tests
- [ ] Port session service
  - [ ] Add observability middleware
  - [ ] Add Prometheus metrics
  - [ ] Write unit tests
- [ ] Port intent_classifier service
  - [ ] Point to Small LLM service
  - [ ] Add observability middleware
  - [ ] Write unit tests

### Gateway Updates
- [ ] Add 5-tier confidence routing
- [ ] Add tutoring flow orchestrator
- [ ] Add session client
- [ ] Update cache client for interactions
- [ ] Add tutoring endpoints
- [ ] Write integration tests

### Infrastructure
- [ ] Add Qdrant to docker-compose
- [ ] Update prometheus.yml for new services
- [ ] Add Grafana dashboards
- [ ] Update .env.example

### Testing
- [ ] All existing tests pass
- [ ] New unit tests for ported services
- [ ] Integration tests for tutoring flow
- [ ] E2E tests for full pipeline

### Documentation
- [ ] Update README.md
- [ ] Update CLAUDE.md
- [ ] Update TESTING.md

---

## Part 9: Success Metrics

After merge, track:

| Metric | Target |
|--------|--------|
| Large LLM call percentage | < 30% of queries |
| Cache hit rate (Tier 1) | > 20% |
| Small LLM usage | > 50% of LLM calls |
| Average response latency | < 1.5s |
| Tutoring completion rate | > 60% |
| All tests passing | 100% |

---

## Timeline Estimate

| Phase | Tasks |
|-------|-------|
| **Phase 1** | Port vector_cache + session + intent_classifier services |
| **Phase 2** | Update gateway with 5-tier routing + tutoring |
| **Phase 3** | Update reformulator with context summarization |
| **Phase 4** | Infrastructure (Qdrant, Grafana dashboards) |
| **Phase 5** | Testing + documentation |

---

## Notes

1. **Small LLM is the key optimization** - It's free (HPC), fast, and good enough for most tasks
2. **Fine-Tuned Model is underutilized** - Add it to Tier 4 for math-specific answers
3. **Caching compounds** - More users = better cache = fewer LLM calls
4. **Tutoring creates value** - Interactions are cached, reducing future costs
