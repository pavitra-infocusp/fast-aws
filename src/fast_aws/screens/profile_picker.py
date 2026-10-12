"""Profile picker — shown at launch and on Ctrl+A."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Label, ListItem, ListView, Static

from fast_aws.auth import format_expiry, list_profiles, resolve_region, sso_session_expiry
from fast_aws.executor import AuthError, Executor
from fast_aws.fmt import truncate
from fast_aws.ui.flow import retry_on_login
from fast_aws.ui.widgets import BackdropDismissModal


class ProfilePicker(BackdropDismissModal[str | None]):
    """Pick and authenticate a profile.

    Dismisses with the profile name once its credentials resolve — the app's
    executor, profile and region are updated first — or None when cancelled.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("q", "cancel", "Cancel"),
    ]

    def __init__(self, current: str | None = None, *, cancellable: bool = True):
        super().__init__()
        self._current = current
        self._cancellable = cancellable
        self._profiles = list_profiles()
        self._busy = False

    def _allow_backdrop_dismiss(self) -> bool:
        return self._cancellable and not self._busy

    def compose(self) -> ComposeResult:
        items = []
        name_w = max((len(p.name) for p in self._profiles), default=0)
        region_w = max((len(p.region) for p in self._profiles), default=0)
        for p in self._profiles:
            marker = "●" if p.name == self._current else " "
            badge = "SSO " if p.is_sso else "AKIA"
            expiry = format_expiry(sso_session_expiry(p)) if p.is_sso else ""
            text = f"{marker} {p.name:<{name_w}}  [{badge}]  {p.region:<{region_w}}  {expiry}"
            items.append(
                ListItem(
                    Label(text.rstrip(), markup=False),
                    classes="current" if p.name == self._current else "",
                )
            )
        names = [p.name for p in self._profiles]
        index = names.index(self._current) if self._current in names else 0
        hint = "Esc to go back" if self._cancellable else "Esc to quit"
        title = "Switch profile" if self._cancellable else "fast-aws"

        with VerticalScroll(id="profile-dialog", classes="dialog"):
            yield Static(title, classes="dialog-title")
            yield Static("Select an AWS profile to browse", classes="dialog-note")
            yield ListView(*items, initial_index=index, id="profiles")
            yield Static(f"Enter to select · {hint}", classes="dialog-note")
            yield Static("", id="profile-status", classes="dialog-note")

    def on_mount(self) -> None:
        if not self._profiles:
            self._set_status(
                "No profiles found in ~/.aws/config. "
                "Configure AWS first:\n    aws configure   (or)   aws configure sso",
                error=True,
            )
            return
        self.query_one("#profiles", ListView).focus()

    def _set_status(self, msg: str, error: bool = False) -> None:
        status = self.query_one("#profile-status", Static)
        status.update(msg)
        status.set_class(error, "dialog-error")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not self._busy:
            self._select(self._profiles[event.index])

    @work(exclusive=False)
    async def _select(self, profile) -> None:
        self._busy = True
        self._set_status(f"Resolving credentials for '{profile.name}'…")
        app = self.app
        region = resolve_region(profile.name, app.cli_region)
        exec = Executor(profile.name, region, readonly=app.readonly)
        try:
            identity = await retry_on_login(
                app,
                exec,
                lambda: exec.call("sts", "get_caller_identity", ttl=False, no_cache=True),
            )
        except AuthError as exc:
            self._busy = False
            self._set_status(f"Login failed: {truncate(str(exc), 160)}", error=True)
            return
        except Exception as exc:
            self._busy = False
            self._set_status(f"Could not authenticate: {truncate(str(exc), 160)}", error=True)
            return

        exec.apply_caller_identity(identity)
        app.executor = exec
        app.profile = profile.name
        app.region = region
        self.dismiss(profile.name)

    def action_cancel(self) -> None:
        if self._busy:
            return
        if self._cancellable:
            self.dismiss(None)
        else:
            self.app.exit()
