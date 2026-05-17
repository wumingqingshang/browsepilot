"""Shared fixtures for tests."""

import os
import pytest
from backend.app.config import settings
from backend.app.session_manager import SessionManager


@pytest.fixture
def session_manager(tmp_path):
    """Create a SessionManager pointed at a temp directory."""
    original = settings.data_dir
    settings.data_dir = str(tmp_path)
    os.makedirs(f"{tmp_path}/sessions", exist_ok=True)
    sm = SessionManager(max_active_sessions=10)
    yield sm
    settings.data_dir = original
