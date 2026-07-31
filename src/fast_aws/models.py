"""Shared data models for resources, pages, links, and actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Item:
    """A single browsable row in a service listing."""

    service: str
    id: str
    label: str
    columns: tuple[str, ...] = ()
    kind: str = ""
    is_dir: bool = False
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Page:
    """The result of listing a service location."""

    columns: list[str]
    items: list[Item]


@dataclass
class Link:
    """A jump to a resource in another (or same) service."""

    service: str
    title: str
    path: list[str]
    id: str
    kind: str = ""


@dataclass
class Action:
    """An operation available on a selected resource."""

    id: str
    label: str
    mutates: bool = False


@dataclass
class Location:
    """Navigation state: where in the service tree the user is."""

    service_key: str
    path: list[str]
    selected_id: str = ""
    label: str = ""
