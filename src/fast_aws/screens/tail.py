"""Live tail of a CloudWatch log group."""

from __future__ import annotations

import asyncio
import time

from rich.console import Group
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, RichLog, Static

from fast_aws.executor import Executor
from fast_aws.fmt import fmt_time_ms, log_message, primary_markup, truncate

TAIL_WINDOW_MS = 30_000
POLL_SECONDS = 2.0


class TailScreen(Screen[None]):
    BINDINGS = [
        Binding("q", "close", "Close"),
        Binding("escape", "close", "Close", show=False),
        Binding("p", "pause", "Pause"),
        Binding("c", "clear", "Clear"),
    ]

    CSS = """
    #tail-log { height: 1fr; }
    #tail-status {
        height: 1;
        color: $foreground-muted;
        background: $panel;
        padding: 0 1;
    }
    #tail-header {
        height: 1;
        color: $text-primary;
        text-style: bold;
        background: $panel;
        padding: 0 1;
    }
    """

    def __init__(self, group: str, exec: Executor):
        super().__init__()
        self._group = group
        self._exec = exec
        self._paused = False

    def compose(self) -> ComposeResult:
        yield Static(
            f"{primary_markup('fast-aws')} [dim]▸[/] tail [dim]▸[/] {self._group}",
            id="tail-header",
        )
        yield RichLog(id="tail-log", highlight=False, markup=False, wrap=True)
        yield Static("", id="tail-status")
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        self._worker = self._poll()

    @work(name="log-tail", exclusive=True)
    async def _poll(self) -> None:
        log = self.query_one("#tail-log", RichLog)
        status = self.query_one("#tail-status", Static)
        last = int(time.time() * 1000) - TAIL_WINDOW_MS
        while True:
            if self._paused:
                await asyncio.sleep(0.5)
                continue
            try:
                resp = await self._exec.call(
                    "logs",
                    "filter_log_events",
                    logGroupName=self._group,
                    startTime=last,
                    interleaved=True,
                    limit=200,
                    ttl=False,
                )
            except Exception as exc:
                status.update(f"tail error: {truncate(str(exc), 120)}")
                await asyncio.sleep(POLL_SECONDS)
                continue
            events = resp.get("events", [])
            count = 0
            for e in events:
                ts = e.get("timestamp", 0)
                if ts < last:
                    continue
                last = ts + 1
                msg = e.get("message", "")
                log.write(Group(Text(f"{fmt_time_ms(ts)}  "), log_message(str(msg))))
                count += 1
            status.update(
                f"tail {self._group} · {count} new · {'⏸ paused' if self._paused else 'live'}"
            )
            await asyncio.sleep(POLL_SECONDS)

    def on_unmount(self) -> None:
        worker = getattr(self, "_worker", None)
        if worker is not None:
            worker.cancel()

    def action_close(self) -> None:
        self.app.pop_screen()

    def action_pause(self) -> None:
        self._paused = not self._paused

    def action_clear(self) -> None:
        self.query_one("#tail-log", RichLog).clear()
