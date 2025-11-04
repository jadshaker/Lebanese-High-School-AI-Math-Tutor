# Lebanese High School AI Math Tutor

An AI-powered mathematics tutoring application designed for Lebanese high school students, built with a microservices architecture using FastAPI, OpenAI, and Ollama.

## Architecture

The application uses a microservices architecture with services communicating via REST APIs:

```
services/
├── gateway/          # API Gateway - Main entry point (Port 8000)
├── large_llm/        # Large LLM Service - OpenAI GPT-4 (Port 8001)
└── small_llm/        # Small LLM Service - Ollama/DeepSeek-R1 on HPC (Port 8005)
```

**Intelligent Routing**: The gateway defaults to the small_llm service for efficiency. Use `use_large_llm: true` in requests to explicitly route to OpenAI's GPT-4. Automatic fallback to large_llm if small_llm fails.

### Service Structure

Each service follows this structure:

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

## Getting Started

### Prerequisites

- Python 3.14+
- Docker and Docker Compose
- OpenAI API key
- SSH access to AUB HPC (Octopus cluster) for small_llm service

### Environment Setup

1. Create a `.env` file in the project root based on `.env.example`:

```bash
# API Keys
OPENAI_API_KEY=sk-your-api-key-here

# Ollama Configuration (for small_llm service)
OLLAMA_SERVICE_URL=http://localhost:11434
OLLAMA_MODEL_NAME=deepseek-r1:7b
```

2. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running with Docker

**1. Start SSH Tunnel to HPC** (required for small_llm service):

```bash
# From your local machine
ssh -L 0.0.0.0:11434:localhost:11434 <username>@octopus.aub.edu.lb -t ssh -L 11434:localhost:11434 onode11
```

Keep this terminal open while services are running.

**2. Start all services**:

```bash
docker compose up --build
```

The gateway will be available at `http://localhost:8000`

### API Endpoints

**Gateway Service** (`http://localhost:8000`)

- `GET /health` - Health check (includes status of all downstream services)
- `POST /query` - Submit a math question
  ```json
  {
    "query": "What is the derivative of x^2?",
    "use_large_llm": false  // Optional: set to true to use GPT-4 instead of Ollama (default: false)
  }
  ```

**Large LLM Service** (`http://localhost:8001`)

- `GET /health` - Health check
- `POST /generate` - Generate answer using OpenAI GPT-4
  ```json
  {
    "query": "What is the derivative of x^2?"
  }
  ```

**Small LLM Service** (`http://localhost:8005`)

- `GET /health` - Health check (verifies Ollama connectivity and model availability)
- `POST /query` - Generate answer using Ollama (DeepSeek-R1 on HPC)
  ```json
  {
    "query": "What is the derivative of x^2?"
  }
  ```

## Development

### Code Quality Tools

Run formatting and type checking:

```bash
python3 cli.py clean
```

Or use VSCode tasks:

- Press `Cmd+Shift+P` (or `Ctrl+Shift+P`)
- Select "Tasks: Run Task"
- Choose "🧹 Clean"

This runs:

1. **isort** - Import sorting
2. **black** - Code formatting
3. **mypy** - Type checking (per service)

### Project Configuration

- **CLAUDE.md** - Instructions for Claude Code when working with this codebase
- **.vscode/tasks.json** - VSCode tasks for development
- **.github/workflows/pre-merge-checks.yml** - CI/CD checks

### Adding New Services

1. Create a new directory in `services/`
2. Follow the service structure pattern
3. Add service URL to `src/config.py`
4. Update docker-compose.yml
5. Add health check endpoint

## Deployment

### Syncing to Remote

Use the VSCode task "🔄 Sync to Octopus" or run:

```bash
rsync -av --delete --exclude=.git --exclude=.venv --exclude=.mypy_cache \
  . octopus:~/dev/Lebanese-High-School-AI-Math-Tutor
```

## Configuration

All configuration is managed through the `Config` class in each service's `src/config.py`:

- **API Keys**: OpenAI API key
- **Service URLs**: URLs for inter-service communication
- **App Settings**: Title, description, version

Environment variables can be set in `.env` or through docker-compose environment settings.

## Current Implementation Status

- ✅ Gateway service with health checks and intelligent routing
- ✅ Large LLM service with OpenAI GPT-4 integration
- ✅ Small LLM service with Ollama/DeepSeek-R1 on HPC
- ✅ Gateway routing: defaults to small_llm, optional large_llm, automatic fallback
- 🚧 Embedding service (planned)
- 🚧 Cache service (planned)
- 🚧 Complexity assessment (planned)
- 🚧 Local model service (planned)
- 🚧 Verification service (planned)

## License

This project is for educational purposes.
