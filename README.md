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
├── small_llm/          # vLLM DeepSeek-R1 (Port 8005)
├── fine_tuned_model/   # vLLM DeepSeek-R1 (Port 8006)
├── reformulator/       # Query improvement via vLLM (Port 8007)
├── intent_classifier/  # User intent classification (Port 8009)
└── session/            # Session state management (Port 8010)

External:
└── qdrant/             # Vector database (Port 6333)
```

**Pipeline**: Gateway orchestrates two phases:
1. **Data Processing**: Input Processor → Reformulator
2. **Answer Retrieval**: 4-Tier Confidence Routing
   - **Tier 1 (>=0.85)**: Small LLM validates cached answer or generates new one
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
- vLLM on RunPod Serverless (all LLM services)

### Environment Setup

Copy `.env.example` to `.env` and fill in your API keys and RunPod endpoint IDs.

### LLM Backend Options

**Option A: RunPod Serverless (Recommended)**

All three LLM services (Small LLM, Reformulator, Fine-Tuned Model) use vLLM endpoints (`runpod/worker-v1-vllm:v2.11.3`) with `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B`. Endpoints scale to zero when idle.

**Option B: AUB HPC via SSH Tunnel**

```bash
ssh -L 0.0.0.0:11434:localhost:11434 username@octopus.aub.edu.lb -t ssh -L 11434:localhost:11434 node_name
```

Then set `*_SERVICE_URL=http://host.docker.internal:11434` and `*_API_KEY=dummy` in `.env`.

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

- **Unit tests** (81): Fully mocked, no external dependencies
- **Integration tests** (5): Require Docker + RunPod/HPC
- **E2E tests** (5): Require Docker + RunPod/HPC

**Parallel execution** (requires `pytest-xdist`):
```bash
python3.14 cli.py test -- -m "integration or e2e" --dist loadgroup -n 4
```

See `TESTING.md` for details.

### CI/CD

- **Pre-merge checks** (`.github/workflows/pre-merge-checks.yml`): Code quality + unit tests on every push/PR
- **Full tests** (`.github/workflows/run-tests.yml`): Integration/E2E tests against RunPod Serverless endpoints

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
