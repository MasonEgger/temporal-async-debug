"""ABOUTME: Smoke test proving the src-layout package imports under the pytest pythonpath.
ABOUTME: Also keeps pytest from exiting 5 (no tests collected) while the package is still empty.
"""

import importlib


def test_package_imports() -> None:
    """The temporal_async_debug package is importable from the src layout."""
    assert importlib.import_module("temporal_async_debug") is not None
