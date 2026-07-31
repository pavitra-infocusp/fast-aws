"""SSM Parameter Store service with masked values and reveal/copy."""

from __future__ import annotations

from fast_aws.fmt import copy_to_clipboard, mask
from fast_aws.models import Action, Item, Page
from fast_aws.services.base import ResourceService


class SSMService(ResourceService):
    key = "ssm"
    name = "SSM Parameter Store"
    icon = "🔧"

    async def list_page(self, path: list[str]) -> Page:
        resp = await self.exec.call("ssm", "describe_parameters", ttl=60)
        items = [
            Item(
                self.key,
                p.get("Name", ""),
                p.get("Name", ""),
                (
                    p.get("Name", "") or "",
                    p.get("Type", "") or "",
                    p.get("Tier", "") or "",
                    (p.get("LastModifiedDate") or "").isoformat() if hasattr(p.get("LastModifiedDate"), "isoformat") else "",
                ),
                kind="param",
                payload=p,
            )
            for p in resp.get("Parameters", [])
        ]
        return Page(["Name", "Type", "Tier", "Modified"], items)

    async def detail(self, item: Item) -> dict:
        try:
            p = await self.exec.call("ssm", "get_parameter", Name=item.id, WithDecryption=True, ttl=15)
            value = p.get("Parameter", {}).get("Value", "")
            return {**item.payload, "Value (masked)": mask(value)}
        except Exception:
            return item.payload

    def actions(self, item: Item) -> list[Action]:
        return [
            Action("reveal", "Reveal parameter value", False),
            Action("copy", "Copy value to clipboard", False),
        ]

    async def run_action(self, action_id: str, item: Item) -> str:
        if action_id in ("reveal", "copy"):
            p = await self.exec.call("ssm", "get_parameter", Name=item.id, WithDecryption=True, ttl=False, no_cache=True)
            value = p.get("Parameter", {}).get("Value", "")
            if action_id == "copy":
                if copy_to_clipboard(value):
                    return f"Copied {len(value)} chars to clipboard"
                return "Clipboard copy failed (no xclip/wl-copy/pbcopy found)"
            return value
        return await super().run_action(action_id, item)
