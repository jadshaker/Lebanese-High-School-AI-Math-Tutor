import json
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException


async def call_service(
    url: str,
    payload: Optional[dict[str, Any]],
    request_id: str,
    timeout: int = 10,
    method: str = "POST",
) -> dict[str, Any]:
    """
    Make HTTP call to a service with standardized error handling

    Args:
        url: Full URL to the service endpoint
        payload: Request payload as dict
        request_id: Request ID for distributed tracing
        timeout: Request timeout in seconds (default: 10)
        method: HTTP method (default: POST)

    Returns:
        Response data as dict

    Raises:
        HTTPException: If the service call fails
    """
    try:
        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8") if payload else None,
            headers={"Content-Type": "application/json", "X-Request-ID": request_id},
            method=method,
        )

        with urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result

    except (HTTPError, URLError) as e:
        # Re-raise as HTTPException with service unavailable status
        raise HTTPException(
            status_code=503, detail=f"Service unavailable: {str(e)}"
        ) from e


async def call_service_safe(
    url: str,
    payload: Optional[dict[str, Any]],
    request_id: str,
    timeout: int = 10,
    method: str = "POST",
    default_on_error: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Make HTTP call to a service with error suppression (for non-critical calls)

    Args:
        url: Full URL to the service endpoint
        payload: Request payload as dict
        request_id: Request ID for distributed tracing
        timeout: Request timeout in seconds (default: 10)
        method: HTTP method (default: POST)
        default_on_error: Default value to return on error (default: empty dict)

    Returns:
        Response data as dict, or default_on_error if call fails
    """
    if default_on_error is None:
        default_on_error = {}

    try:
        return await call_service(url, payload, request_id, timeout, method)
    except HTTPException:
        return default_on_error
