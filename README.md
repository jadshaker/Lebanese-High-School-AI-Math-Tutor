# Lebanese High School AI Math Tutor

An AI-powered mathematics tutoring application designed for Lebanese high school students, built with a microservices architecture using FastAPI, OpenAI, and Ollama.

## Architecture

The application uses a microservices architecture with services communicating via REST APIs:

```
services/
├── gateway/            # API Gateway - Main entry point (Port 8000)
├── large_llm/          # Large LLM Service - OpenAI GPT-4o-mini (Port 8001)
├── embedding/          # Embedding Service - OpenAI text-embedding-3-small (Port 8002)
├── cache/              # Cache Service - Vector storage (stub) (Port 8003)
├── input_processor/    # Input Processor Service - Text/image processing (Port 8004)
├── small_llm/          # Small LLM Service - Ollama/DeepSeek-R1 on HPC (Port 8005)
├── fine_tuned_model/   # Fine-Tuned Model Service - Ollama/TinyLlama on HPC (Port 8006)
├── reformulator/       # Reformulator Service - Query improvement via LLM (Port 8007)
├── answer_retrieval/   # Answer Retrieval Service - Orchestrator for Phase 2 (Port 8008)
└── data_processing/    # Data Processing Service - Orchestrator for Phase 1 (Port 8009)
```

**Pipeline Architecture**: The gateway orchestrates a two-phase pipeline:
- **Phase 1 (Data Processing)**: Input Processor → Reformulator
- **Phase 2 (Answer Retrieval)**: Embedding → Cache → Small LLM → (conditional) Large LLM

The system automatically determines when to use the Large LLM based on cache confidence. All complexity is handled by orchestrator services.

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

# Small LLM Service Configuration (Ollama)
SMALL_LLM_SERVICE_URL=http://localhost:11434
SMALL_LLM_MODEL_NAME=deepseek-r1:7b

# Embedding Service Configuration
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536

# Fine-Tuned Model Service Configuration (Ollama)
FINE_TUNED_MODEL_SERVICE_URL=http://localhost:11434
FINE_TUNED_MODEL_NAME=tinyllama:latest

# Answer Retrieval Service Configuration
CACHE_TOP_K=5

# Data Processing Service Configuration (Phase 1)
INPUT_PROCESSOR_SERVICE_URL=http://input-processor:8004
REFORMULATOR_SERVICE_URL=http://reformulator:8007
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

After setting up the connection with `octopus`, we have to run the models now. Both `small_llm` and `fine_tuned_model` services use the same Ollama instance, so you need to load both models:

```bash
module load ollama

# Load the small_llm model
ollama run deepseek-r1:7b --keepalive -1m
# Press Ctrl+C to exit the chat (model stays loaded)

# Load the fine-tuned model
ollama run tinyllama:latest --keepalive -1m
# Press Ctrl+C to exit the chat (model stays loaded)
```

This could take up to a few minutes depending on the number of parameters. Both models will remain loaded in memory and accessible via the API.

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
- Cache: `http://localhost:8003`
- Input Processor: `http://localhost:8004`
- Small LLM: `http://localhost:8005`
- Fine-Tuned Model: `http://localhost:8006`
- Reformulator: `http://localhost:8007`
- Answer Retrieval: `http://localhost:8008`
- Data Processing: `http://localhost:8009`

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

- `GET /health` - Health check (includes status of orchestrator services: data_processing, answer_retrieval)
- `POST /query` - Submit a math question (orchestrates full pipeline)
  ```json
  {
    "input": "what is derivative of x squared",
    "type": "text"  // "text" or "image"
  }
  ```

  Sample Response:
  ```json
  {
    "answer": "The derivative of x^2 is 2x. This is found using the power rule: d/dx(x^n) = n*x^(n-1).",
    "source": "small_llm",
    "used_cache": true,
    "metadata": {
      "input_type": "text",
      "original_input": "what is derivative of x squared",
      "reformulated_query": "What is the derivative of f(x) = x²?",
      "processing": {
        "phase1": {
          "input_processor": {
            "preprocessing_applied": ["strip_whitespace", "normalize_spacing"]
          },
          "reformulator": {
            "improvements_made": ["standardized mathematical notation", "added clarity"]
          }
        },
        "phase2": {
          "cache_similarity": 0.95,
          "llm_used": "small_llm"
        }
      }
    }
  }
  ```

  **Flow**:
  1. Calls Data Processing Service (Phase 1): processes and reformulates input
  2. Calls Answer Retrieval Service (Phase 2): retrieves answer using cache and LLMs
  3. Combines results and metadata from both phases

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
    "embedding": [0.0234, -0.0521, 0.0834, -0.0129, ...],  // Array of 1536 floats
    "model": "text-embedding-3-small",
    "dimensions": 1536
  }
  ```

**Input Processor Service** (`http://localhost:8004`)

- `GET /health` - Health check
- `POST /process` - Process user input (text or image)
  ```json
  {
    "input": "What is the derivative of x^2?",
    "type": "text"  // "text" or "image"
  }
  ```

  Sample Response (text):
  ```json
  {
    "processed_input": "What is the derivative of x^2?",
    "input_type": "text",
    "metadata": {
      "original_length": 30,
      "processed_length": 30,
      "preprocessing_applied": ["strip_whitespace", "normalize_spacing"]
    }
  }
  ```

  Sample Response (image - stub):
  ```json
  {
    "processed_input": "Image input received",
    "input_type": "image",
    "metadata": {
      "note": "Image processing not yet implemented",
      "planned_features": ["OCR text extraction", "Math notation recognition", "Image validation"],
      "image_data_length": 25
    }
  }
  ```

  **Features**:
  - Text processing: strips whitespace, normalizes spacing, validates length
  - Image processing: stub implementation (acknowledges receipt, returns sample response)
  - Input validation: checks for empty text, invalid types, exceeds max length

**Reformulator Service** (`http://localhost:8007`)

- `GET /health` - Health check (includes Small LLM service status)
- `POST /reformulate` - Reformulate processed input for improved clarity
  ```json
  {
    "processed_input": "derivative of x squared",
    "input_type": "text"
  }
  ```

  Sample Response:
  ```json
  {
    "reformulated_query": "What is the derivative of f(x) = x²?",
    "original_input": "derivative of x squared",
    "improvements_made": [
      "standardized mathematical notation",
      "added clarity and completeness",
      "completed question structure"
    ]
  }
  ```

  **Features**:
  - Uses Small LLM (DeepSeek-R1) to reformulate questions
  - Standardizes mathematical notation (e.g., "x squared" → "x²")
  - Improves question clarity and completeness
  - Fixes grammar and structural issues
  - Provides detailed list of improvements made
  - Cleans LLM responses (handles reasoning tokens, LaTeX notation)

**Answer Retrieval Service** (`http://localhost:8008`)

- `GET /health` - Health check (includes status of all dependent services: embedding, cache, small_llm, large_llm)
- `POST /retrieve-answer` - Orchestrated answer retrieval with caching
  ```json
  {
    "query": "What is the derivative of x^2?"
  }
  ```

  Sample Response (from cache via small_llm):
  ```json
  {
    "answer": "The derivative of x^2 is 2x",
    "source": "small_llm",
    "used_cache": true,
    "confidence": 0.95
  }
  ```

  Sample Response (from large_llm):
  ```json
  {
    "answer": "The derivative of x^2 is 2x. Using the power rule...",
    "source": "large_llm",
    "used_cache": false,
    "confidence": null
  }
  ```

  **Flow**:
  1. Embeds query via Embedding Service
  2. Searches cache for similar Q&A pairs (top-k=5)
  3. Queries Small LLM with cached context
  4. If exact match found (similarity ≥ 0.95), returns cached answer
  5. Otherwise, queries Large LLM for fresh answer
  6. Saves Large LLM answer to cache for future use

**Data Processing Service** (`http://localhost:8009`)

- `GET /health` - Health check (includes status of dependent services: input_processor, reformulator)
- `POST /process-query` - Orchestrated Phase 1 data processing pipeline
  ```json
  {
    "input": "derivative of x squared",
    "type": "text"  // "text" or "image"
  }
  ```

  Sample Response:
  ```json
  {
    "reformulated_query": "What is the derivative of f(x) = x²?",
    "original_input": "derivative of x squared",
    "input_type": "text",
    "processing_metadata": {
      "input_processor": {
        "preprocessing_applied": ["strip_whitespace", "normalize_spacing"]
      },
      "reformulator": {
        "improvements_made": [
          "standardized mathematical notation",
          "added clarity and completeness"
        ]
      }
    }
  }
  ```

  **Flow**:
  1. Processes raw input via Input Processor Service
  2. Reformulates processed input via Reformulator Service
  3. Returns reformulated query with metadata from both services

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
- ✅ Embedding service with OpenAI text-embedding-3-small
- ✅ Cache service (stub) with vector similarity search endpoints (Port 8003)
- ✅ Input Processor service with text processing and image stub (Port 8004)
- ✅ Small LLM service with Ollama/DeepSeek-R1 on HPC (Port 8005)
- ✅ Fine-Tuned Model service with Ollama/TinyLlama on HPC (Port 8006)
- ✅ Reformulator service with LLM-powered query improvement (Port 8007)
- ✅ Answer Retrieval service with complete Phase 2 orchestration (Port 8008)
- ✅ Data Processing service with Phase 1 orchestration (Port 8009)

**Planned Services**:
- 🚧 UI service (Port 3000)
- 🚧 Full cache implementation with vector database

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
