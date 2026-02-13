# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lebanese High School AI Math Tutor - A FastAPI-based application for AI-powered mathematics tutoring tailored for Lebanese high school curriculum, built with a microservices architecture.

## Architecture

The application uses a **microservices architecture** with services communicating via REST APIs. Each service runs in its own Docker container.

### Current Services

- **Gateway** (Port 8000) - API Gateway with 4-tier confidence routing and tutoring
- **Input Processor** (Port 8004) - Text/image processing service
- **Reformulator** (Port 8007) - Query improvement via LLM with context summarization
- **Embedding** (Port 8002) - OpenAI text-embedding-3-small for vector embeddings
- **Vector Cache** (Port 8003) - Qdrant-backed vector storage with Q&A and tutoring collections
- **Small LLM** (Port 8005) - Ollama integration for efficient local inference (DeepSeek-R1 hosted on AUB HPC)
- **Large LLM** (Port 8001) - OpenAI GPT-4o-mini integration for complex math questions
- **Fine-Tuned Model** (Port 8006) - Ollama integration for fine-tuned model (TinyLlama hosted on AUB HPC)
- **Intent Classifier** (Port 8009) - Hybrid rule-based + Small LLM intent classification
- **Session** (Port 8010) - In-memory session state management with TTL cleanup

### External Services

- **Qdrant** (Port 6333) - Vector database for similarity search

### 4-Tier Confidence Routing

The Gateway implements cost-optimized routing based on vector similarity scores:
- **Tier 1 (≥0.85)**: Small LLM validate-or-generate - validates cached answer or generates new one in a single call
- **Tier 2 (0.70-0.85)**: Small LLM generates answer with cache context
- **Tier 3 (0.50-0.70)**: Fine-tuned model for domain-specific response
- **Tier 4 (<0.50)**: Large LLM for novel/complex questions

### Tutoring Flow (Graph Cache)

Interactive tutoring uses a **graph-based caching** approach:

1. **Session Service**: Tracks `question_id`, `current_node_id`, and traversal path
2. **Embedding Service**: Embeds user responses for similarity search
3. **Vector Cache**: Stores tutoring interactions as a tree structure
   - Each question has child nodes (tutoring steps)
   - Each step can have child nodes (follow-up interactions)
4. **Intent Classifier**: Detects student intent (affirmative, negative, partial, question, skip, off_topic)
5. **Fine-Tuned Model**: Generates new tutoring responses (not Small LLM)

**Cache Lookup Flow**:
```
User Response → is_new_branch?
                    │
              ┌── YES ──┐── NO ──┐
              │                   │
              ▼                   ▼
    Skip embed+search     Embed → Search children
              │                   │
              │         ┌── Cache Hit (≥0.85)? ──┐
              │         │                         │
              │        YES                       NO
              │         │                         │
              │         ▼                         │
              │  Return cached response           │
              │  (is_new_branch=False)             │
              │                                   │
              └───────────────────────────────────┘
                              │
                              ▼
                      Intent Classifier
                              │
                              ▼
                      Fine-Tuned Model
                              │
                              ▼
                   Save as new child node
                   (is_new_branch=True)
```

**Cost Optimization**: As the tutoring cache builds up, common student responses (like "I don't understand", "yes", "explain more") get cached, reducing model calls. Additionally, after inserting a new node, the `is_new_branch` flag skips the embedding + cache search on the next interaction (~2.8s saved per turn).

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

# Small LLM Service Configuration (Ollama)
# Note: Use host.docker.internal for Docker, localhost for direct access
SMALL_LLM_SERVICE_URL=http://host.docker.internal:11434
SMALL_LLM_MODEL_NAME=deepseek-r1:7b

# Embedding Service Configuration
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536

# Fine-Tuned Model Service Configuration (Ollama)
FINE_TUNED_MODEL_SERVICE_URL=http://host.docker.internal:11434
FINE_TUNED_MODEL_NAME=tinyllama:latest

# Vector Cache (Qdrant)
QDRANT_HOST=qdrant
QDRANT_PORT=6333
CACHE_TOP_K=5

# 4-Tier Confidence Routing Thresholds
CONFIDENCE_TIER_1=0.85
CONFIDENCE_TIER_2=0.70
CONFIDENCE_TIER_3=0.50

# Session Management
SESSION_TTL_SECONDS=3600
SESSION_MAX_MESSAGES=50

# Tutoring Configuration
TUTORING_ENABLE=true
TUTORING_MAX_DEPTH=5

# Intent Classification
INTENT_RULE_CONFIDENCE_THRESHOLD=0.8
INTENT_USE_LLM_FALLBACK=true
```

Docker Compose loads these via the `env_file` directive.

**Note**: Both `small_llm` and `fine_tuned_model` services connect to the same Ollama instance:
- **Local Development**: Use `http://host.docker.internal:11434` to access HPC via SSH tunnel from host machine
- **CI (GitHub Actions)**: Use `https://POD_ID-11434.proxy.runpod.net` to access RunPod GPU pod
- Services differentiate by using different model names (deepseek-r1:7b vs tinyllama:latest)

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

- `README.md` - **PRIMARY USER DOCUMENTATION** - Must be kept updated (see Keeping README.md Updated section)
- `CLAUDE.md` - This file - Guidance for Claude Code when working with this repository
- `cli.py` - Development CLI for running code quality checks
- `docker-compose.yml` - Orchestrates all microservices
- `.env` - Environment variables (not committed)
- `.env.example` - Example environment variables
- `.vscode/tasks.json` - VSCode tasks for development
- `.github/workflows/pre-merge-checks.yml` - CI/CD code quality and unit tests
- `.github/workflows/run-tests.yml` - CI/CD integration/E2E tests with RunPod GPU pods

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

✅ **Completed** (11 services):

- Gateway service with 4-tier confidence routing, tutoring flow, and OpenAI-compatible API
- Input Processor service with text processing and image stub
- Reformulator service with LLM-powered query improvement and context summarization
- Embedding service with OpenAI text-embedding-3-small (1536 dimensions)
- Vector Cache service with Qdrant backend for Q&A and tutoring interactions
- Small LLM service with Ollama integration (DeepSeek-R1 on AUB HPC)
- Large LLM service with OpenAI GPT-4o-mini integration
- Fine-Tuned Model service with Ollama integration (TinyLlama on AUB HPC)
- Intent Classifier service with hybrid rule-based + LLM fallback
- Session service with in-memory storage and TTL cleanup
- Docker Compose setup with all services + Qdrant
- Prometheus + Grafana observability stack
- Code quality tooling (isort, black, mypy)
- CI/CD pre-merge checks
- VSCode tasks integration

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
   COPY . .
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

## Testing Guidelines

**ALWAYS write tests for new code:**
- Add unit tests for new services or endpoints
- Update tests when modifying existing functionality
- Run tests before committing: `python3.14 cli.py test`

**Test Types (93 total: 83 unit + 5 integration + 5 E2E):**
- **Unit tests** (`@pytest.mark.unit`): Fast, isolated, mock everything external - NO external dependencies
- **Integration tests** (`@pytest.mark.integration`): Real Docker services - REQUIRES Docker + real APIs
- **E2E tests** (`@pytest.mark.e2e`): Full pipeline - REQUIRES Docker + real APIs

**Note:** Integration/E2E tests run against Docker services which make API calls in separate processes
that cannot be mocked with Python libraries. CI runs these automatically using RunPod GPU pods.

**Before Committing:**
1. Run code quality checks: `python3.14 cli.py clean`
2. Run unit tests: `python3.14 cli.py test -- -m unit`
3. Ensure unit tests pass (83 tests)
4. Check coverage if adding new code

**Integration/E2E Tests:**
- Run automatically in CI via RunPod GPU pods (`.github/workflows/run-tests.yml`)
- For local runs: require Docker services + HPC SSH tunnel + valid OPENAI_API_KEY in `.env`

**Quick Test Commands:**
```bash
# Run only unit tests (fast, no external dependencies)
python3.14 cli.py test -- -m unit

# Run integration tests (requires Docker + OpenAI keys + HPC)
python3.14 cli.py test -- -m integration

# Run E2E tests (requires Docker + OpenAI keys + HPC)
python3.14 cli.py test -- -m e2e

# Run with coverage
python3.14 cli.py test -- --cov=services --cov-report=html

# Run specific test file
python3.14 cli.py test -- tests/unit/test_services/test_gateway.py
```

**Recommended Testing Workflow:**
1. During development: Only run unit tests (`-m unit`)
2. Before committing: Run unit tests + code quality checks
3. Before major releases: Run full test suite including integration/E2E

See `TESTING.md` for comprehensive testing guidelines.

## Manual Testing

Test the gateway health check to verify all services are running:

```bash
curl http://localhost:8000/health
```

Test the OpenAI-compatible chat completions endpoint:

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "math-tutor",
    "messages": [{"role": "user", "content": "What is the derivative of x^2?"}]
  }'
```

Test the tutoring endpoint:

```bash
curl -X POST http://localhost:8000/tutoring \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session",
    "user_response": "I understand"
  }'
```

## Deployment

### Docker Compose (Local/Development)

```bash
docker compose up --build
```

### Small LLM & Fine-Tuned Model Services - Ollama SSH Tunnel Setup

Both `small_llm` and `fine_tuned_model` services connect to the same Ollama instance running on AUB's HPC (Octopus cluster). They use different models but share the same tunnel. A double SSH tunnel is required:

**Start SSH Tunnel** (from development machine):
```bash
# Bind to all interfaces (0.0.0.0) so Docker can access it
ssh -L 0.0.0.0:11434:localhost:11434 jss31@octopus.aub.edu.lb -t ssh -L 11434:localhost:11434 onode26
```

This creates:
- **First tunnel**: Dev machine port 11434 → Octopus port 11434
- **Second tunnel**: Octopus port 11434 → onode26 port 11434 (where Ollama runs)

**On the HPC compute node** (e.g., onode26):
```bash
# Set up Ollama to use shared models and avoid NFS issues
module load ollama
export OLLAMA_MODELS=/scratch/shared/ai/models/llms/ollama/models
export TMPDIR=/scratch/<your-user-id>/tmp
export OLLAMA_TMPDIR=/scratch/<your-user-id>/tmp
mkdir -p /scratch/<your-user-id>/tmp

# Start Ollama server (in screen/tmux for persistence)
screen -S ollama
ollama serve

# In another terminal, load both models (they stay in memory)
ollama run deepseek-r1:7b --keepalive -1m    # For small_llm service
# Press Ctrl+C to exit chat (model stays loaded)

ollama run tinyllama:latest --keepalive -1m  # For fine_tuned_model service
# Press Ctrl+C to exit chat (model stays loaded)
```

**Important**:
- Keep SSH tunnel running while services are active
- Use `0.0.0.0` binding (not `localhost`) so Docker containers can access via `host.docker.internal`
- Both models run in the same Ollama instance, differentiated by model name
- For direct service testing (non-Docker), `localhost:11434` works fine

## Documentation Maintenance

### Keeping README.md Updated

**CRITICAL**: The `README.md` file is the primary documentation for users and developers. It MUST be kept in sync with code changes.

**ALWAYS** update `README.md` when making changes to:

1. **Architecture Changes**:
   - Adding, removing, or modifying services
   - Changing service ports or URLs
   - Modifying the microservices architecture
   - Example: If you add a new service at port 8003, update the architecture diagram and service list in README.md

2. **API Changes**:
   - Adding, removing, or modifying endpoints
   - Changing request/response models
   - Modifying query parameters or flags (e.g., `use_large_llm`)
   - Example: If you add a new field to the query request, update the API endpoints section with the new field

3. **Configuration Changes**:
   - Adding new environment variables
   - Changing configuration requirements
   - Modifying `.env.example`
   - Example: If you add a new API key requirement, update both the environment setup section and the example .env snippet

4. **Setup/Installation Changes**:
   - Modifying prerequisites (Python version, dependencies, external services)
   - Changing Docker setup or docker-compose configuration
   - Updating SSH tunnel or HPC connection instructions
   - Example: If you change the SSH tunnel command, update the "Prerequisites: Start SSH Tunnel to HPC" section

5. **Feature Additions**:
   - Implementing new functionality (caching, verification, new routing logic)
   - Completing planned services (change from 🚧 to ✅)
   - Example: When the cache service is implemented, update the "Current Implementation Status" section in README.md from "🚧 Cache service (planned)" to "✅ Cache service with [description]"

6. **Development Tool Changes**:
   - Modifying code quality tools or commands
   - Changing testing procedures
   - Updating the CLI or build commands
   - Example: If you add a new command to `cli.py`, document it in the "Development" section under "Code Quality Tools"

**Before finalizing any task**, review README.md to ensure:
- All user-facing changes are documented
- Code examples are accurate and up-to-date
- The implementation status section reflects current reality
- Commands and examples actually work

**Documentation Quality Standards**:
- Keep explanations clear and concise
- Include working code examples
- Update version numbers if they change
- Maintain consistency with existing documentation style
- Test all commands before documenting them

## Notes for Claude Code

- **EXCEPTION**: Use `openai` package for:
  - Large LLM service: OpenAI API calls
  - Small LLM service: Ollama's OpenAI-compatible API
  - Fine-Tuned Model service: Ollama's OpenAI-compatible API
- **ALWAYS** activate `.venv` before running development commands
- **NEVER** commit `.env` file
- **ALWAYS** add health check endpoint to new services
- **ALWAYS** update README.md when making changes that affect users or developers (see Keeping README.md Updated section)
- **FOLLOW** the service structure pattern for consistency
- Services are independent - each has its own `config.py` and `schemas.py`
- Run `python3 cli.py clean` before committing changes
- For small_llm and fine_tuned_model services: ensure SSH tunnel to HPC is active and both models are loaded before testing
- Both small_llm and fine_tuned_model use the same Ollama instance but different model names (SMALL_LLM_MODEL_NAME and FINE_TUNED_MODEL_NAME)
