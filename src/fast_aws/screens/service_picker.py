"""Service picker — shown after profile auth and when switching services."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Label, ListItem, ListView, Static

from fast_aws.services import SIDEBAR
from fast_aws.ui.widgets import BackdropDismissModal, icon_for


class ServicePicker(BackdropDismissModal[str | None]):
    """Pick a service; dismisses with its key, or None when cancelled."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("q", "cancel", "Cancel"),
    ]

    def __init__(self, current: str | None = None, *, cancellable: bool = True):
        super().__init__()
        self._current = current
        self._cancellable = cancellable

    def _allow_backdrop_dismiss(self) -> bool:
        return self._cancellable

    def compose(self) -> ComposeResult:
        keys = [key for key, _path, _label in SIDEBAR]
        items = [
            ListItem(
                Label(f"{'●' if key == self._current else ' '} {icon_for(key)}  {label}"),
                classes="current" if key == self._current else "",
            )
            for key, _path, label in SIDEBAR
        ]
        index = keys.index(self._current) if self._current in keys else 0
        hint = "Esc to go back" if self._cancellable else "Esc to quit"

        dialog = VerticalScroll(id="service-dialog", classes="dialog")
        dialog.border_title = "Select a service"
        dialog.border_subtitle = f"Enter to open · {hint}"
        with dialog:
            yield Static(id="service-note", classes="dialog-note")
            yield ListView(*items, initial_index=index, id="services-pick")

    def on_mount(self) -> None:
        app = self.app
        self.query_one("#service-note", Static).update(f"{app.profile} · {app.region}")
        self.query_one("#services-pick", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.dismiss(SIDEBAR[event.index][0])

    def action_cancel(self) -> None:
        if self._cancellable:
            self.dismiss(None)
        else:
            self.app.exit()
