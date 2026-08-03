"""Small formatting helpers shared across the app."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from typing import Any


def fmt_bytes(n: int | None) -> str:
    n = n or 0
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TiB"


def fmt_time(ts: Any, tz: bool = True) -> str:
    """Render a datetime, epoch-ms int, or empty string."""
    if ts is None or ts == "":
        return ""
    if isinstance(ts, (int, float)):
        if ts > 10**12:  # milliseconds
            ts = ts / 1000
        try:
            dt = datetime.fromtimestamp(ts, tz=UTC)
        except OverflowError, OSError, ValueError:
            return str(ts)
    elif isinstance(ts, str):
        return ts
    else:
        dt = ts
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
    s = dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    return f"{s} {_tz_label(dt)}" if tz else s


def fmt_time_ms(ts: int | None) -> str:
    return fmt_time(ts)


def _tz_label(dt: datetime) -> str:
    off = dt.utcoffset()
    if off is None:
        return "UTC"
    total = int(off.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{total % 3600 // 60:02d}"


def truncate(s: Any, n: int = 200) -> str:
    s = str(s)
    if len(s) <= n:
        return s
    return s[: n - 3] + "..."


def mask(value: str, keep: int = 8) -> str:
    if not value:
        return "(empty)"
    if len(value) <= keep:
        return "•" * len(value)
    return value[:keep] + "•" * min(12, len(value) - keep)


def pretty(obj: Any, max_len: int = 8000) -> str:
    try:
        text = json.dumps(obj, indent=2, default=str, ensure_ascii=False)
    except TypeError, ValueError:
        text = str(obj)
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def _scalar(value: Any, max_len: int) -> str:
    text = pretty(value, max_len) if isinstance(value, (dict, list)) else str(value)
    return truncate(text.replace("\n", " "), max_len)


def humanize(key: str) -> str:
    """Turn a boto3 key like ``logGroupName`` or ``CreationDate`` into a label."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(key).replace("_", " ").strip())
    return s[:1].upper() + s[1:]


def describe_fallback(obj: Any, max_len: int = 90) -> str:
    """Generic key: value rendering of a boto3 response (used as a last resort)."""
    if not isinstance(obj, dict) or not obj:
        return str(obj) if obj else "(no details)"
    return "\n".join(f"[#94a3b8]{humanize(k)}:[/] {_scalar(v, max_len)}" for k, v in obj.items())


def copy_to_clipboard(value: str) -> bool:
    """Best-effort clipboard copy via available system tool."""
    for tool in ("xclip", "xsel", "wl-copy", "pbcopy"):
        if shutil.which(tool):
            args = [tool, "-selection", "clipboard"] if tool == "xclip" else [tool]
            if tool == "wl-copy":
                args = [tool, "--foreground"]
            try:
                proc = subprocess.run(args, input=value.encode(), capture_output=True)
                return proc.returncode == 0
            except OSError:
                continue
    return False


def unquote_ddb(value: Any) -> str:
    """Convert a DynamoDB attribute value dict to a readable string."""
    if isinstance(value, dict):
        if "S" in value:
            return value["S"]
        if "N" in value:
            return value["N"]
        if "BOOL" in value:
            return str(value["BOOL"])
        if "NULL" in value:
            return "null"
        if "L" in value:
            return "[" + ", ".join(unquote_ddb(v) for v in value["L"]) + "]"
        if "M" in value:
            return "{" + ", ".join(f"{k}: {unquote_ddb(v)}" for k, v in value["M"].items()) + "}"
        if "SS" in value:
            return "[" + ", ".join(value["SS"]) + "]"
        if "NS" in value:
            return "[" + ", ".join(value["NS"]) + "]"
        if "BS" in value:
            return "[binary]"
        return json.dumps(value)
    return str(value)
