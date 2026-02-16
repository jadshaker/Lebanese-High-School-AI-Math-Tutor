# Lebanese High School AI Math Tutor

AI-powered math tutoring for Lebanese high school students, built with a single FastAPI application.

## Architecture

```
src/                             # Single consolidated FastAPI application (Port 8000)
├── main.py                      # Unified app with lifespan, middleware, routes
├── config.py                    # Single merged Config class
├── clients/                     # OpenAI client singletons (LLM + Embedding)
├── services/                    # Business logic modules
│   ├── input_processor/         # Text/image processing
│   ├── reformulator/            # Query improvement via vLLM
│   ├── intent_classifier/       # Hybrid rule-based + LLM classification
│   ├── session/                 # In-memory session state with TTL cleanup
│   └── vector_cache/            # Qdrant-backed vector storage
├── orchestrators/               # Pipeline orchestration
│   ├── answer_retrieval/        # 4-tier confidence routing
│   ├── data_processing/         # Input processing + reformulation
│   └── tutoring/                # Interactive tutoring flow
└── routes/admin.py              # Health, metrics, logs, tracking

External:
├── qdrant/                      # Vector database (Port 6333)
├── open-webui/                  # Chat UI (Port 3000)
├── prometheus/                  # Metrics collection (Port 9090)
└── grafana/                     # Dashboard (Port 3001)
```

**Pipeline**: The app orchestrates two phases:

1. **Data Processing**: Input Processor → Reformulator
2. **Answer Retrieval**: 4-Tier Confidence Routing
   - **Tier 1 (>=0.85)**: Small LLM validates cached answer or generates new one
   - **Tier 2 (0.70-0.85)**: Small LLM generates with cache context
   - **Tier 3 (0.50-0.70)**: Fine-tuned model
   - **Tier 4 (<0.50)**: Large LLM for novel questions

**Tutoring Mode**: Interactive step-by-step problem solving using Session, Intent Classifier, and Fine-Tuned Model. The `is_new_branch` flag skips cache on new conversation nodes.

## Getting Started

### Prerequisites

- Python 3.14+, Docker and Docker Compose
- OpenAI API key, RunPod API key

### Setup

1. Copy `.env.example` to `.env` and fill in API keys and RunPod endpoint IDs
2. `docker compose up --build`
3. App API: `http://localhost:8000`, Open WebUI: `http://localhost:3000`

**LLM Backend**: Small LLM, Reformulator, and Fine-Tuned Model use RunPod Serverless vLLM (`runpod/worker-v1-vllm:v2.11.3`) with `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B`.

## API

App (`http://localhost:8000`):

| Endpoint                    | Description                               |
| --------------------------- | ----------------------------------------- |
| `GET /health`               | Health check (Qdrant + session status)    |
| `GET /v1/models`            | List available models (OpenAI-compatible) |
| `POST /v1/chat/completions` | OpenAI-compatible chat endpoint           |
| `POST /tutoring`            | Tutoring interaction endpoint             |
| `GET /metrics`              | Prometheus metrics                        |
| `GET /track/{request_id}`   | Trace request logs                        |

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"math-tutor","messages":[{"role":"user","content":"What is the derivative of x^2?"}]}'
```

## Development

```bash
python3.14 cli.py clean    # isort + black + mypy (run before committing)
pytest -n auto             # Run all tests in parallel
```

### Dev Pod (Local Development Mode)

For faster iteration without serverless cold starts, spin up a RunPod pod with 3 GPUs, each running its own vLLM instance:

```bash
python3.14 cli.py pod start      # Create 3-GPU pod, wait for vLLM, generate .env.dev
docker compose up --build        # Services use dev pod instead of serverless
python3.14 cli.py pod stop       # Destroy pod, delete .env.dev (back to serverless)
```

**How it works**: `pod start` creates a 3-GPU pod where each vLLM instance is pinned to its own GPU via `CUDA_VISIBLE_DEVICES` (ports 8000-8002). It writes `.env.dev` which overrides the serverless URLs in `.env`. Docker Compose loads `.env.dev` automatically when it exists. `pod stop` destroys the pod and deletes `.env.dev` so services fall back to serverless.

**GPU fallback**: Tries A40 48GB, RTX A6000 48GB in order until available.

### Testing

```bash
python3.14 cli.py test                    # All tests
python3.14 cli.py test -- -m unit         # Unit tests (no external deps)
python3.14 cli.py test -- -m integration  # Integration (Docker + RunPod)
python3.14 cli.py test -- -m e2e          # E2E (Docker + RunPod)
```

Integration/E2E tests mock external APIs by default. Use `--use-real-apis` to test against real endpoints. CI runs the full suite against RunPod Serverless.

### CI/CD

- **Pre-merge** (`.github/workflows/pre-merge-checks.yml`): isort + black + mypy on every push/PR
- **Full tests** (`.github/workflows/run-tests.yml`): All tests against RunPod endpoints

## Observability

- **Prometheus** (`http://localhost:9090`) — metrics collection via `/metrics` endpoint
- **Grafana** (`http://localhost:3001`, admin/admin) — pre-configured dashboard with 13 panels across 5 rows (overview stats, pipeline performance, LLM & cache, sessions & tutoring, app health)
- **Structured logging** — logs to stdout + `.logs/app/app-YYYY-MM-DD.log` (date-based files, 7-day retention)
- **Request tracing** — unique request IDs; trace via `GET /track/{request_id}`

## Data Preprocessing

Tools in `data_preprocessing/` for processing Lebanese math curriculum: PDF splitting, LaTeX conversion, exercise extraction, solution generation.

## License

This project is for educational purposes.
