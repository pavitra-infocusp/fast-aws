"""Base class for AWS resource services."""

from __future__ import annotations

from typing import Any

from fast_aws.executor import Executor
from fast_aws.models import Action, Item, Link, Page


class ResourceService:
    key: str = ""
    name: str = ""
    icon: str = ""

    def __init__(self, exec: Executor):
        self.exec = exec

    async def list_page(self, path: list[str]) -> Page:
        raise NotImplementedError

    async def detail(self, item: Item) -> Any:
        return item.payload

    async def links(self, item: Item) -> list[Link]:
        return []

    def actions(self, item: Item) -> list[Action]:
        return []

    async def run_action(self, action_id: str, item: Item) -> str:
        return f"Action '{action_id}' is not implemented for {self.name}"

    def filter(self, items: list[Item], query: str) -> list[Item]:
        q = query.strip().lower()
        if not q:
            return items
        return [
            i
            for i in items
            if q in i.label.lower()
            or any(q in str(c).lower() for c in i.columns)
            or q in str(i.payload).lower()
        ]


def _pad(item: Item, ncols: int) -> list[str]:
    cells = list(item.columns)
    while len(cells) < ncols:
        cells.append("")
    return cells[:ncols]
