"""Base class for AWS resource services."""

from __future__ import annotations

from typing import Any

from rich.console import RenderableType

from fast_aws.executor import Executor
from fast_aws.fmt import describe_fallback, detail_fallback
from fast_aws.models import Action, Item, Link, Page


class ResourceService:
    key: str = ""
    name: str = ""
    icon: str = ""

    def __init__(self, exec: Executor):
        self.exec = exec

    async def list_page(self, path: list[str], *, cursor: str | None = None) -> Page:
        """Return one page of items. Never drain the AWS paginator.

        ``cursor`` is the opaque token from a previous ``Page.cursor``.
        """
        raise NotImplementedError

    async def detail(self, item: Item) -> Any:
        return item.payload

    def describe(self, item: Item, detail: Any) -> str:
        """Human-meaningful summary for the inspector; overridden per service."""
        return describe_fallback(detail)

    def detail_body(self, item: Item, detail: Any) -> str | RenderableType:
        """Rich modal body for Enter; default is humanized kv, not raw JSON."""
        return detail_fallback(detail)

    async def links(self, item: Item) -> list[Link]:
        return []

    def actions(self, item: Item) -> list[Action]:
        return []

    async def run_action(self, action_id: str, item: Item) -> str | RenderableType:
        return f"Action '{action_id}' is not implemented for {self.name}"

    def path_label(self, segment: str) -> str:
        """Human label for a path segment in the breadcrumb."""
        return segment

    def filter(self, items: list[Item], query: str) -> list[Item]:
        q = query.strip().lower()
        if not q:
            return items
        return [
            i
            for i in items
            if q in i.label.lower()
            or any(q in _cell_text(c).lower() for c in i.columns)
            or q in str(i.payload).lower()
        ]


def _cell_text(cell: Any) -> str:
    plain = getattr(cell, "plain", None)
    return plain if isinstance(plain, str) else str(cell)


def _pad(item: Item, ncols: int) -> list[Any]:
    cells = list(item.columns)
    while len(cells) < ncols:
        cells.append("")
    return cells[:ncols]
