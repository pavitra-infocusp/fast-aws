"""Interactive SSO login screen that streams `aws sso login` output."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import RichLog, Static

from fast_aws.executor import AuthError, Executor
from fast_aws.fmt import truncate
from fast_aws.ui.widgets import BackdropDismissModal


class LoginScreen(BackdropDismissModal[str]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, exec: Executor):
        super().__init__()
        self._exec = exec

    def _backdrop_result(self) -> str:
        return "cancel"

    def compose(self) -> ComposeResult:
        dialog = VerticalScroll(classes="dialog")
        dialog.border_title = "SSO login"
        dialog.border_subtitle = "Esc to cancel"
        with dialog:
            yield Static(
                "If a browser did not open automatically, copy the URL below and authorize in it.",
                classes="dialog-note",
            )
            yield RichLog(id="login-log", highlight=False, markup=False, wrap=True)
            yield Static("", id="login-status", classes="dialog-note")

    def on_mount(self) -> None:
        self._run()

    @work(exclusive=False)
    async def _run(self) -> None:
        log = self.query_one("#login-log", RichLog)
        status = self.query_one("#login-status", Static)
        try:
            await self._exec.sso_login_stream(lambda line: log.write(line))
            log.write("Login complete.")
            status.update(f"Authenticated as {self._exec.profile}")
            self.dismiss("ok")
        except AuthError as exc:
            log.write(f"Login failed: {exc}")
            status.update(f"Login failed: {truncate(str(exc), 200)}", classes="dialog-error")
            self.dismiss("error")

    def action_cancel(self) -> None:
        self.dismiss("cancel")
