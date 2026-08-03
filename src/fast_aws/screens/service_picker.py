"""Service picker — shown after profile auth and when switching services."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView, Static

from fast_aws.models import Location
from fast_aws.services import SIDEBAR
from fast_aws.ui.widgets import icon_for

CSS = """
#service-screen { align: center middle; height: 100%; }
#service-dialog {
    width: 64; max-width: 92%; max-height: 80%;
    background: #151b23; border: tall #2f3a48; padding: 1 2;
}
#services-pick { margin: 1 0 0 0; height: auto; max-height: 24; }
"""


class ServicePicker(Screen[None]):
    BINDINGS = [
        Binding("escape", "quit_app", "Quit"),
        Binding("q", "quit_app", "Quit"),
    ]

    CSS = CSS

    def compose(self) -> ComposeResult:
        with Container(id="service-screen"), VerticalScroll(id="service-dialog"):
            yield Static("Select a service", classes="dialog-title")
            yield Static(id="service-note", classes="dialog-note")
            yield ListView(id="services-pick")

    def on_mount(self) -> None:
        app = self.app
        note = f"{app.profile} · {app.region}"
        self.query_one("#service-note", Static).update(note)

        lv = self.query_one("#services-pick", ListView)
        for key, _path, label in SIDEBAR:
            lv.append(ListItem(Label(f"{icon_for(key)}  {label}")))
        lv.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        key, path, label = SIDEBAR[event.index]
        from fast_aws.screens.browse import BrowseScreen

        self.app.switch_screen(BrowseScreen(initial=Location(key, path, label=label)))

    def action_quit_app(self) -> None:
        self.app.exit()
