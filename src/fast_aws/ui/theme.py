"""App-wide CSS theme for fast-aws.

The stylesheet lives in a real file (`app.tcss`) so Textual's dev mode
(`uv run textual run --dev`) can hot-reload CSS changes live.
"""

from __future__ import annotations

from pathlib import Path

CSS_PATH = Path(__file__).resolve().parent / "app.tcss"
"""Path to the app stylesheet; used as `FastAwsApp.CSS_PATH`."""
