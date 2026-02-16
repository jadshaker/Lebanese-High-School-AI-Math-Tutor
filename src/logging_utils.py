import logging
import uuid
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Optional


class StructuredLogger:
    """
    Structured logger that outputs logs in uvicorn-style format for readability.

    Logs to both:
    - Console (stdout) - for Docker logs
    - File (with daily rotation) - for persistent storage
    """

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.logger = logging.getLogger(service_name)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        # Remove existing handlers to avoid duplicates
        self.logger.handlers.clear()

        # Console handler (for Docker logs)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(console_handler)

        # File handler (for persistent logs with daily rotation)
        log_dir = Path("/app/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "app.log"

        file_handler = TimedRotatingFileHandler(
            log_file,
            when="midnight",
            interval=1,
            backupCount=7,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(file_handler)

    def log(
        self,
        level: str,
        message: str,
        context: Optional[dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        """Log a structured message in uvicorn-style format."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level_padded = level.ljust(8)

        req_id = request_id or generate_request_id()
        log_parts = [
            f"{timestamp} | {level_padded} | {self.service_name}:{req_id} - {message}"
        ]

        if context:
            context_str = " ".join(f"{k}={v}" for k, v in context.items())
            log_parts.append(f" - {context_str}")

        log_line = "".join(log_parts)
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(log_line)

    def info(
        self,
        message: str,
        context: Optional[dict] = None,
        request_id: Optional[str] = None,
    ):
        """Log INFO level message"""
        self.log("INFO", message, context, request_id)

    def debug(
        self,
        message: str,
        context: Optional[dict] = None,
        request_id: Optional[str] = None,
    ):
        """Log DEBUG level message"""
        self.log("DEBUG", message, context, request_id)

    def warning(
        self,
        message: str,
        context: Optional[dict] = None,
        request_id: Optional[str] = None,
    ):
        """Log WARNING level message"""
        self.log("WARNING", message, context, request_id)

    def error(
        self,
        message: str,
        context: Optional[dict] = None,
        request_id: Optional[str] = None,
    ):
        """Log ERROR level message"""
        self.log("ERROR", message, context, request_id)


def generate_request_id() -> str:
    """Generate a unique request ID for distributed tracing"""
    return f"req-{uuid.uuid4().hex[:12]}"


def get_logs_by_request_id(request_id: str, max_lines: int = 1000) -> list[str]:
    """Read logs from file and filter by request ID."""
    log_file = Path("/app/logs/app.log")

    if not log_file.exists():
        return []

    matching_logs = []

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            recent_lines = (
                all_lines[-max_lines:] if len(all_lines) > max_lines else all_lines
            )
            for line in recent_lines:
                if request_id in line:
                    matching_logs.append(line.strip())
    except Exception:
        pass

    return matching_logs
