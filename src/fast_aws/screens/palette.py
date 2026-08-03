"""Command palette — fuzzy filter over app-level commands."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static


class PaletteScreen(ModalScreen[str]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, entries: list[tuple[str, str]]):
        super().__init__()
        self._entries = entries
        self._filtered: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog small"):
            yield Static("Command palette", classes="dialog-title")
            yield Input(id="palette-input", placeholder="type to filter…")
            yield ListView(id="palette-list", classes="dialog-list")

    def on_mount(self) -> None:
        self._update_list("")
        self.query_one("#palette-input", Input).focus()

    def _update_list(self, query: str) -> None:
        lv = self.query_one("#palette-list", ListView)
        ql = query.strip().lower()
        self._filtered = [(label, value) for label, value in self._entries if ql in label.lower()]
        lv.clear()
        for label, _value in self._filtered:
            lv.append(ListItem(Label(label)))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "palette-input":
            self._update_list(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._filtered:
            index = self.query_one("#palette-list", ListView).index or 0
            self.dismiss(self._filtered[index][1])

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.dismiss(self._filtered[event.index][1])

    def action_cancel(self) -> None:
        self.dismiss(None)
