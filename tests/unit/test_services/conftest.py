import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from prometheus_client import REGISTRY

# Required env vars for Config (set BEFORE any app imports)
_TEST_ENV = {
    "SMALL_LLM_SERVICE_URL": "http://test-small-llm:8005",
    "SMALL_LLM_MODEL_NAME": "test-model",
    "SMALL_LLM_API_KEY": "test-key",
    "FINE_TUNED_MODEL_SERVICE_URL": "http://test-fine-tuned:8006",
    "FINE_TUNED_MODEL_NAME": "test-model",
    "FINE_TUNED_MODEL_API_KEY": "test-key",
    "LARGE_LLM_MODEL_NAME": "test-model",
    "REFORMULATOR_LLM_SERVICE_URL": "http://test-reformulator:8007",
    "REFORMULATOR_LLM_MODEL_NAME": "test-model",
    "REFORMULATOR_LLM_API_KEY": "test-key",
    "QDRANT_HOST": "localhost",
    "QDRANT_PORT": "6333",
}


def _ensure_env():
    """Set required env vars (only if not already set)."""
    for key, value in _TEST_ENV.items():
        os.environ.setdefault(key, value)


def _ensure_path():
    """Add project root to sys.path."""
    project_root = str(Path(__file__).parent.parent.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


def _mock_logging():
    """Inject mocked src.logging_utils into sys.modules."""
    mock_logging_utils = MagicMock()
    mock_logger_class = MagicMock()
    mock_logger_instance = MagicMock()
    mock_logger_class.return_value = mock_logger_instance
    mock_logging_utils.StructuredLogger = mock_logger_class
    mock_logging_utils.generate_request_id = MagicMock(return_value="test-request-id")
    mock_logging_utils.get_logs_by_request_id = MagicMock(return_value=[])
    sys.modules["src.logging_utils"] = mock_logging_utils


def load_app():
    """
    Load the consolidated FastAPI app for testing.

    Sets up dummy env vars, mocks logging_utils, and imports src.main.
    """
    _ensure_env()
    _ensure_path()
    _mock_logging()

    src_main = importlib.import_module("src.main")
    return src_main.app


def cleanup_modules():
    """Clean up all src.* modules from sys.modules and Prometheus registry."""
    modules_to_remove = [
        key
        for key in list(sys.modules.keys())
        if key.startswith("src.") or key == "src"
    ]
    for module_name in modules_to_remove:
        del sys.modules[module_name]

    # Remove project root from sys.path if it was added
    project_root = str(Path(__file__).parent.parent.parent.parent)
    sys.path[:] = [p for p in sys.path if p != project_root]

    # Clear Prometheus collectors to avoid duplication errors
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass


@pytest.fixture(scope="module")
def app():
    """Load the consolidated app — keeps modules loaded for entire test module."""
    the_app = load_app()
    yield the_app
    cleanup_modules()
