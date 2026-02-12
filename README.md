# Lebanese High School AI Math Tutor

AI-powered math tutoring for Lebanese high school students, built with FastAPI microservices.

## Architecture

```
services/
├── gateway/            # API Gateway - Orchestrator (Port 8000)
├── large_llm/          # OpenAI GPT-4o-mini (Port 8001)
├── embedding/          # OpenAI text-embedding-3-small (Port 8002)
├── vector_cache/       # Qdrant vector storage (Port 8003)
├── input_processor/    # Text/image processing (Port 8004)
├── small_llm/          # Ollama DeepSeek-R1 (Port 8005)
├── fine_tuned_model/   # Ollama TinyLlama (Port 8006)
├── reformulator/       # Query improvement via LLM (Port 8007)
├── intent_classifier/  # User intent classification (Port 8009)
└── session/            # Session state management (Port 8010)

External:
└── qdrant/             # Vector database (Port 6333)
```

**Pipeline**: Gateway orchestrates two phases:
1. **Data Processing**: Input Processor → Reformulator
2. **Answer Retrieval**: 4-Tier Confidence Routing
   - **Tier 1 (≥0.85)**: Small LLM validates cached answer or generates new one
   - **Tier 2 (0.70-0.85)**: Small LLM generates with cache context
   - **Tier 3 (0.50-0.70)**: Fine-tuned model
   - **Tier 4 (<0.50)**: Large LLM for novel questions

**Tutoring Mode**: Interactive step-by-step problem solving using:
- Session service for conversation state (with `is_new_branch` optimization to skip cache on new nodes)
- Intent classifier for understanding student responses
- Fine-tuned model for generating appropriate tutoring responses

## Getting Started

### Prerequisites

- Python 3.14+
- Docker and Docker Compose
- OpenAI API key
- Ollama instance (AUB HPC via SSH tunnel or RunPod)

### Environment Setup

Create `.env` from `.env.example`:

```bash
# API Keys
OPENAI_API_KEY=your_key_here

# LLM Services (Ollama)
SMALL_LLM_SERVICE_URL=http://host.docker.internal:11434
SMALL_LLM_MODEL_NAME=deepseek-r1:7b
FINE_TUNED_MODEL_SERVICE_URL=http://host.docker.internal:11434
FINE_TUNED_MODEL_NAME=tinyllama:latest

# Embedding
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536

# Vector Cache (Qdrant)
QDRANT_HOST=qdrant
QDRANT_PORT=6333
CACHE_TOP_K=5

# 4-Tier Confidence Routing
CONFIDENCE_TIER_1=0.85
CONFIDENCE_TIER_2=0.70
CONFIDENCE_TIER_3=0.50

# Session Management
SESSION_TTL_SECONDS=3600
SESSION_MAX_MESSAGES=50

# Tutoring
TUTORING_ENABLE=true
TUTORING_MAX_DEPTH=5

# Intent Classification
INTENT_RULE_CONFIDENCE_THRESHOLD=0.8
INTENT_USE_LLM_FALLBACK=true
```

### Ollama Setup (AUB HPC)

```bash
# Reserve GPU node
ssh username@octopus.aub.edu.lb
srun --partition=gpu --pty bash

# Start Ollama on the node
module load ollama
ollama serve

# SSH tunnel (from your machine, bind 0.0.0.0 for Docker access)
ssh -L 0.0.0.0:11434:localhost:11434 username@octopus.aub.edu.lb -t ssh -L 11434:localhost:11434 node_name

# Load models (on the node)
ollama run deepseek-r1:7b --keepalive -1m
ollama run tinyllama:latest --keepalive -1m
```

### Run

```bash
docker compose up --build
```

Services: `http://localhost:8000` (Gateway), ports 8001-8010 for individual services.

**UI**: Open WebUI at `http://localhost:3000`

## API

**Gateway** (`http://localhost:8000`):

- `GET /health` — Health check (includes all downstream services)
- `GET /v1/models` — List available models (OpenAI-compatible)
- `POST /v1/chat/completions` — OpenAI-compatible chat endpoint
- `POST /tutoring` — Tutoring interaction endpoint
- `GET /track/{request_id}` — Trace request across services

```bash
# OpenAI-compatible chat
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "math-tutor",
    "messages": [{"role": "user", "content": "What is the derivative of x^2?"}]
  }'

# Tutoring interaction
curl -X POST http://localhost:8000/tutoring \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-123",
    "user_response": "I understand"
  }'
```

## Development

### Code Quality

```bash
python3 cli.py clean   # isort + black + mypy
```

### Testing

```bash
python3.14 cli.py test              # All tests
python3.14 cli.py test -- -m unit   # Unit tests only (no external deps)
```

- **Unit tests**: Fully mocked, no external dependencies
- **Integration tests**: Require Docker + real APIs
- **E2E tests**: Require Docker + real APIs

See `TESTING.md` for details.

### CI/CD

- **Pre-merge checks** (`.github/workflows/pre-merge-checks.yml`): Code quality + unit tests on every push/PR
- **Full tests** (`.github/workflows/run-tests.yml`): Creates RunPod GPU pod, loads models, runs all tests against real Ollama inference

## Observability

- **Prometheus** (`http://localhost:9090`): Metrics collection
- **Grafana** (`http://localhost:3001`): Dashboards and visualization
- **Request tracing**: `GET /track/{request_id}` for distributed tracing

## Data Preprocessing

Tools in `data_preprocessing/` for processing Lebanese math curriculum:

- `pdf_splitter/` — Split PDFs into pages
- `pdf_to_latex/` — Convert PDFs to LaTeX
- `extract_exercises/` — Extract exercises
- `generate_solutions/` — Generate solutions

## License

This project is for educational purposes.
