"""Persistent user config for fast-aws (JSON under ~/.config/fast-aws/)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_THEME = "textual-dark"

_CONFIG_DIR = Path.home() / ".config" / "fast-aws"
_CONFIG_PATH = _CONFIG_DIR / "config.json"


def config_path() -> Path:
    """Return the config file path (overridable in tests via monkeypatch)."""
    return _CONFIG_PATH


def load() -> dict[str, Any]:
    """Load config JSON; return {} on missing or corrupt file."""
    path = config_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save(data: dict[str, Any]) -> None:
    """Write config JSON, creating the config directory if needed."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def get_theme() -> str:
    """Return the saved theme name, or the default."""
    theme = load().get("theme")
    return theme if isinstance(theme, str) and theme else DEFAULT_THEME


def set_theme(name: str) -> None:
    """Persist the selected theme name."""
    data = load()
    data["theme"] = name
    save(data)
