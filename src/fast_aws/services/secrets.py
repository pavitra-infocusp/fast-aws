"""Secrets Manager service with reveal / copy actions."""

from __future__ import annotations

from typing import Any

from fast_aws.fmt import copy_to_clipboard, fmt_time, kv_block, truncate
from fast_aws.models import Action, Item, Page
from fast_aws.services.base import ResourceService


class SecretsService(ResourceService):
    key = "secretsmanager"
    name = "Secrets Manager"
    icon = "🔐"

    async def list_page(self, path: list[str]) -> Page:
        resp = await self.exec.call("secretsmanager", "list_secrets", ttl=60)
        items = [
            Item(
                self.key,
                s.get("ARN", ""),
                s.get("Name", ""),
                (
                    s.get("Name", "") or "",
                    (s.get("Description") or "")[:80],
                    "on" if s.get("RotationEnabled") else "",
                ),
                kind="secret",
                payload=s,
            )
            for s in resp.get("SecretList", [])
        ]
        return Page(["Name", "Description", "Rotation"], items)

    async def detail(self, item: Item) -> dict:
        return item.payload

    def describe(self, item: Item, detail: Any) -> str:
        d = detail if isinstance(detail, dict) else {}
        return kv_block(
            [
                ("Name", d.get("Name", item.label)),
                ("ARN", truncate(d.get("ARN", ""), 60)),
                ("Description", d.get("Description", "") or "—"),
                ("Rotation", "on" if d.get("RotationEnabled") else "off"),
                ("Last changed", fmt_time(d.get("LastChangedDate"))),
                ("Created", fmt_time(d.get("CreatedDate"))),
            ]
        )

    def detail_body(self, item: Item, detail: Any) -> str:
        d = detail if isinstance(detail, dict) else {}
        return kv_block(
            [
                ("Name", d.get("Name", item.label)),
                ("ARN", d.get("ARN", "") or "—"),
                ("Description", d.get("Description", "") or "—"),
                ("Rotation", "on" if d.get("RotationEnabled") else "off"),
                ("Rotation lambda", d.get("RotationLambdaARN", "") or "—"),
                ("Last rotated", fmt_time(d.get("LastRotatedDate"))),
                ("Last changed", fmt_time(d.get("LastChangedDate"))),
                ("Last accessed", fmt_time(d.get("LastAccessedDate"))),
                ("Created", fmt_time(d.get("CreatedDate"))),
                ("Deleted", fmt_time(d.get("DeletedDate")) or None),
                ("Owning service", d.get("OwningService", "") or "—"),
                ("Primary region", d.get("PrimaryRegion", "") or "—"),
            ]
        )

    def actions(self, item: Item) -> list[Action]:
        return [
            Action("reveal", "Reveal secret value", False),
            Action("copy", "Copy value to clipboard", False),
        ]

    async def run_action(self, action_id: str, item: Item) -> str:
        if action_id in ("reveal", "copy"):
            v = await self.exec.call(
                "secretsmanager", "get_secret_value", SecretId=item.id, ttl=False, no_cache=True
            )
            value = v.get("SecretString")
            if value is None:
                value = "<binary secret — use download>"
            if action_id == "copy":
                if copy_to_clipboard(value):
                    return f"Copied {len(value)} chars to clipboard"
                return "Clipboard copy failed (no xclip/wl-copy/pbcopy found)"
            return value
        return await super().run_action(action_id, item)
