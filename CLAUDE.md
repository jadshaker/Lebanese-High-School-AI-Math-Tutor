# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lebanese High School AI Math Tutor - A FastAPI-based application for AI-powered mathematics tutoring tailored for Lebanese high school curriculum, built with a microservices architecture.

## Architecture

The application uses a **microservices architecture** with services communicating via REST APIs. Each service runs in its own Docker container.

### Current Services

- **Gateway** (Port 8000) - API Gateway that orchestrates requests to other services
- **Large LLM** (Port 8001) - OpenAI GPT-4 integration for complex math questions
- **Small LLM** (Port 8005) - Ollama integration for efficient local inference (DeepSeek-R1 hosted on AUB HPC)

### Planned Services

- Embedding service (Port 8002)
- Cache service (Port 8003)
- Complexity assessment (Port 8004)
- Local model service (Port 8006)
- Verification service (Port 8007)

## Service Structure

Each service follows this standard structure:

```
services/<service-name>/
├── Dockerfile                    # Container definition
├── requirements.txt              # Python dependencies
└── src/
    ├── __init__.py
    ├── main.py                   # FastAPI app with endpoints
    ├── config.py                 # Configuration using Config class
    └── models/
        ├── __init__.py
        └── schemas.py            # Pydantic models
```

### Key Patterns

1. **Configuration**: All services use a `Config` class with nested classes for organization as needed. So `config.py` files differ between services:

   ```python
   import os

   from dotenv import load_dotenv

   load_dotenv()


   class Config:
       class SERVICES:
           LARGE_LLM_URL = os.getenv("LARGE_LLM_SERVICE_URL", "...")

       class API_KEYS:
           OPENAI = os.getenv("OPENAI_API_KEY")
   ```

2. **Health Checks**: Every service must have a `GET /health` endpoint

3. **Imports**: Services use absolute imports from `src`:
   ```python
   from src.config import Config
   from src.models.schemas import MyModel
   ```

4. **Code Style**:
   - Do NOT include module-level docstrings at the top of files
   - Class and function docstrings are encouraged
   - Keep imports at the top without any docstrings above them

## Development Commands

### Code Quality

Run all quality checks:

```bash
python3 cli.py clean
```

This runs:

1. `isort` - Import sorting with black profile
2. `black` - Code formatting
3. `mypy` - Type checking (per service with `--explicit-package-bases`)

**VSCode Task**: Use the "🧹 Clean" task from VSCode tasks menu

### Running Services

**Docker (Recommended)**:

```bash
docker compose up --build
```

**Individual Service** (for testing):

```bash
cd services/gateway
source ../../.venv/bin/activate
uvicorn src.main:app --reload --port 8000
```

### Docker Structure

- Build context: `services/<service-name>/`
- Each service has its own Dockerfile
- Services copy only what they need:
  - `requirements.txt`
  - `src/` directory with their code
  - Shared `src/__init__.py` and `src/config.py`

## Environment Variables

All environment variables are defined in `.env` at the project root:

```bash
# API Keys
OPENAI_API_KEY=sk-...

# Ollama Configuration (for small_llm service)
OLLAMA_SERVICE_URL=http://localhost:11434
OLLAMA_MODEL_NAME=deepseek-r1:7b
```

Docker Compose loads these via the `env_file` directive.

**Note**: When running small_llm in Docker, `OLLAMA_SERVICE_URL` is overridden to `http://host.docker.internal:11434` to access Ollama via SSH tunnel from the host machine.

## Code Quality Tools

The project enforces code quality using:

- **isort**: Sorts imports with black profile
- **black**: Code formatting (line length 88)
- **mypy**: Type checking with explicit package bases

Configuration:

- `isort`: Uses `--profile black`
- `black`: Default settings
- `mypy`: Runs per-service with `--explicit-package-bases`

## Important Files

- `cli.py` - Development CLI for running code quality checks
- `docker-compose.yml` - Orchestrates all microservices
- `.env` - Environment variables (not committed)
- `.env.example` - Example environment variables
- `.vscode/tasks.json` - VSCode tasks for development
- `.github/workflows/pre-merge-checks.yml` - CI/CD checks

## API Guidelines

### Request/Response Models

All API endpoints use Pydantic models defined in `services/<name>/src/models/schemas.py`:

```python
class QueryRequest(BaseModel):
    """User query request"""
    query: str = Field(..., description="User's math question")

class FinalResponse(BaseModel):
    """Final response to user"""
    answer: str = Field(..., description="Final answer")
    path_taken: str = Field(..., description="Which service path was used")
```

### Error Handling

Use FastAPI's `HTTPException`:

```python
raise HTTPException(
    status_code=503,
    detail=f"Service unavailable: {str(e)}"
)
```

### Inter-Service Communication

Services use Python's built-in `urllib`:

```python
from urllib.request import Request, urlopen
import json

req = Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

with urlopen(req) as response:
    result = json.loads(response.read().decode("utf-8"))
```

Exception: Large LLM and Small LLM services use the official `openai` package (Large LLM for OpenAI API calls, Small LLM for Ollama's OpenAI-compatible API).

## Current Implementation Status

✅ **Completed**:

- Gateway service with health checks and intelligent routing
- Large LLM service with OpenAI GPT-4o-mini integration
- Small LLM service with Ollama integration (DeepSeek-R1 on AUB HPC)
- Gateway routing: defaults to small_llm, optional `use_large_llm` flag, automatic fallback
- Docker Compose setup with all services
- Code quality tooling (isort, black, mypy)
- CI/CD pre-merge checks
- VSCode tasks integration

🚧 **In Progress**:

- Additional microservices (embedding, cache, complexity assessment, verification)
- Request verification
- Caching strategy

## Adding New Services

When creating a new service:

1. **Create directory structure**:

   ```bash
   mkdir -p services/<service-name>/src/models
   touch services/<service-name>/src/{__init__.py,main.py,config.py}
   touch services/<service-name>/src/models/{__init__.py,schemas.py}
   ```

2. **Create Dockerfile**:

   ```dockerfile
   FROM python:3.14-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY src/ src/
   EXPOSE <port>
   CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "<port>"]
   ```

3. **Add to docker-compose.yml**:

   ```yaml
   <service-name>:
     build:
       context: services/<service-name>
       dockerfile: Dockerfile
     container_name: math-tutor-<service-name>
     ports:
       - '<port>:<port>'
     env_file:
       - .env
     networks:
       - math-tutor-network
   ```

4. **Update Config class** in `services/gateway/src/config.py`:

   ```python
   class SERVICES:
       <SERVICE>_URL = os.getenv("<SERVICE>_SERVICE_URL", "http://<service>:<port>")
   ```

5. **Add health check** endpoint in the new service

## Testing

Test the gateway health check to verify all services are running:

```bash
curl http://localhost:8000/health
```

Test the query endpoint:

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the derivative of x^2?"}'
```

## Deployment

### Docker Compose (Local/Development)

```bash
docker compose up --build
```

### Small LLM Service - Ollama SSH Tunnel Setup

The small_llm service connects to Ollama running on AUB's HPC (Octopus cluster, onode11). A double SSH tunnel is required:

**Start SSH Tunnel** (from development machine):
```bash
# Bind to all interfaces (0.0.0.0) so Docker can access it
ssh -L 0.0.0.0:11434:localhost:11434 jss31@octopus.aub.edu.lb -t ssh -L 11434:localhost:11434 onode11
```

This creates:
- **First tunnel**: Dev machine port 11434 → Octopus port 11434
- **Second tunnel**: Octopus port 11434 → onode11 port 11434 (where Ollama runs)

**On onode11** (HPC compute node):
```bash
# Start Ollama server (in screen/tmux for persistence)
screen -S ollama
ollama serve

# Verify Ollama is running
ollama list
```

**Important**:
- Keep SSH tunnel running while services are active
- Use `0.0.0.0` binding (not `localhost`) so Docker containers can access via `host.docker.internal`
- For direct service testing (non-Docker), `localhost:11434` works fine

## Notes for Claude Code

- **EXCEPTION**: Use `openai` package for:
  - Large LLM service: OpenAI API calls
  - Small LLM service: Ollama's OpenAI-compatible API
- **ALWAYS** activate `.venv` before running development commands
- **NEVER** commit `.env` file
- **ALWAYS** add health check endpoint to new services
- **FOLLOW** the service structure pattern for consistency
- Services are independent - each has its own `config.py` and `schemas.py`
- Run `python3 cli.py clean` before committing changes
- For small_llm service: ensure SSH tunnel to HPC is active before testing
