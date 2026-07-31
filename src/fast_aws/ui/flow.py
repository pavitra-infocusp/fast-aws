"""Shared async flows: interactive SSO login with automatic retry."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from fast_aws.executor import Executor, LoginRequired
from fast_aws.screens.login import LoginScreen


async def show_login(app, exec: Executor) -> bool:
    """Push the interactive SSO login screen and wait for its result."""
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()

    def callback(result: str | None) -> None:
        if not fut.done():
            fut.set_result(result)

    app.push_screen(LoginScreen(exec), callback)
    result = await fut
    return result == "ok"


async def retry_on_login(app, exec: Executor, fn: Callable[[], Awaitable[Any]], *args: Any, **kwargs: Any):
    """Run an async call; if an SSO login is required, run it and retry once."""
    try:
        return await fn(*args, **kwargs)
    except LoginRequired:
        if await show_login(app, exec):
            return await fn(*args, **kwargs)
        raise
