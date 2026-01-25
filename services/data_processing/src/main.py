import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from fastapi import Request as FastAPIRequest
from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from src.config import Config
from src.logging_utils import (
    StructuredLogger,
    generate_request_id,
    get_logs_by_request_id,
)
from src.metrics import (
    data_processing_input_processor_duration_seconds,
    data_processing_reformulator_duration_seconds,
    http_request_duration_seconds,
    http_requests_total,
)
from src.models.schemas import ProcessQueryRequest, ProcessQueryResponse

app = FastAPI(title="Data Processing Service", version="1.0.0")
logger = StructuredLogger("data_processing")


@app.middleware("http")
async def logging_and_metrics_middleware(request: FastAPIRequest, call_next):
    """Middleware to log all HTTP requests and responses, and record metrics"""
    request_id = request.headers.get("X-Request-ID", generate_request_id())
    start_time = time.time()

    # Skip logging /metrics endpoint unless there's an error
    is_metrics_endpoint = request.url.path == "/metrics"

    # Log incoming request (skip /metrics)
    if not is_metrics_endpoint:
        logger.info(
            "Incoming request",
            context={
                "endpoint": request.url.path,
                "method": request.method,
            },
            request_id=request_id,
        )

    request.state.request_id = request_id

    try:
        response = await call_next(request)
        duration = time.time() - start_time

        # Record metrics (skip /metrics endpoint to avoid recursion)
        if not is_metrics_endpoint:
            http_requests_total.labels(
                service="data_processing",
                endpoint=request.url.path,
                method=request.method,
                status=response.status_code,
            ).inc()

            http_request_duration_seconds.labels(
                service="data_processing",
                endpoint=request.url.path,
                method=request.method,
            ).observe(duration)

        # Log response (skip /metrics if status is 200)
        if not (is_metrics_endpoint and response.status_code == 200):
            logger.info(
                "Request completed",
                context={
                    "endpoint": request.url.path,
                    "status_code": response.status_code,
                    "duration_seconds": round(duration, 3),
                },
                request_id=request_id,
            )

        response.headers["X-Request-ID"] = request_id
        return response

    except Exception as e:
        duration = time.time() - start_time

        # Record error metrics
        if not is_metrics_endpoint:
            http_requests_total.labels(
                service="data_processing",
                endpoint=request.url.path,
                method=request.method,
                status=500,
            ).inc()

            http_request_duration_seconds.labels(
                service="data_processing",
                endpoint=request.url.path,
                method=request.method,
            ).observe(duration)

        # Always log errors, even for /metrics
        logger.error(
            "Request failed",
            context={
                "endpoint": request.url.path,
                "error": str(e),
                "duration_seconds": round(duration, 3),
            },
            request_id=request_id,
        )
        raise


@app.get("/health")
def health_check() -> dict[str, str | dict]:
    """
    Health check endpoint that verifies all dependent services

    Returns:
        Dict with overall status and individual service statuses
    """
    services_status = {}
    overall_healthy = True

    # Check Input Processor Service
    try:
        req = Request(f"{Config.SERVICES.INPUT_PROCESSOR_URL}/health", method="GET")
        with urlopen(req, timeout=2) as response:
            services_status["input_processor"] = "healthy"
    except Exception:
        services_status["input_processor"] = "unhealthy"
        overall_healthy = False

    # Check Reformulator Service
    try:
        req = Request(f"{Config.SERVICES.REFORMULATOR_URL}/health", method="GET")
        with urlopen(req, timeout=2) as response:
            services_status["reformulator"] = "healthy"
    except Exception:
        services_status["reformulator"] = "unhealthy"
        overall_healthy = False

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "service": "data_processing",
        "dependencies": services_status,
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/logs/{request_id}")
async def get_logs(request_id: str):
    """Get logs for a specific request ID"""
    logs = get_logs_by_request_id(request_id)
    return {"request_id": request_id, "logs": logs, "count": len(logs)}


@app.post("/process-query", response_model=ProcessQueryResponse)
async def process_query(
    request: ProcessQueryRequest, fastapi_request: FastAPIRequest
) -> ProcessQueryResponse:
    """
    Orchestrates Phase 1 data processing flow:
    1. Process input via Input Processor
    2. Reformulate query via Reformulator
    3. Return reformulated query with metadata

    Args:
        request: ProcessQueryRequest with user input and type

    Returns:
        ProcessQueryResponse with reformulated query and metadata

    Raises:
        HTTPException: If any service fails
    """
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    try:
        logger.info(
            "Starting data processing",
            context={"input_type": request.type, "input_length": len(request.input)},
            request_id=request_id,
        )

        # Step 1: Process input via Input Processor
        processed_data = await _process_input(request.input, request.type, request_id)

        # Step 2: Reformulate query via Reformulator
        reformulated_data = await _reformulate_query(
            processed_data["processed_input"], processed_data["input_type"], request_id
        )

        logger.info(
            "Data processing completed",
            context={
                "reformulated_query": reformulated_data["reformulated_query"][:100],
            },
            request_id=request_id,
        )

        # Step 3: Combine results and return
        return ProcessQueryResponse(
            reformulated_query=reformulated_data["reformulated_query"],
            original_input=request.input,
            input_type=processed_data["input_type"],
            processing_metadata={
                "input_processor": processed_data.get("metadata", {}),
                "reformulator": {
                    "improvements_made": reformulated_data.get("improvements_made", [])
                },
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Data processing error",
            context={"error": str(e), "error_type": type(e).__name__},
            request_id=request_id,
        )
        raise HTTPException(status_code=500, detail=f"Data processing error: {str(e)}")


async def _process_input(input_text: str, input_type: str, request_id: str) -> dict:
    """
    Call Input Processor to process raw user input

    Args:
        input_text: Raw user input (text or image data)
        input_type: Type of input ('text' or 'image')
        request_id: Request ID for tracing

    Returns:
        Dict with processed_input, input_type, and metadata

    Raises:
        HTTPException: If input processor service fails
    """
    start_time = time.time()
    try:
        logger.info(
            "Calling Input Processor",
            context={"input_type": input_type},
            request_id=request_id,
        )

        req = Request(
            f"{Config.SERVICES.INPUT_PROCESSOR_URL}/process",
            data=json.dumps({"input": input_text, "type": input_type}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Request-ID": request_id},
            method="POST",
        )

        with urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            duration = time.time() - start_time
            data_processing_input_processor_duration_seconds.observe(duration)

            logger.info(
                "Input Processor responded",
                context={"processed": True, "duration_seconds": round(duration, 3)},
                request_id=request_id,
            )
            return result

    except (HTTPError, URLError) as e:
        duration = time.time() - start_time
        data_processing_input_processor_duration_seconds.observe(duration)

        logger.error(
            "Input Processor service error",
            context={"error": str(e), "duration_seconds": round(duration, 3)},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=503, detail=f"Input processor service unavailable: {str(e)}"
        )


async def _reformulate_query(
    processed_input: str, input_type: str, request_id: str
) -> dict:
    """
    Call Reformulator to improve query clarity

    Args:
        processed_input: Processed user input from Input Processor
        input_type: Type of input ('text' or 'image')
        request_id: Request ID for tracing

    Returns:
        Dict with reformulated_query, original_input, and improvements_made

    Raises:
        HTTPException: If reformulator service fails
    """
    start_time = time.time()
    try:
        logger.info(
            "Calling Reformulator",
            context={"processed_input": processed_input[:100]},
            request_id=request_id,
        )

        req = Request(
            f"{Config.SERVICES.REFORMULATOR_URL}/reformulate",
            data=json.dumps(
                {"processed_input": processed_input, "input_type": input_type}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Request-ID": request_id},
            method="POST",
        )

        with urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            duration = time.time() - start_time
            data_processing_reformulator_duration_seconds.observe(duration)

            logger.info(
                "Reformulator responded",
                context={
                    "reformulated_query": result.get("reformulated_query", "")[:100],
                    "duration_seconds": round(duration, 3),
                },
                request_id=request_id,
            )
            return result

    except (HTTPError, URLError) as e:
        duration = time.time() - start_time
        data_processing_reformulator_duration_seconds.observe(duration)

        logger.error(
            "Reformulator service error",
            context={"error": str(e), "duration_seconds": round(duration, 3)},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=503, detail=f"Reformulator service unavailable: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8009)
