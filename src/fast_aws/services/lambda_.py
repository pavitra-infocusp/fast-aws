"""Lambda service: functions, config, log group + role links, invoke."""

from __future__ import annotations

import contextlib
from typing import Any

from botocore.exceptions import ClientError

from fast_aws.executor import LoginRequired
from fast_aws.fmt import fmt_bytes, fmt_time, kv_block, section, truncate
from fast_aws.models import Action, Item, Link, Page
from fast_aws.services.base import ResourceService


class LambdaService(ResourceService):
    key = "lambda"
    name = "Lambda"
    icon = "λ"

    async def list_page(self, path: list[str], *, cursor: str | None = None) -> Page:
        kwargs: dict[str, Any] = {"MaxItems": 50, "ttl": 30}
        if cursor:
            kwargs["Marker"] = cursor
        resp = await self.exec.call("lambda", "list_functions", **kwargs)
        items = [
            Item(
                self.key,
                f.get("FunctionName", ""),
                f.get("FunctionName", ""),
                (
                    f.get("FunctionName", "") or "",
                    f.get("Runtime", "") or "",
                    f.get("State", "") or "",
                    fmt_time(f.get("LastModified")),
                ),
                kind="function",
                payload=f,
            )
            for f in resp.get("Functions", [])
        ]
        return Page(
            ["Function", "Runtime", "State", "Modified"],
            items,
            cursor=resp.get("NextMarker"),
        )

    async def detail(self, item: Item) -> dict:
        try:
            return await self.exec.call("lambda", "get_function", FunctionName=item.label, ttl=30)
        except ClientError:
            return item.payload

    def describe(self, item: Item, detail: Any) -> str:
        cfg = detail.get("Configuration", detail) if isinstance(detail, dict) else {}
        if not isinstance(cfg, dict):
            cfg = {}
        arch = cfg.get("Architectures") or [""]
        return kv_block(
            [
                ("Name", cfg.get("FunctionName", item.label)),
                ("Runtime", cfg.get("Runtime", "") or "—"),
                ("State", cfg.get("State", "") or "—"),
                ("Last modified", fmt_time(cfg.get("LastModified")) or "—"),
                ("Handler", cfg.get("Handler", "") or "—"),
                ("Memory", f"{cfg['MemorySize']} MB" if cfg.get("MemorySize") else None),
                ("Timeout", f"{cfg['Timeout']} s" if cfg.get("Timeout") else None),
                ("Arch", arch[0] if arch else "—"),
                ("Role", str(cfg.get("Role", "")).split("/")[-1] or "—"),
                ("Description", cfg.get("Description", "") or "—"),
            ]
        )

    def detail_body(self, item: Item, detail: Any) -> str:
        d = detail if isinstance(detail, dict) else {}
        cfg = d.get("Configuration", d) if isinstance(d, dict) else {}
        if not isinstance(cfg, dict):
            cfg = {}
        arch = cfg.get("Architectures") or []
        parts = [
            kv_block(
                [
                    ("Name", cfg.get("FunctionName", item.label)),
                    ("ARN", cfg.get("FunctionArn", "") or "—"),
                    ("Runtime", cfg.get("Runtime", "") or "—"),
                    ("State", cfg.get("State", "") or "—"),
                    ("Last modified", fmt_time(cfg.get("LastModified")) or "—"),
                    ("Handler", cfg.get("Handler", "") or "—"),
                    ("Memory", f"{cfg['MemorySize']} MB" if cfg.get("MemorySize") else "—"),
                    ("Timeout", f"{cfg['Timeout']} s" if cfg.get("Timeout") else "—"),
                    (
                        "Ephemeral storage",
                        (
                            f"{(cfg.get('EphemeralStorage') or {}).get('Size', '')} MB"
                            if cfg.get("EphemeralStorage")
                            else None
                        ),
                    ),
                    ("Arch", ", ".join(arch) if arch else "—"),
                    ("Role", cfg.get("Role", "") or "—"),
                    ("Description", cfg.get("Description", "") or "—"),
                    ("Package type", cfg.get("PackageType", "") or "—"),
                    ("Layers", len(cfg.get("Layers") or [])),
                ]
            )
        ]
        env = ((cfg.get("Environment") or {}).get("Variables")) or {}
        if env:
            parts.append(section("Environment"))
            parts.append(kv_block([(k, v) for k, v in sorted(env.items())]))
        code = d.get("Code") if isinstance(d, dict) else None
        if isinstance(code, dict) and code:
            parts.append(section("Code"))
            loc = code.get("Location")
            parts.append(
                kv_block(
                    [
                        ("Size", fmt_bytes(code.get("CodeSize") or cfg.get("CodeSize"))),
                        ("SHA256", code.get("CodeSha256") or cfg.get("CodeSha256") or "—"),
                        ("Repository type", code.get("RepositoryType", "") or "—"),
                        ("Location", truncate(loc, 80) if loc else None),
                    ]
                )
            )
        elif cfg.get("CodeSize") or cfg.get("CodeSha256"):
            parts.append(section("Code"))
            parts.append(
                kv_block(
                    [
                        ("Size", fmt_bytes(cfg.get("CodeSize"))),
                        ("SHA256", cfg.get("CodeSha256", "") or "—"),
                    ]
                )
            )
        tags = d.get("Tags") if isinstance(d, dict) else None
        if isinstance(tags, dict) and tags:
            parts.append(section("Tags"))
            parts.append(kv_block([(k, v) for k, v in sorted(tags.items())]))
        return "\n".join(parts)

    async def links(self, item: Item) -> list[Link]:
        out: list[Link] = []
        if item.kind != "function":
            return out
        fn = item.label
        out.append(
            Link("logs", f"Log group /aws/lambda/{fn}", [f"/aws/lambda/{fn}"], "", kind="log_group")
        )

        role = item.payload.get("Role", "")
        if role:
            role_name = role.rstrip("/").split("/")[-1]
            out.append(
                Link("iam", f"Execution role {role_name}", ["roles"], role_name, kind="role")
            )

        try:
            mappings = await self.exec.call(
                "lambda", "list_event_source_mappings", FunctionName=fn, ttl=60
            )
        except (ClientError, LoginRequired):
            mappings = {}
        for m in mappings.get("EventSourceMappings", []):
            arn = m.get("EventSourceArn", "")
            if ":table/" in arn:
                tname = arn.split(":table/")[-1]
                out.append(
                    Link("dynamodb", f"DynamoDB stream {tname}", ["tables"], tname, kind="dynamodb")
                )
            elif ":queue/" in arn:
                qname = arn.split(":queue/")[-1]
                out.append(Link("sqs", f"SQS queue {qname}", [], qname, kind="sqs"))
        return out

    def actions(self, item: Item) -> list[Action]:
        return [Action("invoke", "Invoke function", mutates=True)]

    async def run_action(self, action_id: str, item: Item) -> str:
        if action_id == "invoke":
            self.exec.ensure_can_mutate()
            result = await self.exec.call(
                "lambda",
                "invoke",
                FunctionName=item.label,
                Payload=b"{}",
                LogType="None",
                ttl=False,
            )
            body = ""
            with contextlib.suppress(Exception):
                body = result["Payload"].read().decode()
            status = result.get("StatusCode", "?")
            return f"Invoke → HTTP {status}\n\n{truncate(body, 1500)}"
        return await super().run_action(action_id, item)
