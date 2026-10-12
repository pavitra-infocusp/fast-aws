"""fast-aws Textual application."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import Static

from fast_aws.auth import list_profiles, resolve_region
from fast_aws.config import DEFAULT_THEME, get_theme, set_theme
from fast_aws.executor import Executor
from fast_aws.ui.theme import CSS_PATH


class NoConfigScreen(Screen[None]):
    """Shown when no AWS profiles are configured."""

    BINDINGS = [Binding("q", "quit_app", "Quit"), Binding("escape", "quit_app", "Quit")]

    CSS = """
    Screen { align: center middle; }
    #msg {
        width: 68;
        max-width: 92%;
        background: $background;
        border: round $primary;
        padding: 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]fast-aws[/]\n\n"
            "No profiles found in ~/.aws/config.\n\n"
            "Set up AWS first, then re-launch:\n"
            "    aws configure          (access keys)\n"
            "    aws configure sso      (SSO)\n\n"
            "Or pass a profile directly:\n"
            "    fast-aws --profile <name> --region <region>\n\n"
            "[dim]Press q to quit.[/]",
            id="msg",
        )

    def action_quit_app(self) -> None:
        self.app.exit()


class FastAwsApp(App[None]):
    TITLE = "fast-aws"
    SUB_TITLE = "browse AWS resources"
    CSS_PATH = str(CSS_PATH)
    ENABLE_COMMAND_PALETTE = False  # we ship our own palette on ctrl+p
    ansi_color = True  # use terminal colours; no painted background

    def __init__(
        self,
        profile: str | None = None,
        region: str | None = None,
        readonly: bool = True,
    ):
        super().__init__()
        self.cli_profile = profile
        self.cli_region = region
        self.readonly = readonly
        self.profile: str | None = profile
        self.region: str | None = region
        self.executor: Executor | None = None

    def on_mount(self) -> None:
        saved = get_theme()
        self.theme = saved if saved in self.available_themes else DEFAULT_THEME
        self.theme_changed_signal.subscribe(self, self._on_theme_changed)

        profiles = list_profiles()
        if self.cli_profile:
            self._init_executor(self.cli_profile, self.cli_region)
        elif profiles:
            from fast_aws.screens.profile_picker import ProfilePicker

            # Nothing to fall back to at launch, so the picker can't be cancelled.
            self.push_screen(ProfilePicker(cancellable=False), self._on_launch_profile)
        else:
            self.push_screen(NoConfigScreen())

    def _on_theme_changed(self, theme: Theme) -> None:
        set_theme(theme.name)

    def _init_executor(self, profile: str | None, region: str | None) -> None:
        """Build the executor and show the service picker."""
        self.profile = profile or "default"
        self.region = resolve_region(self.profile, region)
        self.executor = Executor(self.profile, self.region, readonly=self.readonly)
        self._pick_service()

    def _on_launch_profile(self, profile: str | None) -> None:
        if profile is not None:
            self._pick_service()

    def _pick_service(self) -> None:
        from fast_aws.screens.service_picker import ServicePicker

        self.push_screen(ServicePicker(cancellable=False), self._on_launch_service)

    def _on_launch_service(self, key: str | None) -> None:
        if key is None:
            return
        from fast_aws.screens.browse import BrowseScreen
        from fast_aws.services import service_root

        self.push_screen(BrowseScreen(initial=service_root(key)))
