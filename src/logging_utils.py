import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

LOG_DIR = Path("/app/logs")
KEEP_DAYS = 7


def _today_log_file() -> Path:
    """Return path to today's log file (e.g. app-2026-02-16.log)."""
    return LOG_DIR / f"app-{datetime.utcnow().strftime('%Y-%m-%d')}.log"


def _cleanup_old_logs() -> None:
    """Delete log files older than KEEP_DAYS."""
    cutoff = datetime.utcnow().timestamp() - (KEEP_DAYS * 86400)
    for f in LOG_DIR.glob("app-*.log"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


class StructuredLogger:
    """
    Structured logger that outputs logs in uvicorn-style format.

    Logs to both:
    - Console (stdout) - for Docker logs
    - File (date-based, e.g. app-2026-02-16.log) - 7 days retained
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

        # Date-based file handler
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            _today_log_file(), mode="a", encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(file_handler)

        _cleanup_old_logs()

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
    """Search log files for entries matching a request ID."""
    matching_logs: list[str] = []
    log_files = sorted(LOG_DIR.glob("app-*.log"), reverse=True)

    for log_file in log_files:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if request_id in line:
                        matching_logs.append(line.strip())
                        if len(matching_logs) >= max_lines:
                            return matching_logs
        except Exception:
            pass

    return matching_logs
