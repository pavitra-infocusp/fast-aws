"""Profile picker — shown at launch and on Ctrl+A."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView, Static

from fast_aws.auth import list_profiles, resolve_region
from fast_aws.executor import AuthError, Executor
from fast_aws.fmt import truncate
from fast_aws.ui.flow import retry_on_login

CSS = """
#profile-screen { align: center middle; height: 100%; }
#profile-dialog {
    width: 64; max-width: 92%; max-height: 80%;
    background: #151b23; border: tall #2f3a48; padding: 1 2;
}
#profile-status { padding: 1 0 0 0; }
#profiles { margin: 1 0 0 0; height: auto; max-height: 24; }
"""


class ProfilePicker(Screen[None]):
    BINDINGS = [
        Binding("escape", "quit_app", "Quit"),
        Binding("q", "quit_app", "Quit"),
    ]

    CSS = CSS

    def compose(self) -> ComposeResult:
        with Container(id="profile-screen"), VerticalScroll(id="profile-dialog"):
            yield Static("fast-aws", classes="dialog-title")
            yield Static("Select an AWS profile to browse", classes="dialog-note")
            yield ListView(id="profiles")
            yield Static("", id="profile-status", classes="dialog-note")

    def on_mount(self) -> None:
        self._profiles = list_profiles()
        lv = self.query_one("#profiles", ListView)
        if not self._profiles:
            self.query_one("#profile-status", Static).update(
                "No profiles found in ~/.aws/config. "
                "Configure AWS first:\n    aws configure   (or)   aws configure sso",
                classes="dialog-error",
            )
            return
        for p in self._profiles:
            badge = "SSO" if p.is_sso else "AKIA"
            region = f" · {p.region}" if p.region else ""
            lv.append(ListItem(Label(f"{p.name:<24} [{badge}]{region}")))
        lv.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self._select(self._profiles[event.index])

    @work(exclusive=False)
    async def _select(self, profile) -> None:
        status = self.query_one("#profile-status", Static)
        status.update(f"Resolving credentials for '{profile.name}'…")
        app = self.app
        region = resolve_region(profile.name, app.cli_region)
        exec = Executor(profile.name, region, readonly=app.readonly)
        try:
            await retry_on_login(
                app,
                exec,
                lambda: exec.call("sts", "get_caller_identity", ttl=False, no_cache=True),
            )
        except AuthError as exc:
            status.update(f"Login failed: {truncate(str(exc), 160)}", classes="dialog-error")
            return
        except Exception as exc:
            status.update(
                f"Could not authenticate: {truncate(str(exc), 160)}", classes="dialog-error"
            )
            return

        app.executor = exec
        app.profile = profile.name
        app.region = region
        from fast_aws.screens.browse import BrowseScreen

        app.switch_screen(BrowseScreen())

    def action_quit_app(self) -> None:
        self.app.exit()
