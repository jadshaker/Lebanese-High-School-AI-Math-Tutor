import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from src.config import Config
from src.models.schemas import ProcessQueryRequest, ProcessQueryResponse

app = FastAPI(title="Data Processing Service", version="1.0.0")


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


@app.post("/process-query", response_model=ProcessQueryResponse)
async def process_query(request: ProcessQueryRequest) -> ProcessQueryResponse:
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
    try:
        # Step 1: Process input via Input Processor
        processed_data = await _process_input(request.input, request.type)

        # Step 2: Reformulate query via Reformulator
        reformulated_data = await _reformulate_query(
            processed_data["processed_input"], processed_data["input_type"]
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
        raise HTTPException(status_code=500, detail=f"Data processing error: {str(e)}")


async def _process_input(input_text: str, input_type: str) -> dict:
    """
    Call Input Processor to process raw user input

    Args:
        input_text: Raw user input (text or image data)
        input_type: Type of input ('text' or 'image')

    Returns:
        Dict with processed_input, input_type, and metadata

    Raises:
        HTTPException: If input processor service fails
    """
    try:
        req = Request(
            f"{Config.SERVICES.INPUT_PROCESSOR_URL}/process",
            data=json.dumps({"input": input_text, "type": input_type}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result

    except (HTTPError, URLError) as e:
        raise HTTPException(
            status_code=503, detail=f"Input processor service unavailable: {str(e)}"
        )


async def _reformulate_query(processed_input: str, input_type: str) -> dict:
    """
    Call Reformulator to improve query clarity

    Args:
        processed_input: Processed user input from Input Processor
        input_type: Type of input ('text' or 'image')

    Returns:
        Dict with reformulated_query, original_input, and improvements_made

    Raises:
        HTTPException: If reformulator service fails
    """
    try:
        req = Request(
            f"{Config.SERVICES.REFORMULATOR_URL}/reformulate",
            data=json.dumps(
                {"processed_input": processed_input, "input_type": input_type}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result

    except (HTTPError, URLError) as e:
        raise HTTPException(
            status_code=503, detail=f"Reformulator service unavailable: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8009)
