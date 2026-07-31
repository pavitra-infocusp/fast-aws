"""Main browse screen: sidebar, list, breadcrumb, inspector, relationships."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Input, Label, ListItem, ListView, Static

from fast_aws.executor import ReadonlyViolation
from fast_aws.fmt import pretty, truncate
from fast_aws.models import Action, Item, Link, Location, Page
from fast_aws.services import SIDEBAR, build_services
from fast_aws.services.base import _pad
from fast_aws.ui.flow import retry_on_login
from fast_aws.ui.widgets import (
    ActionsScreen,
    ConfirmScreen,
    LinksScreen,
    ResultScreen,
    icon_for,
)
from fast_aws.screens.palette import PaletteScreen
from fast_aws.screens.profile_picker import ProfilePicker
from fast_aws.screens.tail import TailScreen


class BrowseScreen(Screen[None]):
    BINDINGS = [
        Binding("ctrl+p", "palette", "Palette"),
        Binding("r", "refresh", "Refresh"),
        Binding("ctrl+e", "toggle_mode", "Mode"),
        Binding("ctrl+a", "switch_profile", "Profile"),
        Binding("escape", "back", "Back"),
        Binding("l", "links", "Links"),
        Binding("a", "actions", "Actions"),
        Binding("i", "toggle_inspector", "Inspector"),
        Binding("/", "filter", "Filter"),
        Binding("f", "filter", "Filter"),
        Binding("g", "top", "Top"),
        Binding("G", "bottom", "Bottom"),
        Binding("q", "quit_app", "Quit"),
    ]

    def __init__(self, initial: Location | None = None):
        super().__init__()
        self._initial = initial
        self._services: dict[str, object] = {}
        self._history: list[Location] = []
        self._loc: Location | None = None
        self._page_items: list[Item] = []
        self._rows: list[Item] = []
        self._filter_query = ""
        self._current: Item | None = None
        self._current_detail: object | None = None
        self._current_links: list[Link] = []
        self._current_actions: list[Action] = []
        self._pending_detail: str | None = None
        self._pending_action: tuple[object, Action, Item] | None = None

    # -- lifecycle ---------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Static(id="topbar")
        with Horizontal(id="layout"):
            yield Sidebar(id="sidebar")
            with Vertical(id="main"):
                yield Static("", id="breadcrumb")
                with Horizontal(id="filter-row", classes="hidden"):
                    yield Static("Filter:", id="filter-label")
                    yield Input(id="filter", placeholder="type to filter…")
                yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
                yield Static("", id="status")
            with VerticalScroll(id="inspector"):
                yield Static("Inspector", id="insp-title")
                yield Static("", id="insp-kind")
                yield Static("Enter → full JSON · i → hide panel", id="insp-note")
                yield Static("", id="insp-detail")
                yield Static("Linked resources (l)", classes="insp-section")
                yield Static("", id="insp-links")
                yield Static("Actions (a)", classes="insp-section")
                yield Static("", id="insp-actions")

    def on_mount(self) -> None:
        self._services = build_services(self.app.executor)
        self._refresh_topbar()

        lv = self.query_one("#services", ListView)
        for key, path, label in SIDEBAR:
            lv.append(ListItem(Label(f"{icon_for(key)}  {label}")))
        lv.focus()

        if self._initial is not None:
            self._navigate(self._initial, push_history=False)
        else:
            first = SIDEBAR[0]
            self._navigate(Location(first[0], first[1], label=first[2]), push_history=False)

    def _refresh_topbar(self) -> None:
        exec = self.app.executor
        mode = exec.mode_label
        color = "#fbbf24" if exec.readonly else "#f87171"
        self.query_one("#topbar", Static).update(
            f"[bold #7dd3fc]fast-aws[/] [dim]▸[/] [#94a3b8]{self.app.profile}[/] "
            f"[dim]▸[/] {self.app.region}    [bold {color}]{mode}[/]"
        )

    # -- navigation --------------------------------------------------------
    def _navigate(self, loc: Location, push_history: bool = True) -> None:
        if push_history and self._loc is not None:
            if self._loc.service_key != loc.service_key or self._loc.path != loc.path:
                self._history.append(self._loc)
        self._loc = loc
        self._load(loc)

    @work(exclusive=False)
    async def _load(self, loc: Location) -> None:
        svc = self._services[loc.service_key]
        self._set_status(f"Loading {svc.name}…")
        try:
            page = await retry_on_login(self.app, self.app.executor, lambda: svc.list_page(loc.path))
        except Exception as exc:
            self._set_status(f"Error loading {svc.name}: {truncate(str(exc), 160)}", error=True)
            return
        self._render_page(loc, page)
        self._set_status(f"{svc.name} · {len(self._page_items)} items")

    def _render_page(self, loc: Location, page: Page) -> None:
        self._loc = loc
        self._filter_query = ""
        self._update_breadcrumb()
        table = self.query_one("#table", DataTable)
        table.clear(columns=True)
        cols = page.columns or ["Value"]
        for col in cols:
            table.add_column(col, key=col)
        self._page_items = page.items
        self._rebuild_table()
        if loc.selected_id:
            self._select_id(loc.selected_id)
        table.focus()

    def _rebuild_table(self) -> None:
        svc = self._services[self._loc.service_key]
        items = svc.filter(self._page_items, self._filter_query)
        table = self.query_one("#table", DataTable)
        table.clear()
        n = len(table.columns)
        self._rows = []
        for i, item in enumerate(items):
            table.add_row(*_pad(item, n), key=f"row{i}")
            self._rows.append(item)
        if self._rows:
            table.move_cursor(row=0)

    def _select_id(self, selected_id: str) -> None:
        for i, item in enumerate(self._rows):
            if item.id == selected_id:
                self.query_one("#table", DataTable).move_cursor(row=i)
                return

    def _update_breadcrumb(self) -> None:
        svc = self._services[self._loc.service_key]
        parts = [f"[bold #7dd3fc]{svc.icon} {svc.name}[/]"]
        for seg in self._loc.path:
            parts.append(f"[dim]/[/][#94a3b8]{truncate(seg, 40)}[/]")
        if self._current is not None and self._current.label:
            last = self._loc.path[-1] if self._loc.path else None
            if not (self._current.is_dir and self._current.label == last):
                parts.append(f"[dim]▸[/][#e2e8f0]{truncate(self._current.label, 40)}[/]")
        self.query_one("#breadcrumb", Static).update("  ".join(parts))

    # -- selection / inspector ---------------------------------------------
    def _selected_item(self) -> Item | None:
        table = self.query_one("#table", DataTable)
        row = table.cursor_row
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        row = event.cursor_row
        if 0 <= row < len(self._rows):
            self._load_detail(self._rows[row])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row = event.cursor_row
        if 0 <= row < len(self._rows):
            self._open_item(self._rows[row])

    @work(exclusive=False)
    async def _load_detail(self, item: Item) -> None:
        svc = self._services[item.service]
        token = f"{item.service}:{item.id}"
        self._pending_detail = token
        try:
            detail = await retry_on_login(self.app, self.app.executor, lambda: svc.detail(item))
        except Exception as exc:
            if self._pending_detail == token:
                self._set_status(f"Detail error: {truncate(str(exc), 120)}", error=True)
            return
        try:
            links = await svc.links(item)
        except Exception:
            links = []
        actions = svc.actions(item)
        if self._pending_detail == token:
            self._pending_detail = None
            self._current = item
            self._current_detail = detail
            self._current_links = links
            self._current_actions = actions
            self._render_inspector(item, detail, links, actions)

    def _render_inspector(self, item: Item, detail: object, links: list[Link], actions: list[Action]) -> None:
        svc = self._services[item.service]
        self.query_one("#insp-title", Static).update(item.label)
        self.query_one("#insp-kind", Static).update(f"{svc.icon} {svc.name} · {item.kind}")
        body = svc.describe(item, detail)
        self.query_one("#insp-detail", Static).update(body)
        link_lines = "\n".join(f"{icon_for(l.service)}  {l.title}" for l in links) or "(none)"
        self.query_one("#insp-links", Static).update(link_lines)
        act_lines = "\n".join(f"{('✎' if a.mutates else '·')}  {a.label}" for a in actions) or "(none)"
        self.query_one("#insp-actions", Static).update(act_lines)
        self._update_breadcrumb()

    def _set_status(self, msg: str, error: bool = False) -> None:
        status = self.query_one("#status", Static)
        status.update(msg)
        status.set_class(error, "error")

    # -- actions -----------------------------------------------------------
    def _open_item(self, item: Item) -> None:
        if item.is_dir:
            new_path = self._loc.path + [item.id]
            self._navigate(Location(self._loc.service_key, new_path, label=item.label))
        else:
            self.app.push_screen(ResultScreen(item.label, pretty(self._current_detail or item.payload)))

    def action_open(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        if self.query_one("#filter", Input).has_focus:
            return
        self._open_item(item)

    def action_back(self) -> None:
        if not self.query_one("#filter-row").has_class("hidden"):
            self._hide_filter()
            return
        if self._history:
            loc = self._history.pop()
            self._loc = loc
            self._load(loc)
        else:
            self.notify("At top level — Ctrl+A to switch profile", timeout=2)

    def action_links(self) -> None:
        if not self._current_links:
            self.notify("No linked resources for this selection", timeout=2)
            return
        self.app.push_screen(LinksScreen(self._current_links), self._on_link_picked)

    def _on_link_picked(self, link: Link | None) -> None:
        if link is None:
            return
        self._navigate(Location(link.service, link.path, link.id, label=link.title))

    def action_actions(self) -> None:
        if not self._current_actions:
            self.notify("No actions for this selection", timeout=2)
            return
        self.app.push_screen(
            ActionsScreen(self._current_actions, self.app.executor.readonly), self._on_action_picked
        )

    def _on_action_picked(self, action: Action | None) -> None:
        if action is None or self._current is None:
            return
        svc = self._services[self._current.service]
        if action.mutates:
            self._pending_action = (svc, action, self._current)
            self.app.push_screen(
                ConfirmScreen(
                    f"Run '{action.label}' on '{self._current.label}'?", danger=True
                ),
                self._on_action_confirmed,
            )
        else:
            self._run_action(svc, action, self._current)

    def _on_action_confirmed(self, confirmed: bool | None) -> None:
        if not confirmed or self._pending_action is None:
            self._pending_action = None
            return
        svc, action, item = self._pending_action
        self._pending_action = None
        self._run_action(svc, action, item)

    @work(exclusive=False)
    async def _run_action(self, svc, action: Action, item: Item) -> None:
        try:
            result = await retry_on_login(
                self.app, self.app.executor, lambda: svc.run_action(action.id, item)
            )
        except ReadonlyViolation as exc:
            self.notify(str(exc), severity="error", timeout=4)
            return
        except Exception as exc:
            self.notify(f"Action failed: {truncate(str(exc), 160)}", severity="error", timeout=4)
            return
        if result == "OPEN_TAIL":
            self.app.push_screen(TailScreen(item.label, self.app.executor))
        elif result and len(result) > 300:
            self.app.push_screen(ResultScreen(action.label, result))
        else:
            self.notify(result or "Done", timeout=3)

    # -- filter ------------------------------------------------------------
    def action_filter(self) -> None:
        row = self.query_one("#filter-row")
        row.remove_class("hidden")
        self.query_one("#filter", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter":
            self._filter_query = event.value
            self._rebuild_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "filter":
            self._hide_filter()

    def _hide_filter(self) -> None:
        row = self.query_one("#filter-row")
        row.add_class("hidden")
        inp = self.query_one("#filter", Input)
        inp.value = ""
        self._filter_query = ""
        self._rebuild_table()
        self.query_one("#table", DataTable).focus()

    # -- top-level ---------------------------------------------------------
    def action_refresh(self) -> None:
        self.app.executor.bust()
        self.notify("Cache cleared — refreshing", timeout=2)
        if self._loc is not None:
            self._load(self._loc)

    def action_toggle_mode(self) -> None:
        exec = self.app.executor
        target = "Edit" if exec.readonly else "Readonly"
        self.app.push_screen(
            ConfirmScreen(f"Switch to {target} mode?", danger=not exec.readonly),
            self._on_mode_confirmed,
        )

    def _on_mode_confirmed(self, confirmed: bool | None) -> None:
        if confirmed:
            exec = self.app.executor
            exec.set_readonly(not exec.readonly)
            self._refresh_topbar()
            self.notify(f"Mode: {exec.mode_label}", timeout=3)
            if self._current is not None:
                self._load_detail(self._current)

    def action_switch_profile(self) -> None:
        self.app.switch_screen(ProfilePicker())

    def action_palette(self) -> None:
        self.app.push_screen(PaletteScreen(self._palette_entries()), self._on_palette)

    def _palette_entries(self) -> list[tuple[str, str]]:
        entries = [
            ("Switch profile", "profile"),
            ("Toggle Readonly/Edit mode", "mode"),
            ("Refresh (clear cache)", "refresh"),
            ("Quit fast-aws", "quit"),
        ]
        for key, path, label in SIDEBAR:
            entries.append((f"{icon_for(key)}  Go to {label}", f"go:{key}"))
        return entries

    def _on_palette(self, value: str | None) -> None:
        if not value:
            return
        if value == "profile":
            self.action_switch_profile()
        elif value == "mode":
            self.action_toggle_mode()
        elif value == "refresh":
            self.action_refresh()
        elif value == "quit":
            self.app.push_screen(
                ConfirmScreen("Quit fast-aws?", danger=True), lambda yes: self.app.exit() if yes else None
            )
        elif value.startswith("go:"):
            key = value.split(":", 1)[1]
            entry = next(e for e in SIDEBAR if e[0] == key)
            self._navigate(Location(entry[0], entry[1], label=entry[2]))

    def action_quit_app(self) -> None:
        self.app.push_screen(
            ConfirmScreen("Quit fast-aws?", danger=True), lambda yes: self.app.exit() if yes else None
        )

    def action_toggle_inspector(self) -> None:
        inspector = self.query_one("#inspector")
        if inspector.has_class("hidden"):
            inspector.remove_class("hidden")
            self.notify("Inspector shown (i)", timeout=2)
        else:
            inspector.add_class("hidden")
            self.notify("Inspector hidden — i to show", timeout=2)

    def action_top(self) -> None:
        table = self.query_one("#table", DataTable)
        if self._rows:
            table.move_cursor(row=0)

    def action_bottom(self) -> None:
        table = self.query_one("#table", DataTable)
        if self._rows:
            table.move_cursor(row=len(self._rows) - 1)


class Sidebar(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Static("SERVICES", id="sidebar-title")
        yield ListView(id="services")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        screen = self.app.screen
        if isinstance(screen, BrowseScreen):
            key, path, label = SIDEBAR[event.index]
            screen._navigate(Location(key, path, label=label))
