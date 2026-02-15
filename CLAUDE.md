# CLAUDE.md

## Project Overview

Lebanese High School AI Math Tutor — FastAPI microservices for AI math tutoring (Lebanese curriculum). 11 services communicating via REST, each in its own Docker container.

## Architecture

| Service           | Port | Description                                               |
| ----------------- | ---- | --------------------------------------------------------- |
| Gateway           | 8000 | API Gateway with 4-tier confidence routing and tutoring   |
| Large LLM         | 8001 | OpenAI GPT-4o-mini                                        |
| Embedding         | 8002 | OpenAI text-embedding-3-small                             |
| Vector Cache      | 8003 | Qdrant-backed vector storage (Q&A + tutoring collections) |
| Input Processor   | 8004 | Text/image processing                                     |
| Small LLM         | 8005 | vLLM DeepSeek-R1-Distill-Qwen-7B (RunPod Serverless)      |
| Fine-Tuned Model  | 8006 | vLLM DeepSeek-R1-Distill-Qwen-7B (RunPod Serverless)      |
| Reformulator      | 8007 | Query improvement via vLLM (RunPod Serverless)            |
| Session           | 8008 | In-memory session state with TTL cleanup                  |
| Intent Classifier | 8009 | Hybrid rule-based + Small LLM intent classification       |
| Qdrant            | 6333 | Vector database (external)                                |

**4-Tier Routing**: Tier 1 (>=0.85) Small LLM validate-or-generate → Tier 2 (0.70-0.85) Small LLM with context → Tier 3 (0.50-0.70) Fine-tuned model → Tier 4 (<0.50) Large LLM

**Tutoring Flow**: Graph-based caching with Session, Embedding, Vector Cache, Intent Classifier, Fine-Tuned Model. `is_new_branch` skips embedding + cache search after inserting a new node.

## Key Patterns

- **Config**: `Config` class in `config.py` with nested classes. `os.environ[]` for required, `os.getenv()` for optional.
- **Health checks**: Every service has `GET /health`
- **Imports**: Absolute from `src` (e.g., `from src.config import Config`)
- **Code style**: No module-level docstrings; class/function docstrings encouraged
- **Inter-service calls**: `urllib` for HTTP, `openai` package for LLM calls
- **Event loop safety**: Sync OpenAI client endpoints use `def` (not `async def`). Gateway uses `asyncio.to_thread`.
- **LLM backend**: Each LLM service uses a separate RunPod Serverless vLLM endpoint with model `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B`

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

Defined in `.env` (not committed). See `.env.example` for all required variables. Docker Compose loads via `env_file`.

## Commands

```bash
python3.14 cli.py clean   # isort + black + mypy
pytest -n auto             # Run tests in parallel
docker compose up --build  # Run all services
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
