"""DynamoDB service: tables and bounded scans."""

from __future__ import annotations

import json

from botocore.exceptions import ClientError

from fast_aws.fmt import fmt_bytes, pretty, unquote_ddb
from fast_aws.models import Item, Page
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
                        Item(self.key, name, name, ("?", "?", "?"), kind="table", is_dir=True, payload={"TableName": name})
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

    def filter(self, items: list[Item], query: str) -> list[Item]:
        q = query.strip().lower()
        if not q:
            return items
        return [i for i in items if q in i.label.lower() or q in json.dumps(i.payload).lower()]

    async def links(self, item: Item) -> list[Item]:
        return []
