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

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog small"):
            yield Static("Command palette", classes="dialog-title")
            yield Input(id="palette-input", placeholder="type to filter…")
            yield ListView(id="palette-list", classes="dialog-list")

    def on_mount(self) -> None:
        self._render("")
        self.query_one("#palette-input", Input).focus()

    def _render(self, query: str) -> None:
        lv = self.query_one("#palette-list", ListView)
        lv.clear()
        ql = query.strip().lower()
        for label, value in self._entries:
            if ql in label.lower():
                lv.append(ListItem(Label(label)))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "palette-input":
            self._render(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        lv = self.query_one("#palette-list", ListView)
        if lv.index is not None:
            self.dismiss(self._entries[lv.index][1])

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.dismiss(self._entries[event.index][1])

    def action_cancel(self) -> None:
        self.dismiss(None)
