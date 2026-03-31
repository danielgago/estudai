"""Shared test fixtures for the estudai test suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Use an isolated app data directory for a test.

    Returns:
        Path: The temporary app data directory.
    """
    data_dir = tmp_path / "app-data"
    monkeypatch.setenv("ESTUDAI_DATA_DIR", str(data_dir))
    return data_dir
