# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lebanese High School AI Math Tutor - A FastAPI microservices application for AI-powered mathematics tutoring tailored for Lebanese high school curriculum.

## Architecture

Services communicate via REST APIs, each running in its own Docker container.

### Services

| Service | Port | Description |
|---------|------|-------------|
| Gateway | 8000 | API Gateway with 4-tier confidence routing and tutoring |
| Large LLM | 8001 | OpenAI GPT-4o-mini |
| Embedding | 8002 | OpenAI text-embedding-3-small |
| Vector Cache | 8003 | Qdrant-backed vector storage (Q&A + tutoring collections) |
| Input Processor | 8004 | Text/image processing |
| Small LLM | 8005 | vLLM DeepSeek-R1-Distill-Qwen-7B (RunPod Serverless) |
| Fine-Tuned Model | 8006 | vLLM DeepSeek-R1-Distill-Qwen-7B (RunPod Serverless) |
| Reformulator | 8007 | Query improvement via vLLM with context summarization (RunPod Serverless) |
| Session | 8010 | In-memory session state with TTL cleanup |
| Intent Classifier | 8009 | Hybrid rule-based + Small LLM intent classification |
| **Qdrant** | 6333 | Vector database (external) |

### 4-Tier Confidence Routing

Cost-optimized routing based on vector similarity scores:
- **Tier 1 (>=0.85)**: Small LLM validate-or-generate
- **Tier 2 (0.70-0.85)**: Small LLM with cache context
- **Tier 3 (0.50-0.70)**: Fine-tuned model
- **Tier 4 (<0.50)**: Large LLM

### Tutoring Flow (Graph Cache)

Interactive tutoring uses graph-based caching with Session, Embedding, Vector Cache, Intent Classifier, and Fine-Tuned Model. The `is_new_branch` flag skips embedding + cache search after inserting a new node.

## Key Patterns

- **Config**: Each service has its own `Config` class in `config.py` with nested classes. Uses `os.environ[]` for required vars, `os.getenv()` for optional with defaults.
- **Health checks**: Every service must have `GET /health`
- **Imports**: Absolute from `src` (e.g., `from src.config import Config`)
- **Code style**: No module-level docstrings; class/function docstrings encouraged
- **Inter-service calls**: `urllib` for HTTP, `openai` package for LLM calls
- **Event loop safety**: Endpoints calling synchronous OpenAI client must use `def` (not `async def`). Gateway uses `asyncio.to_thread`.
- **LLM backend**: Small LLM, Reformulator, Fine-Tuned Model each use a separate RunPod Serverless vLLM endpoint with model name `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B`

## Service Structure

```
services/<service-name>/
├── Dockerfile
├── requirements.txt
└── src/
    ├── __init__.py
    ├── main.py
    ├── config.py
    └── models/
        ├── __init__.py
        └── schemas.py
```

## Environment Variables

Defined in `.env` (not committed). See `.env.example` for all required variables. Docker Compose loads via `env_file` directive.

## Development Commands

```bash
python3.14 cli.py clean       # isort + black + mypy
pytest -n auto                # Run tests in parallel
docker compose up --build      # Run all services
```

## Testing

- **Unit tests** (`@pytest.mark.unit`): Fully mocked, no external dependencies
- **Integration tests** (`@pytest.mark.integration`): Require Docker + RunPod/HPC
- **E2E tests** (`@pytest.mark.e2e`): Require Docker + RunPod/HPC

Integration/E2E use `pytest-xdist` with `xdist_group` markers for parallelization. CI runs them via RunPod Serverless endpoints.

**Before committing**: `python3.14 cli.py clean` then `pytest -n auto`

See `TESTING.md` for details.

## Current Implementation Status

All 11 services completed:
- Gateway with 4-tier routing, tutoring, OpenAI-compatible API
- Input Processor, Embedding, Large LLM (GPT-4o-mini)
- Small LLM + Fine-Tuned Model + Reformulator (vLLM on RunPod Serverless)
- Vector Cache (Qdrant), Intent Classifier, Session
- Docker Compose + Qdrant, Prometheus + Grafana observability
- CI/CD (pre-merge checks + full test suite with RunPod)

## Deployment

- **Local**: `docker compose up --build`
- **LLM services**: RunPod Serverless vLLM (`runpod/worker-v1-vllm:v2.11.3`). Set `*_SERVICE_URL` and `*_API_KEY` in `.env`.
- **Alternative**: AUB HPC via SSH tunnel (set `*_SERVICE_URL=http://host.docker.internal:11434`)

## Rules

- **ALWAYS** activate `.venv` before running dev commands
- **ALWAYS** update `README.md` when making user-facing changes
- **ALWAYS** run `python3.14 cli.py clean` before committing
- **ALWAYS** use agents (Task tool) as needed for parallel work, research, and complex tasks without waiting for explicit user request
- **NEVER** commit `.env` file
- Use `terminal-notifier` when needing user input or done with tasks
