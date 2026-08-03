"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from fast_aws import config


@pytest.fixture(autouse=True)
def _isolate_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Keep tests from reading/writing the real ~/.config/fast-aws/config.json."""
    path = tmp_path / "fast-aws-config.json"
    monkeypatch.setattr(config, "_CONFIG_PATH", path)
    monkeypatch.setattr(config, "_CONFIG_DIR", tmp_path)
