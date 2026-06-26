"""Shared fixtures for the Daikin Madoka test suite."""

import sys
from pathlib import Path

import pytest

# Make `custom_components.daikin_madoka` importable directly (PEP 420 namespace).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in every test."""
    yield
