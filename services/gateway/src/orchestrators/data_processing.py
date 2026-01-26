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
        logger.info("  → Input Processor", request_id=request_id)

        result = await call_service(
            f"{Config.SERVICES.INPUT_PROCESSOR_URL}/process",
            {"input": input_text, "type": input_type},
            request_id,
            timeout=10,
        )

        duration = time.time() - start_time
        gateway_input_processor_duration_seconds.observe(duration)

        preview = result.get("processed_input", "")[:50]
        logger.info(
            f"  ✓ Input Processor ({duration:.1f}s): {preview}...",
            request_id=request_id,
        )
        return result

    except Exception as e:
        duration = time.time() - start_time
        gateway_input_processor_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="input_processor_error").inc()

        logger.error(
            f"Input Processor service error ({duration:.1f}s): {str(e)}",
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
        logger.info("  → Reformulator", request_id=request_id)

        result = await call_service(
            f"{Config.SERVICES.REFORMULATOR_URL}/reformulate",
            {"processed_input": processed_input, "input_type": input_type},
            request_id,
            timeout=30,
        )

        duration = time.time() - start_time
        gateway_reformulator_duration_seconds.observe(duration)

        preview = result.get("reformulated_query", "")[:50]
        improvements = result.get("improvements_made", [])
        logger.info(
            f"  ✓ Reformulator ({duration:.1f}s): {preview}... [{len(improvements)} improvements]",
            request_id=request_id,
        )
        return result

    except Exception as e:
        duration = time.time() - start_time
        gateway_reformulator_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="reformulator_error").inc()

        logger.error(
            f"Reformulator service error ({duration:.1f}s): {str(e)}",
            request_id=request_id,
        )
        raise


async def process_user_input(user_message: str, request_id: str) -> dict:
    """
    Execute Data Processing pipeline

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
    logger.info("Data Processing Pipeline: Started", request_id=request_id)

    # Step 1: Process input
    input_result = await _process_input(user_message, "text", request_id)
    processed_input = input_result["processed_input"]

    # Step 2: Reformulate query
    reformulate_result = await _reformulate_query(processed_input, "text", request_id)
    reformulated_query = reformulate_result["reformulated_query"]

    logger.info(
        f"Data Processing Pipeline: Completed - Query reformulated",
        request_id=request_id,
    )

    return {
        "processed_input": processed_input,
        "reformulated_query": reformulated_query,
        "improvements_made": reformulate_result.get("improvements_made", []),
    }
