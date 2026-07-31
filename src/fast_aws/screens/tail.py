"""Live tail of a CloudWatch log group."""

from __future__ import annotations

import asyncio
import time

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import RichLog, Static

from fast_aws.executor import Executor
from fast_aws.fmt import fmt_time_ms, truncate
from fast_aws.ui.theme import TOPBAR

TAIL_WINDOW_MS = 30_000
POLL_SECONDS = 2.0


class TailScreen(Screen[None]):
    BINDINGS = [
        Binding("q", "close", "Close"),
        Binding("escape", "close", "Close"),
        Binding("p", "pause", "Pause"),
        Binding("c", "clear", "Clear"),
    ]

    CSS = """
    #tail-log { height: 1fr; }
    #tail-status { height: 1; color: #64748b; background: #10151c; padding: 0 1; }
    #tail-header { height: 1; color: #7dd3fc; text-style: bold; background: #10151c; padding: 0 1; }
    """ + TOPBAR

    def __init__(self, group: str, exec: Executor):
        super().__init__()
        self._group = group
        self._exec = exec
        self._paused = False

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold #7dd3fc]fast-aws[/] [dim]▸[/] tail [dim]▸[/] {self._group}",
            id="tail-header",
        )
        yield RichLog(id="tail-log", highlight=False, markup=False, wrap=True)
        yield Static("", id="tail-status")

    def on_mount(self) -> None:
        self._worker = self.run_worker(self._poll(), name="log-tail", exclusive=True)

    @work(exclusive=False)
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
                log.write(f"{fmt_time_ms(ts)}  {msg}")
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
