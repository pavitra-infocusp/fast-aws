"""CloudWatch Logs service: groups → streams → events, Lambda reverse links, tail."""

from __future__ import annotations

from typing import Any

from rich.console import Group, RenderableType
from rich.text import Text

from fast_aws.fmt import (
    describe_fallback,
    detail_fallback,
    fmt_bytes,
    fmt_time_ms,
    kv,
    kv_block,
    log_message,
    section,
    truncate,
)
from fast_aws.models import Action, Item, Link, Page
from fast_aws.services.base import ResourceService

EVENT_LIMIT = 100


class CloudWatchService(ResourceService):
    key = "logs"
    name = "CloudWatch Logs"
    icon = "📜"

    async def list_page(self, path: list[str], *, cursor: str | None = None) -> Page:
        if not path:
            kwargs: dict[str, Any] = {"limit": 100, "ttl": 30}
            if cursor:
                kwargs["nextToken"] = cursor
            resp = await self.exec.call("logs", "describe_log_groups", **kwargs)
            items = [
                Item(
                    self.key,
                    g.get("logGroupName", ""),
                    g.get("logGroupName", ""),
                    (
                        g.get("logGroupName", "") or "",
                        fmt_bytes(g.get("storedBytes", 0)),
                        fmt_time_ms(g.get("creationTime")),
                        str(g.get("retentionInDays", "∞")),
                    ),
                    kind="log_group",
                    is_dir=True,
                    payload=g,
                )
                for g in resp.get("logGroups", [])
            ]
            return Page(
                ["Log group", "Bytes", "Created", "Retention(d)"],
                items,
                cursor=resp.get("nextToken"),
            )

        group = path[0]
        if len(path) == 1:
            kwargs = {
                "logGroupName": group,
                "orderBy": "LastEventTime",
                "descending": True,
                "limit": 50,
                "ttl": 15,
            }
            if cursor:
                kwargs["nextToken"] = cursor
            resp = await self.exec.call("logs", "describe_log_streams", **kwargs)
            items = [
                Item(
                    self.key,
                    s.get("logStreamName", ""),
                    s.get("logStreamName", ""),
                    (s.get("logStreamName", "") or "", fmt_time_ms(s.get("lastEventTimestamp"))),
                    kind="log_stream",
                    is_dir=True,
                    payload=s,
                )
                for s in resp.get("logStreams", [])
            ]
            return Page(["Stream", "Last event"], items, cursor=resp.get("nextToken"))

        # Event preview stays intentionally bounded (no cursor continuation).
        stream = path[1]
        resp = await self.exec.call(
            "logs",
            "get_log_events",
            logGroupName=group,
            logStreamName=stream,
            startFromHead=False,
            limit=EVENT_LIMIT,
            ttl=10,
        )
        items = [
            Item(
                self.key,
                f"{e.get('timestamp', 0)}-{len(e.get('message', ''))}",
                truncate(e.get("message", ""), 160),
                (fmt_time_ms(e.get("timestamp")), truncate(e.get("message", ""), 300)),
                kind="log_event",
                payload=e,
            )
            for e in resp.get("events", [])
        ]
        return Page(["Timestamp", "Message"], items)

    async def links(self, item: Item) -> list[Link]:
        if item.kind == "log_group":
            name = item.label
            if name.startswith("/aws/lambda/"):
                fn = name[len("/aws/lambda/") :].split("/")[0]
                return [Link("lambda", f"Lambda: {fn}", [], fn, kind="lambda")]
        return []

    def describe(self, item: Item, detail: Any) -> str:
        d = detail if isinstance(detail, dict) else {}
        if item.kind == "log_group":
            ret = d.get("retentionInDays")
            return kv_block(
                [
                    ("Group", d.get("logGroupName", item.label)),
                    ("Bytes", fmt_bytes(d.get("storedBytes", 0))),
                    ("Retention", f"{ret} d" if ret else "forever"),
                    ("Created", fmt_time_ms(d.get("creationTime"))),
                ]
            )
        if item.kind == "log_stream":
            return kv_block(
                [
                    ("Stream", d.get("logStreamName", item.label)),
                    ("Last event", fmt_time_ms(d.get("lastEventTimestamp"))),
                    ("First event", fmt_time_ms(d.get("creationTime"))),
                ]
            )
        if item.kind == "log_event":
            return kv_block(
                [
                    ("Timestamp", fmt_time_ms(d.get("timestamp"))),
                    ("Message", truncate(d.get("message", ""), 300)),
                ]
            )
        return describe_fallback(d)

    def detail_body(self, item: Item, detail: Any) -> str | RenderableType:
        d = detail if isinstance(detail, dict) else {}
        if item.kind == "log_group":
            ret = d.get("retentionInDays")
            return kv_block(
                [
                    ("Group", d.get("logGroupName", item.label)),
                    ("ARN", d.get("arn", "") or "—"),
                    ("Bytes", fmt_bytes(d.get("storedBytes", 0))),
                    ("Retention", f"{ret} d" if ret else "forever"),
                    ("Created", fmt_time_ms(d.get("creationTime"))),
                    ("KMS key", d.get("kmsKeyId", "") or "—"),
                    ("Metric filter count", d.get("metricFilterCount", "") or "—"),
                ]
            )
        if item.kind == "log_stream":
            return kv_block(
                [
                    ("Stream", d.get("logStreamName", item.label)),
                    ("ARN", d.get("arn", "") or "—"),
                    ("Created", fmt_time_ms(d.get("creationTime"))),
                    ("First event", fmt_time_ms(d.get("firstEventTimestamp"))),
                    ("Last event", fmt_time_ms(d.get("lastEventTimestamp"))),
                    ("Last ingestion", fmt_time_ms(d.get("lastIngestionTime"))),
                    ("Stored bytes", fmt_bytes(d.get("storedBytes"))),
                ]
            )
        if item.kind == "log_event":
            msg = d.get("message", "") or ""
            header = Text.from_markup(
                "\n".join(
                    [
                        kv("Timestamp", fmt_time_ms(d.get("timestamp"))),
                        kv("Ingestion", fmt_time_ms(d.get("ingestionTime"))),
                        section("Message"),
                    ]
                )
            )
            return Group(header, log_message(str(msg)))
        return detail_fallback(d)

    def actions(self, item: Item) -> list[Action]:
        if item.kind == "log_group":
            return [Action("tail", "Tail latest events (live)", False)]
        if item.kind == "log_event":
            return []
        return []

    async def run_action(self, action_id: str, item: Item) -> str:
        if action_id == "tail":
            return "OPEN_TAIL"
        return await super().run_action(action_id, item)
