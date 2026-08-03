"""DynamoDB service: tables and bounded scans."""

from __future__ import annotations

import json
from typing import Any

from botocore.exceptions import ClientError

from fast_aws.fmt import fmt_bytes, fmt_time, pretty, truncate, unquote_ddb
from fast_aws.models import Item, Link, Page
from fast_aws.services.base import ResourceService

SCAN_LIMIT = 25


class DynamoDBService(ResourceService):
    key = "dynamodb"
    name = "DynamoDB"
    icon = "🏬"

    async def list_page(self, path: list[str]) -> Page:
        if not path:
            names = (await self.exec.call("dynamodb", "list_tables", ttl=30)).get("TableNames", [])
            items: list[Item] = []
            for name in names:
                try:
                    d = await self.exec.call("dynamodb", "describe_table", TableName=name, ttl=300)
                    t = d.get("Table", {})
                    items.append(
                        Item(
                            self.key,
                            name,
                            name,
                            (
                                name,
                                t.get("TableStatus", ""),
                                fmt_bytes(t.get("TableSizeBytes", 0)),
                                str(t.get("ItemCount", 0)),
                            ),
                            kind="table",
                            is_dir=True,
                            payload=t,
                        )
                    )
                except ClientError:
                    items.append(
                        Item(
                            self.key,
                            name,
                            name,
                            (name, "?", "?", "?"),
                            kind="table",
                            is_dir=True,
                            payload={"TableName": name},
                        )
                    )
            return Page(["Table", "Status", "Size", "Items"], items)

        table = path[0]
        resp = await self.exec.call("dynamodb", "scan", TableName=table, Limit=SCAN_LIMIT, ttl=15)
        items = []
        for row in resp.get("Items", []):
            label = await self._key_label(table, row)
            items.append(
                Item(
                    self.key,
                    label,
                    label,
                    (truncate(pretty(row, 300), 200),),
                    kind="item",
                    payload=row,
                )
            )
        return Page([f"Item (scan limit {SCAN_LIMIT})"], items)

    async def _key_label(self, table: str, row: dict) -> str:
        try:
            d = await self.exec.call("dynamodb", "describe_table", TableName=table, ttl=300)
            ks = d.get("Table", {}).get("KeySchema", [])
            parts = [
                f"{a['AttributeName']}={unquote_ddb(row[a['AttributeName']])}"
                for a in ks
                if a.get("AttributeName") in row
            ]
            if parts:
                return ", ".join(parts)
        except Exception:
            pass
        return truncate(pretty(row), 120)

    async def detail(self, item: Item) -> dict:
        return item.payload

    def describe(self, item: Item, detail: Any) -> str:
        if item.kind == "item":
            if isinstance(detail, dict):
                return "\n".join(f"[#94a3b8]{k}:[/] {unquote_ddb(v)}" for k, v in detail.items())
            return str(detail)
        d = detail if isinstance(detail, dict) else {}
        keys = ", ".join(
            f"{k.get('AttributeName')} ({k.get('KeyType')})" for k in d.get("KeySchema", [])
        )
        billing = (d.get("BillingModeSummary") or {}).get("BillingMode", "PROVISIONED")
        stream = (d.get("StreamSpecification") or {}).get("StreamEnabled")
        gsis = d.get("GlobalSecondaryIndexes", [])
        return "\n".join(
            [
                f"[#94a3b8]Table:[/] {d.get('TableName', item.label)}",
                f"[#94a3b8]Status:[/] {d.get('TableStatus', '') or '—'}",
                f"[#94a3b8]Items:[/] {d.get('ItemCount', 0)}",
                f"[#94a3b8]Size:[/] {fmt_bytes(d.get('TableSizeBytes', 0))}",
                f"[#94a3b8]Keys:[/] {keys or '—'}",
                f"[#94a3b8]Billing:[/] {billing}",
                f"[#94a3b8]Stream:[/] {'enabled' if stream else 'off'}",
                f"[#94a3b8]GSI:[/] {len(gsis)}",
                f"[#94a3b8]Created:[/] {fmt_time(d.get('CreationDateTime'))}",
            ]
        )

    def filter(self, items: list[Item], query: str) -> list[Item]:
        q = query.strip().lower()
        if not q:
            return items
        return [i for i in items if q in i.label.lower() or q in json.dumps(i.payload).lower()]

    async def links(self, item: Item) -> list[Link]:
        return []
