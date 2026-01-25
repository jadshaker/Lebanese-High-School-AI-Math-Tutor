import importlib
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY


def load_service_app_for_module(service_name: str) -> Any:
    """
    Load a service's FastAPI app for a test module.

    This function loads the service with mocked logging and keeps modules
    in sys.modules for the duration of the test module (including during
    test collection when @patch decorators are evaluated). Cleanup happens
    after the module completes.

    Args:
        service_name: Name of the service directory (e.g., 'gateway', 'large_llm')

    Returns:
        The FastAPI app instance
    """
    # Get absolute path to service
    service_path = Path(__file__).parent.parent.parent.parent / "services" / service_name
    service_parent = str(service_path)

    # Add service's parent directory to sys.path
    if service_parent not in sys.path:
        sys.path.insert(0, service_parent)

    # Mock StructuredLogger to avoid file system issues
    # This mock needs to be in sys.modules BEFORE we import src.main
    # so that @patch decorators can resolve correctly during test collection
    mock_logging_utils = MagicMock()
    mock_logger_class = MagicMock()
    mock_logger_instance = MagicMock()
    mock_logger_class.return_value = mock_logger_instance
    mock_logging_utils.StructuredLogger = mock_logger_class
    mock_logging_utils.generate_request_id = MagicMock(return_value="test-request-id")
    mock_logging_utils.get_logs_by_request_id = MagicMock(return_value=[])

    # Inject mocks BEFORE importing
    sys.modules['src.logging_utils'] = mock_logging_utils

    # Import the main module - this stays in sys.modules for the test module duration
    src_main = importlib.import_module('src.main')
    app = src_main.app

    return app


def cleanup_service_modules():
    """Clean up service modules from sys.modules, sys.path, and Prometheus registry."""
    modules_to_remove = [
        'src.main',
        'src.config',
        'src.logging_utils',
        'src.metrics',
        'src.models',
        'src.models.schemas',
        'src',
    ]

    for module_name in modules_to_remove:
        if module_name in sys.modules:
            del sys.modules[module_name]

    # Remove service paths from sys.path
    services_dir = str(Path(__file__).parent.parent.parent.parent / "services")
    sys.path[:] = [p for p in sys.path if not p.startswith(services_dir)]

    # Clear Prometheus collectors to avoid duplication errors
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            # Ignore errors if collector was already unregistered
            pass


@pytest.fixture(scope="module")
def gateway_app():
    """Load gateway service app - keeps modules loaded for entire test module"""
    app = load_service_app_for_module("gateway")
    yield app
    cleanup_service_modules()


@pytest.fixture(scope="module")
def large_llm_app():
    """Load large_llm service app - keeps modules loaded for entire test module"""
    app = load_service_app_for_module("large_llm")
    yield app
    cleanup_service_modules()


@pytest.fixture(scope="module")
def embedding_app():
    """Load embedding service app - keeps modules loaded for entire test module"""
    app = load_service_app_for_module("embedding")
    yield app
    cleanup_service_modules()


@pytest.fixture(scope="module")
def cache_app():
    """Load cache service app - keeps modules loaded for entire test module"""
    app = load_service_app_for_module("cache")
    yield app
    cleanup_service_modules()


@pytest.fixture(scope="module")
def small_llm_app():
    """Load small_llm service app - keeps modules loaded for entire test module"""
    app = load_service_app_for_module("small_llm")
    yield app
    cleanup_service_modules()


@pytest.fixture(scope="module")
def fine_tuned_model_app():
    """Load fine_tuned_model service app - keeps modules loaded for entire test module"""
    app = load_service_app_for_module("fine_tuned_model")
    yield app
    cleanup_service_modules()


@pytest.fixture(scope="module")
def input_processor_app():
    """Load input_processor service app - keeps modules loaded for entire test module"""
    app = load_service_app_for_module("input_processor")
    yield app
    cleanup_service_modules()


@pytest.fixture(scope="module")
def reformulator_app():
    """Load reformulator service app - keeps modules loaded for entire test module"""
    app = load_service_app_for_module("reformulator")
    yield app
    cleanup_service_modules()
