# CLAUDE.md

## Project Overview

Lebanese High School AI Math Tutor — a single FastAPI application for AI math tutoring (Lebanese curriculum). All services consolidated into one container with direct function calls.

## Architecture

| Container | Port | Description |
| --------- | ---- | ----------- |
| App | 8000 | Single FastAPI app — all services merged |
| Qdrant | 6333 | Vector database (external) |
| Open WebUI | 3000 | Chat UI (external) |
| Prometheus | 9090 | Metrics collection (external) |
| Grafana | 3001 | Dashboard (external) |

```
src/
├── main.py                         # Unified FastAPI app with lifespan
├── config.py                       # Single merged Config class
├── logging_utils.py                # Structured logging
├── metrics.py                      # All Prometheus metrics
├── models/schemas.py               # All Pydantic models
├── clients/
│   ├── llm.py                      # 4 OpenAI client singletons (small, fine-tuned, large, reformulator)
│   └── embedding.py                # OpenAI embedding client
├── services/
│   ├── input_processor/service.py  # Text processing
│   ├── reformulator/               # Query improvement (prompts.py + service.py)
│   ├── intent_classifier/          # Rule-based + LLM classification (prompts.py + service.py)
│   ├── session/service.py          # In-memory session store + TTL cleanup
│   └── vector_cache/               # Qdrant operations (repository.py + service.py)
├── orchestrators/
│   ├── answer_retrieval/           # 4-tier routing (prompts.py + service.py)
│   ├── data_processing/service.py  # Input processing + reformulation pipeline
│   └── tutoring/                   # Tutoring flow (prompts.py + service.py)
└── routes/admin.py                 # /health, /metrics, /logs, /track
```

**4-Tier Routing**: Tier 1 (>=0.85) Small LLM validate-or-generate → Tier 2 (0.70-0.85) Small LLM with context → Tier 3 (0.50-0.70) Fine-tuned model → Tier 4 (<0.50) Large LLM

**Tutoring Flow**: Graph-based caching with Session, Embedding, Vector Cache, Intent Classifier, Fine-Tuned Model. `is_new_branch` skips embedding + cache search after inserting a new node.

## Key Patterns

- **Config**: `Config` class in `config.py` with nested classes. `os.environ[]` for required, `os.getenv()` for optional.
- **Health checks**: `GET /health` checks Qdrant connectivity + session status
- **Imports**: Absolute from `src` (e.g., `from src.config import Config`)
- **Code style**: No module-level docstrings; class/function docstrings encouraged
- **Service calls**: Direct Python function calls (no inter-service HTTP)
- **Event loop safety**: Sync OpenAI client calls use `asyncio.to_thread()` in async orchestrators
- **LLM clients**: 4 OpenAI client singletons in `clients/llm.py` — Small LLM, Fine-tuned, Large LLM, Reformulator
- **LLM backend**: Small LLM, Reformulator, and Fine-Tuned Model use RunPod Serverless vLLM with `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B`

## Environment Variables

Defined in `.env` (not committed). See `.env.example` for all required variables. Docker Compose loads via `env_file`.

## Commands

```bash
python3.14 cli.py clean          # isort + black + mypy
pytest -n auto                   # Run tests in parallel
docker compose up --build        # Run all services

python3.14 cli.py pod start      # Create dev GPU pod (3 vLLM instances), generate .env.dev
python3.14 cli.py pod stop       # Destroy pod, delete .env.dev
```

## Testing

- **Unit** (`@pytest.mark.unit`): Fully mocked, no external deps
- **Integration** (`@pytest.mark.integration`): Docker + RunPod vLLM
- **E2E** (`@pytest.mark.e2e`): Docker + RunPod vLLM

Before committing: `python3.14 cli.py clean` then `pytest -n auto`

## Rules

- **ALWAYS** activate `.venv` before running dev commands
- **ALWAYS** update `README.md` when making user-facing changes
- **ALWAYS** run `python3.14 cli.py clean` before committing
- **ALWAYS** use agents (Task tool) as needed for parallel work, research, and complex tasks without waiting for explicit user request
- **NEVER** commit `.env` file
- Use `terminal-notifier` when needing user input or done with tasks
