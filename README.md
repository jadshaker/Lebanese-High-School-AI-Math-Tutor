# Lebanese High School AI Math Tutor

An AI-powered mathematics tutoring application designed for Lebanese high school students, built with a microservices architecture using FastAPI and OpenAI.

## Architecture

The application uses a microservices architecture with services communicating via REST APIs:

```
services/
├── gateway/          # API Gateway - Main entry point (Port 8000)
└── large_llm/        # Large LLM Service - OpenAI integration (Port 8001)
```

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

### Environment Setup

1. Create a `.env` file in the project root based on the `example.env` file:

```bash
OPENAI_API_KEY=sk-your-api-key-here
```

2. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running with Docker

Start all services:

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
    "query": "What is the derivative of x^2?"
  }
  ```

**Large LLM Service** (`http://localhost:8001`)

- `GET /health` - Health check
- `POST /generate` - Generate answer using OpenAI
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

- ✅ Gateway service with health checks
- ✅ Large LLM service with OpenAI integration
- 🚧 Embedding service (planned)
- 🚧 Cache service (planned)
- 🚧 Complexity assessment (planned)
- 🚧 Small LLM service (planned)
- 🚧 Local model service (planned)
- 🚧 Verification service (planned)

## License

This project is for educational purposes.
