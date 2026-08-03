"""UI helpers and shared modal widgets."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from fast_aws.models import Action, Link

SERVICE_ICONS: dict[str, str] = {
    "s3": "🪣",
    "lambda": "λ",
    "dynamodb": "🏬",
    "apigateway": "🔁",
    "cognito": "👤",
    "secretsmanager": "🔐",
    "ssm": "🔧",
    "iam": "🪪",
    "logs": "📜",
    "sqs": "📮",
}


def icon_for(service: str) -> str:
    return SERVICE_ICONS.get(service, "•")


class ConfirmScreen(ModalScreen[bool]):
    """Yes/No confirmation dialog."""

    BINDINGS = [Binding("escape", "no", "No"), Binding("enter", "yes", "Yes")]

    def __init__(self, question: str, title: str = "Confirm", danger: bool = False):
        super().__init__()
        self._question = question
        self._title = title
        self._danger = danger

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog small"):
            yield Static(self._title, classes="dialog-title")
            yield Static(self._question)
            yield Button("No", variant="default", id="no")
            yield Button("Yes", variant="error" if self._danger else "primary", id="yes")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_no(self) -> None:
        self.dismiss(False)

    def action_yes(self) -> None:
        self.dismiss(True)


class ResultScreen(ModalScreen[None]):
    """Show a (possibly long) text result, e.g. secret values."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("b", "dismiss", "Close"),
    ]

    def __init__(self, title: str, body: str, *, markup: bool = False):
        super().__init__()
        self._title = title
        self._body = body
        self._markup = markup

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog"):
            yield Static(self._title, classes="dialog-title")
            yield Static(self._body, id="result-body", markup=self._markup)

    def action_dismiss(self) -> None:
        self.dismiss(None)


class LinksScreen(ModalScreen[Link | None]):
    """Pick a linked resource to jump to."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, links: list[Link]):
        super().__init__()
        self._links = links

    def compose(self) -> ComposeResult:
        from textual.widgets import Label, ListItem, ListView

        with VerticalScroll(classes="dialog small"):
            yield Static("Jump to linked resource", classes="dialog-title")
            yield Label("Press Enter to jump, Esc to cancel", classes="dialog-note")
            items = [
                ListItem(Label(f"{icon_for(link.service)}  {link.title}")) for link in self._links
            ]
            yield ListView(*items, id="links-list", classes="dialog-list")

    def on_mount(self) -> None:
        self.query_one("#links-list").focus()

    def on_list_view_selected(self, event) -> None:
        self.dismiss(self._links[event.list_view.index])

    def action_cancel(self) -> None:
        self.dismiss(None)


class ActionsScreen(ModalScreen[Action | None]):
    """Pick an action for the selected resource."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, actions: list[Action], readonly: bool):
        super().__init__()
        self._actions = actions
        self._readonly = readonly

    def compose(self) -> ComposeResult:
        from textual.widgets import Label, ListItem, ListView

        with VerticalScroll(classes="dialog small"):
            yield Static("Actions", classes="dialog-title")
            if self._readonly:
                yield Label(
                    "Readonly mode — mutating actions hidden (Ctrl+E to enable Edit)",
                    classes="dialog-note",
                )
            items = []
            for action in self._actions:
                if action.mutates and self._readonly:
                    continue
                marker = "✎" if action.mutates else "·"
                items.append(ListItem(Label(f"{marker}  {action.label}")))
            yield ListView(*items, id="actions-list", classes="dialog-list")

    def on_mount(self) -> None:
        self.query_one("#actions-list").focus()

    def on_list_view_selected(self, event) -> None:
        self.dismiss(self._actions[event.list_view.index])

    def action_cancel(self) -> None:
        self.dismiss(None)
