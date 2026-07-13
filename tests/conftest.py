"""Shared pytest fixtures for the rizza test suite."""

import os
import tempfile

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolate_rizza_directory():
    """Point RIZZA_DIRECTORY at a session-scoped temp dir.

    Config.base_dir defaults to ~/rizza, and several tests construct a bare
    Config() without overriding base_dir. Without this, those tests read and
    write real user data (genetic tests, telemetry) under the real home
    directory instead of an isolated location.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["RIZZA_DIRECTORY"] = tmpdir
        yield
        del os.environ["RIZZA_DIRECTORY"]
