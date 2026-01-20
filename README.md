# Lebanese High School AI Math Tutor

An AI-powered mathematics tutoring application designed for Lebanese high school students, built with a microservices architecture using FastAPI, OpenAI, and Ollama.

## Architecture

The application uses a microservices architecture with services communicating via REST APIs:

```
services/
├── gateway/          # API Gateway - Main entry point (Port 8000)
├── large_llm/        # Large LLM Service - OpenAI GPT-4o-mini (Port 8001)
├── small_llm/        # Small LLM Service - Ollama/DeepSeek-R1 on HPC (Port 8005)
└── embedding/        # Embedding Service - OpenAI text-embedding-3-small (Port 8002)
```

**Intelligent Routing**: The gateway defaults to the small_llm service for efficiency. Use `use_large_llm: true` in requests to explicitly route to OpenAI's GPT-4o-mini. Automatic fallback to large_llm if small_llm fails.

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
OPENAI_API_KEY=your_openai_api_key_here
MINERU_API_KEY=your_mineru_api_key_here

# Ollama Configuration (for small_llm service)
OLLAMA_SERVICE_URL=http://localhost:11434
OLLAMA_MODEL_NAME=deepseek-r1:7b

# Embedding Service Configuration
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
```

### Running with Docker

#### Prerequisites: Start SSH Tunnel to HPC

The small_llm service requires an SSH tunnel to AUB's HPC (Octopus cluster):

```bash
ssh username@octopus.aub.edu.lb
```

Once you are connected to octopus, you have to preserve a node with GPUs for the `ollama` to run there.

Run this command

```bash
srun --partition=gpu --pty bash
```

Once connected to a node, setup `ollama` there:

```bash
module load ollama
ollama serve # This might take a few seconds to run
```

You will have this signature in the terminal `username@node_name`, check the `node_name` and replace it in the below command.

Run the below command on another terminal

```bash
ssh -L 11434:localhost:11434 username@octopus.aub.edu.lb -t ssh -L 11434:localhost:11434 node_name
```

This way we have a 2 way tunnel to the node we are connected to on `octopus`.

After setting up the connection with `octopus`, we have to run the model now using the below command in the same terminal, change `deepseek-r1:7b` with the model you want to run on `ollama`:

```bash
module load ollama
ollama run deepseek-r1:7b --keepalive -1m
```

This could take up to a few minutes depending on the number of parameters. Once you are able to send a message to the model you are set up; you can test the model in the terminal if you want.

#### Start All Services

```bash
# Build and start all services
docker compose up --build

# Or run in detached mode (background)
docker compose up -d --build
```

Services will be available at:

- Gateway: `http://localhost:8000`
- Large LLM: `http://localhost:8001`
- Embedding: `http://localhost:8002`
- Small LLM: `http://localhost:8005`

#### Stop Services

```bash
# Stop all services (preserves containers)
docker compose stop

# Stop and remove containers
docker compose down

# Stop and remove containers + volumes + networks
docker compose down -v
```

#### View Logs

```bash
# View logs from all services
docker compose logs

# Follow logs in real-time
docker compose logs -f

# View logs for a specific service
docker compose logs gateway
docker compose logs small-llm
docker compose logs large-llm

# Follow logs for a specific service
docker compose logs -f small-llm
```

#### Restart Services

```bash
# Restart all services
docker compose restart

# Restart a specific service
docker compose restart small-llm
docker compose restart gateway
```

#### Rebuild Services

```bash
# Rebuild all services
docker compose build

# Rebuild a specific service
docker compose build small-llm

# Rebuild and restart
docker compose up -d --build small-llm
```

#### Check Service Status

```bash
# List running containers
docker compose ps

# Check health of all services
curl http://localhost:8000/health | jq
```

### API Endpoints

**Gateway Service** (`http://localhost:8000`)

- `GET /health` - Health check (includes status of all downstream services)
- `POST /query` - Submit a math question
  ```json
  {
    "query": "What is the derivative of x^2?",
    "use_large_llm": false // Optional: set to true to use GPT-4o-mini instead of Ollama (default: false)
  }
  ```
  
  Sample Response:
  ```json
  {
    "answer": "The derivative of x^2 is 2x. This is found using the power rule: d/dx(x^n) = n*x^(n-1).",
    "path_taken": "small_llm",
    "verified": true,
    "fallback_used": false
  }
  ```

**Embedding Service** (`http://localhost:8002`)

- `GET /health` - Health check
- `POST /embed` - Generate embeddings for text
  ```json
  {
    "text": "What is calculus?"
  }
  ```
  
  Sample Response:
  ```json
  {
    "embedding": [0.123, -0.456, ...],  // Array of 1536 floats
    "model": "text-embedding-3-small",
    "dimensions": 1536
  }
  ```

## Development

### Code Quality Tools

Run formatting and type checking:

```bash
python3 cli.py clean
```

This runs:

1. **isort** - Import sorting
2. **black** - Code formatting
3. **mypy** - Type checking (per service)

### Project Configuration

- **CLAUDE.md** - Instructions for Claude Code when working with this codebase
- **.github/workflows/pre-merge-checks.yml** - CI/CD checks

### Adding New Services

1. Create a new directory in `services/`
2. Follow the service structure pattern
3. Add service URL to `src/config.py` and `.env.example`
4. Update docker-compose.yml
5. Add health check endpoint

## Configuration

All configuration is managed through the `Config` class in each service's `src/config.py`:

- **API Keys**: OpenAI API key
- **Service URLs**: URLs for inter-service communication
- **App Settings**: Title, description, version

Environment variables can be set in `.env` or through docker-compose environment settings.

## Current Implementation Status

**Completed Services**:
- ✅ Gateway service with health checks and intelligent routing
- ✅ Large LLM service with OpenAI GPT-4o-mini integration
- ✅ Small LLM service with Ollama/DeepSeek-R1 on HPC
- ✅ Embedding service with OpenAI text-embedding-3-small

**Planned Services**:
- 🚧 Cache service (Port 8003)
- 🚧 Complexity assessment service (Port 8004)
- 🚧 Local model service (Port 8006)
- 🚧 Verification service (Port 8007)

## Data Preprocessing

The `data_preprocessing/` directory contains tools for processing educational materials:

```
data_preprocessing/
├── pdf_splitter/        # Split PDF documents into pages
├── pdf_to_latex/        # Convert PDF documents to LaTeX format
├── extract_exercises/   # Extract exercises from educational materials
└── generate_solutions/  # Generate solutions for extracted exercises
```

These tools help prepare and structure the Lebanese high school mathematics curriculum content for the AI tutoring system.

## License

This project is for educational purposes.
