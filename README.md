# Lebanese High School AI Math Tutor

AI-powered math tutoring for Lebanese high school students, built with FastAPI microservices.

## Architecture

```
services/
├── gateway/            # API Gateway - Orchestrator (Port 8000)
├── large_llm/          # OpenAI GPT-4o-mini (Port 8001)
├── embedding/          # OpenAI text-embedding-3-small (Port 8002)
├── cache/              # Vector storage stub (Port 8003)
├── input_processor/    # Text/image processing (Port 8004)
├── small_llm/          # vLLM DeepSeek-R1 (Port 8005)
├── fine_tuned_model/   # vLLM DeepSeek-R1 (Port 8006)
└── reformulator/       # Query improvement via vLLM (Port 8007)
```

**Pipeline**: Gateway orchestrates two phases:
1. **Data Processing**: Input Processor → Reformulator
2. **Answer Retrieval**: Embedding → Cache → Small LLM → (conditional) Large LLM

## Getting Started

### Prerequisites

- Python 3.14+
- Docker and Docker Compose
- OpenAI API key
- vLLM on RunPod Serverless (all LLM services)

### Environment Setup

Create `.env` from `.env.example`:

```bash
OPENAI_API_KEY=your_key_here
SMALL_LLM_SERVICE_URL=https://api.runpod.ai/v2/<endpoint_id>/openai
SMALL_LLM_MODEL_NAME=deepseek-ai/DeepSeek-R1-Distill-Qwen-7B
SMALL_LLM_API_KEY=your_runpod_api_key
REFORMULATOR_LLM_SERVICE_URL=https://api.runpod.ai/v2/<endpoint_id>/openai
REFORMULATOR_LLM_MODEL_NAME=deepseek-ai/DeepSeek-R1-Distill-Qwen-7B
REFORMULATOR_LLM_API_KEY=your_runpod_api_key
FINE_TUNED_MODEL_SERVICE_URL=https://api.runpod.ai/v2/<endpoint_id>/openai
FINE_TUNED_MODEL_NAME=deepseek-ai/DeepSeek-R1-Distill-Qwen-7B
FINE_TUNED_MODEL_API_KEY=your_runpod_api_key
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
CACHE_TOP_K=5
```

### LLM Backend Options

**Option A: RunPod Serverless (Recommended)**

All three LLM services (Small LLM, Reformulator, Fine-Tuned Model) use vLLM endpoints (`runpod/worker-v1-vllm:stable-cuda12.1.0`) with `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` (HuggingFace FP16). Endpoints scale to zero when idle (no cost) and serve requests on-demand via OpenAI-compatible API.

**Option B: AUB HPC via SSH Tunnel**

```bash
# SSH tunnel (from your machine, bind 0.0.0.0 for Docker access)
ssh -L 0.0.0.0:11434:localhost:11434 username@octopus.aub.edu.lb -t ssh -L 11434:localhost:11434 node_name

# On the HPC node: start Ollama and load model
module load ollama && ollama serve
ollama run deepseek-r1:7b --keepalive -1m
```

Then set `*_SERVICE_URL=http://host.docker.internal:11434` and `*_API_KEY=dummy` in `.env`.

### Run

```bash
docker compose up --build
```

Services: `http://localhost:8000` (Gateway), ports 8001-8007 for individual services.

**UI**: Open WebUI at `http://localhost:3000`

## API

**Gateway** (`http://localhost:8000`):

- `GET /health` — Health check (includes all downstream services)
- `POST /query` — Submit a math question

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"input": "what is derivative of x squared", "type": "text"}'
```

## Development

### Code Quality

```bash
python3 cli.py clean   # isort + black + mypy
```

### Testing

```bash
python3.14 cli.py test              # All tests
python3.14 cli.py test -- -m unit   # Unit tests only (no external deps)
```

- **Unit tests** (81): Fully mocked, no external dependencies
- **Integration tests** (5): Require Docker + RunPod/HPC
- **E2E tests** (5): Require Docker + RunPod/HPC

**Parallel execution** (requires `pytest-xdist`):
```bash
python3.14 cli.py test -- -m "integration or e2e" --dist loadgroup -n 4
```

See `TESTING.md` for details.

### CI/CD

- **Pre-merge checks** (`.github/workflows/pre-merge-checks.yml`): Code quality + unit tests on every push/PR
- **Full tests** (`.github/workflows/run-tests.yml`): Runs integration/E2E tests against RunPod Serverless endpoints with real LLM inference

## Data Preprocessing

Tools in `data_preprocessing/` for processing Lebanese math curriculum:

- `pdf_splitter/` — Split PDFs into pages
- `pdf_to_latex/` — Convert PDFs to LaTeX
- `extract_exercises/` — Extract exercises
- `generate_solutions/` — Generate solutions

## License

This project is for educational purposes.
