"""Lazy-loading DataTable: appends rows when the cursor/scroll nears the end."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from textual.message import Message
from textual.widgets import DataTable

from fast_aws.models import Item
from fast_aws.services.base import _pad

NEAR_END_ROWS = 5


class LazyDataTable(DataTable[Any]):
    """DataTable that requests more rows when the user approaches the end.

    Owns near-end detection and loading debounce. Does not fetch AWS data —
    the parent screen handles ``MoreNeeded`` by calling the service and then
    ``append_page``.
    """

    class MoreNeeded(Message):
        """Posted when another page should be fetched."""

    class PageLoaded(Message):
        """Posted after rows are set or appended (for status-bar updates)."""

        def __init__(self, loaded: int, has_more: bool) -> None:
            self.loaded = loaded
            self.has_more = has_more
            super().__init__()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._all_items: list[Item] = []
        self._visible: list[Item] = []
        self._next_cursor: str | None = None
        self._fetching = False
        self._filter_fn: Callable[[Item], bool] | None = None
        self._ncols = 0

    # -- public state ------------------------------------------------------
    @property
    def next_cursor(self) -> str | None:
        return self._next_cursor

    @property
    def has_more(self) -> bool:
        return self._next_cursor is not None

    @property
    def fetching(self) -> bool:
        return self._fetching

    @property
    def loaded_count(self) -> int:
        return len(self._all_items)

    @property
    def rows_items(self) -> list[Item]:
        """Items currently shown (after local filter)."""
        return self._visible

    def begin_loading(self) -> None:
        self._fetching = True

    def end_loading(self) -> None:
        self._fetching = False

    # -- page management ---------------------------------------------------
    def reset(self, columns: Sequence[str]) -> None:
        """Clear all rows and recreate columns for a new location."""
        self._all_items = []
        self._visible = []
        self._next_cursor = None
        self._fetching = False
        self._filter_fn = None
        self.clear(columns=True)
        cols = list(columns) or ["Value"]
        for col in cols:
            self.add_column(col, key=col)
        self._ncols = len(cols)

    def set_page(self, items: Sequence[Item], *, cursor: str | None) -> None:
        """Replace the buffer with the first page of results."""
        self._all_items = list(items)
        self._next_cursor = cursor
        self._fetching = False
        self._rebuild_visible(move_to_top=True)
        self.post_message(self.PageLoaded(len(self._all_items), self.has_more))

    def append_page(self, items: Sequence[Item], *, cursor: str | None) -> None:
        """Append another page without clearing the existing buffer."""
        self._all_items.extend(items)
        self._next_cursor = cursor
        self._fetching = False
        # When filtering, rebuild; otherwise append only new visible rows.
        if self._filter_fn is not None:
            self._rebuild_visible(move_to_top=False)
        else:
            start = len(self._visible)
            for i, item in enumerate(items):
                self.add_row(*_pad(item, self._ncols), key=f"row{start + i}")
                self._visible.append(item)
        self.post_message(self.PageLoaded(len(self._all_items), self.has_more))
        self._maybe_request_more()

    def apply_filter(self, predicate: Callable[[Item], bool] | None) -> None:
        """Filter the loaded buffer locally without clearing pagination state."""
        self._filter_fn = predicate
        self._rebuild_visible(move_to_top=True)

    def item_at(self, row: int) -> Item | None:
        if 0 <= row < len(self._visible):
            return self._visible[row]
        return None

    def select_id(self, selected_id: str) -> None:
        for i, item in enumerate(self._visible):
            if item.id == selected_id:
                self.move_cursor(row=i)
                return

    # -- internals ---------------------------------------------------------
    def _rebuild_visible(self, *, move_to_top: bool) -> None:
        pred = self._filter_fn
        self._visible = [i for i in self._all_items if pred is None or pred(i)]
        self.clear()
        for i, item in enumerate(self._visible):
            self.add_row(*_pad(item, self._ncols), key=f"row{i}")
        if self._visible and move_to_top:
            self.move_cursor(row=0)

    def _maybe_request_more(self) -> None:
        if self._fetching or not self.has_more:
            return
        # Local filter covers the loaded buffer only — don't keep fetching
        # while filtering (that would silently drain the account).
        if self._filter_fn is not None:
            return
        n = len(self._visible)
        if n == 0:
            self._fetching = True
            self.post_message(self.MoreNeeded())
            return
        near_cursor = self.cursor_row >= max(0, n - NEAR_END_ROWS)
        near_scroll = self.is_vertical_scroll_end
        if near_cursor or near_scroll:
            self._fetching = True
            self.post_message(self.MoreNeeded())

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        self._maybe_request_more()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        # Bubble still reaches the screen; we only use this for load-more.
        self._maybe_request_more()
