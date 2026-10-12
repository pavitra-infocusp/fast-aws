"""Unit tests for persistent JSON config."""

from __future__ import annotations

from fast_aws import config


def test_load_missing_returns_empty():
    assert config.load() == {}


def test_load_corrupt_returns_empty():
    config.config_path().write_text("{not-json", encoding="utf-8")
    assert config.load() == {}


def test_get_theme_default():
    assert config.get_theme() == config.DEFAULT_THEME


def test_set_theme_round_trip():
    config.set_theme("nord")
    assert config.get_theme() == "nord"
    data = config.load()
    assert data == {"theme": "nord"}


def test_set_theme_preserves_other_keys():
    config.save({"theme": "dracula", "extra": 1})
    config.set_theme("gruvbox")
    assert config.load() == {"theme": "gruvbox", "extra": 1}


def test_get_theme_ignores_non_string():
    config.save({"theme": 123})
    assert config.get_theme() == config.DEFAULT_THEME


def test_mask_secret():
    from fast_aws import fmt

    assert fmt.mask_secret("API_TOKEN", "abc") == fmt.MASK
    assert fmt.mask_secret("REGION", "us-east-1") == "us-east-1"
    masked = fmt.mask_secret("DATABASE_URL", "postgresql://u:pw@host:5432/db")
    assert "pw" not in masked and "u:" in masked and "@host" in masked
