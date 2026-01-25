import time

from src.clients.http_client import call_service
from src.config import Config
from src.logging_utils import StructuredLogger
from src.metrics import (
    gateway_errors_total,
    gateway_input_processor_duration_seconds,
    gateway_reformulator_duration_seconds,
)

logger = StructuredLogger("gateway")


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
            "Phase 1.1: Calling Input Processor",
            context={"input_type": input_type, "input_length": len(input_text)},
            request_id=request_id,
        )

        result = await call_service(
            f"{Config.SERVICES.INPUT_PROCESSOR_URL}/process",
            {"input": input_text, "type": input_type},
            request_id,
            timeout=10,
        )

        duration = time.time() - start_time
        gateway_input_processor_duration_seconds.observe(duration)

        logger.info(
            "Input Processor responded",
            context={
                "processed_input": result.get("processed_input", "")[:100],
                "duration_seconds": round(duration, 3),
            },
            request_id=request_id,
        )
        return result

    except Exception as e:
        duration = time.time() - start_time
        gateway_input_processor_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="input_processor_error").inc()

        logger.error(
            "Input Processor service error",
            context={"error": str(e), "duration_seconds": round(duration, 3)},
            request_id=request_id,
        )
        raise


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
            "Phase 1.2: Calling Reformulator",
            context={"processed_input": processed_input[:100]},
            request_id=request_id,
        )

        result = await call_service(
            f"{Config.SERVICES.REFORMULATOR_URL}/reformulate",
            {"processed_input": processed_input, "input_type": input_type},
            request_id,
            timeout=30,
        )

        duration = time.time() - start_time
        gateway_reformulator_duration_seconds.observe(duration)

        logger.info(
            "Reformulator responded",
            context={
                "reformulated_query": result.get("reformulated_query", "")[:100],
                "improvements_made": result.get("improvements_made", []),
                "duration_seconds": round(duration, 3),
            },
            request_id=request_id,
        )
        return result

    except Exception as e:
        duration = time.time() - start_time
        gateway_reformulator_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="reformulator_error").inc()

        logger.error(
            "Reformulator service error",
            context={"error": str(e), "duration_seconds": round(duration, 3)},
            request_id=request_id,
        )
        raise


async def run_phase1(user_message: str, request_id: str) -> dict:
    """
    Execute Phase 1: Data Processing pipeline

    Flow:
        1. Process input (Input Processor)
        2. Reformulate query (Reformulator)

    Args:
        user_message: Raw user message from chat
        request_id: Request ID for tracing

    Returns:
        Dict with:
            - processed_input: Processed input text
            - reformulated_query: Reformulated query text
            - improvements_made: List of improvements made

    Raises:
        HTTPException: If any service in the pipeline fails
    """
    logger.info(
        "PHASE 1: Data Processing - Starting",
        context={},
        request_id=request_id,
    )

    # Step 1.1: Process input
    input_result = await _process_input(user_message, "text", request_id)
    processed_input = input_result["processed_input"]

    # Step 1.2: Reformulate query
    reformulate_result = await _reformulate_query(processed_input, "text", request_id)
    reformulated_query = reformulate_result["reformulated_query"]

    logger.info(
        "PHASE 1: Data Processing - Completed",
        context={
            "original_input": user_message[:100],
            "reformulated_query": reformulated_query[:100],
            "improvements_made": reformulate_result.get("improvements_made", []),
        },
        request_id=request_id,
    )

    return {
        "processed_input": processed_input,
        "reformulated_query": reformulated_query,
        "improvements_made": reformulate_result.get("improvements_made", []),
    }
