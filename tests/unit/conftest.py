import os
import sys

import pytest


@pytest.fixture(scope="function", autouse=True)
def isolate_imports():
    """
    Isolate imports between tests to prevent sys.path pollution.

    Each test file adds its service directory to sys.path, but this can cause
    conflicts when running all tests together. This fixture cleans up after each test.
    """
    # Store original sys.path
    original_path = sys.path.copy()

    # Store original modules to clean up service-specific imports
    original_modules = set(sys.modules.keys())

    yield

    # Restore sys.path
    sys.path[:] = original_path

    # Remove any service-specific modules that were imported
    # (modules starting with 'src.' that were added during the test)
    new_modules = set(sys.modules.keys()) - original_modules
    for module_name in new_modules:
        if module_name.startswith('src.') or module_name == 'src':
            del sys.modules[module_name]


@pytest.fixture(scope="session", autouse=True)
def disable_prometheus_metrics():
    """Disable Prometheus metrics multiprocess mode for tests"""
    # Prevent prometheus from trying to use multiprocess mode
    os.environ.pop("PROMETHEUS_MULTIPROC_DIR", None)
