import asyncio
import time

from src.logging_utils import StructuredLogger
from src.metrics import (
    gateway_errors_total,
    gateway_input_processor_duration_seconds,
    gateway_reformulator_duration_seconds,
)
from src.services.input_processor.service import process_input
from src.services.reformulator.service import reformulate_query

logger = StructuredLogger("gateway")


async def _process_input_step(
    input_text: str, input_type: str, request_id: str
) -> dict:
    """Process raw user input."""
    start_time = time.time()
    try:
        logger.info("  → Input Processor", request_id=request_id)

        result = process_input(input_text, input_type, request_id)

        duration = time.time() - start_time
        gateway_input_processor_duration_seconds.observe(duration)

        preview = result.processed_input[:50]
        logger.info(
            f"  ✓ Input Processor ({duration:.1f}s): {preview}...",
            request_id=request_id,
        )
        return {
            "processed_input": result.processed_input,
            "input_type": result.input_type,
            "metadata": result.metadata,
        }

    except Exception as e:
        duration = time.time() - start_time
        gateway_input_processor_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="input_processor_error").inc()
        logger.error(
            f"Input Processor error ({duration:.1f}s): {str(e)}",
            request_id=request_id,
        )
        raise


async def _reformulate_step(
    processed_input: str, input_type: str, request_id: str
) -> dict:
    """Reformulate query for clarity."""
    start_time = time.time()
    try:
        logger.info("  → Reformulator", request_id=request_id)

        # reformulate_query is sync (OpenAI SDK), run in thread
        result = await asyncio.to_thread(
            reformulate_query, processed_input, input_type, request_id
        )

        duration = time.time() - start_time
        gateway_reformulator_duration_seconds.observe(duration)

        preview = result.reformulated_query[:50]
        improvements = result.improvements_made
        logger.info(
            f"  ✓ Reformulator ({duration:.1f}s): {preview}... [{len(improvements)} improvements]",
            request_id=request_id,
        )
        return {
            "reformulated_query": result.reformulated_query,
            "original_input": result.original_input,
            "improvements_made": result.improvements_made,
        }

    except Exception as e:
        duration = time.time() - start_time
        gateway_reformulator_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="reformulator_error").inc()
        logger.error(
            f"Reformulator error ({duration:.1f}s): {str(e)}",
            request_id=request_id,
        )
        raise


async def process_user_input(user_message: str, request_id: str) -> dict:
    """Execute Data Processing pipeline: Process input → Reformulate."""
    pipeline_start = time.time()
    latency: dict[str, float] = {}
    logger.info("Data Processing Pipeline: Started", request_id=request_id)

    # Step 1: Process input
    t0 = time.time()
    input_result = await _process_input_step(user_message, "text", request_id)
    latency["input_processor"] = round(time.time() - t0, 3)
    processed_input = input_result["processed_input"]

    # Step 2: Reformulate query
    t0 = time.time()
    reformulate_result = await _reformulate_step(processed_input, "text", request_id)
    latency["reformulator"] = round(time.time() - t0, 3)
    reformulated_query = reformulate_result["reformulated_query"]

    latency["data_processing_total"] = round(time.time() - pipeline_start, 3)
    logger.info(
        "Data Processing Pipeline: Completed - Query reformulated",
        request_id=request_id,
    )

    return {
        "processed_input": processed_input,
        "reformulated_query": reformulated_query,
        "improvements_made": reformulate_result.get("improvements_made", []),
        "latency": latency,
    }
