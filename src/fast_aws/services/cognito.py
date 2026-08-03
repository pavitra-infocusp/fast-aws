"""Cognito service: user pools and identity pools with Lambda trigger links."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from fast_aws.fmt import describe_fallback, detail_fallback, fmt_time, kv_block, section, truncate
from fast_aws.models import Action, Item, Link, Page
from fast_aws.services.base import ResourceService

POOLS_DIR = "__pools"
IDENTITY_DIR = "__identity"


class CognitoService(ResourceService):
    key = "cognito"
    name = "Cognito"
    icon = "👤"

    async def list_page(self, path: list[str]) -> Page:
        if not path:
            return Page(
                ["Section"],
                [
                    Item(
                        self.key,
                        POOLS_DIR,
                        "User Pools",
                        ("User Pools",),
                        kind="dir",
                        is_dir=True,
                        payload={},
                    ),
                    Item(
                        self.key,
                        IDENTITY_DIR,
                        "Identity Pools",
                        ("Identity Pools",),
                        kind="dir",
                        is_dir=True,
                        payload={},
                    ),
                ],
            )
        if path[0] == POOLS_DIR:
            resp = await self.exec.call("cognito-idp", "list_user_pools", MaxResults=60, ttl=60)
            items = [
                Item(
                    self.key,
                    p.get("Id", ""),
                    p.get("Name", ""),
                    (p.get("Name", ""), p.get("Id", ""), p.get("Status", "") or ""),
                    kind="user_pool",
                    is_dir=True,
                    payload=p,
                )
                for p in resp.get("UserPools", [])
            ]
            return Page(["User pool", "ID", "Status"], items)
        resp = await self.exec.call(
            "cognito-identity", "list_identity_pools", MaxResults=60, ttl=60
        )
        items = [
            Item(
                self.key,
                p.get("IdentityPoolId", ""),
                p.get("IdentityPoolName", ""),
                (p.get("IdentityPoolName", ""), p.get("IdentityPoolId", "") or ""),
                kind="identity_pool",
                is_dir=True,
                payload=p,
            )
            for p in resp.get("IdentityPools", [])
        ]
        return Page(["Identity pool", "ID"], items)

    async def detail(self, item: Item) -> dict:
        if item.kind == "user_pool":
            try:
                d = await self.exec.call(
                    "cognito-idp", "describe_user_pool", UserPoolId=item.id, ttl=60
                )
                return d.get("UserPool", d)
            except ClientError:
                return item.payload
        if item.kind == "identity_pool":
            try:
                d = await self.exec.call(
                    "cognito-identity", "describe_identity_pool", IdentityPoolId=item.id, ttl=60
                )
                return d
            except ClientError:
                return item.payload
        return item.payload

    def describe(self, item: Item, detail: Any) -> str:
        d = detail if isinstance(detail, dict) else {}
        if item.kind == "user_pool":
            triggers = d.get("LambdaConfig") or {}
            trig = ", ".join(f"{k}: {v.split(':')[-1]}" for k, v in triggers.items()) or "none"
            return kv_block(
                [
                    ("Name", d.get("Name", item.label)),
                    ("ID", d.get("Id", item.id)),
                    ("Status", d.get("Status", "") or "—"),
                    ("Created", fmt_time(d.get("CreationDate"))),
                    ("Lambda triggers", truncate(trig, 60)),
                ]
            )
        if item.kind == "identity_pool":
            return kv_block(
                [
                    ("Name", d.get("IdentityPoolName", item.label)),
                    ("ID", d.get("IdentityPoolId", item.id)),
                ]
            )
        return describe_fallback(d)

    def detail_body(self, item: Item, detail: Any) -> str:
        d = detail if isinstance(detail, dict) else {}
        if item.kind == "user_pool":
            parts = [
                kv_block(
                    [
                        ("Name", d.get("Name", item.label)),
                        ("ID", d.get("Id", item.id)),
                        ("ARN", d.get("Arn", "") or "—"),
                        ("Status", d.get("Status", "") or "—"),
                        ("Created", fmt_time(d.get("CreationDate"))),
                        ("Last modified", fmt_time(d.get("LastModifiedDate"))),
                        ("MFA", d.get("MfaConfiguration", "") or "—"),
                        ("Domain", d.get("Domain", "") or "—"),
                        ("Estimated users", d.get("EstimatedNumberOfUsers", "") or "—"),
                    ]
                )
            ]
            triggers = d.get("LambdaConfig") or {}
            if triggers:
                parts.append(section("Lambda triggers"))
                parts.append(
                    kv_block(
                        [
                            (k, v.split(":")[-1] if isinstance(v, str) else v)
                            for k, v in triggers.items()
                        ]
                    )
                )
            return "\n".join(parts)
        if item.kind == "identity_pool":
            parts = [
                kv_block(
                    [
                        ("Name", d.get("IdentityPoolName", item.label)),
                        ("ID", d.get("IdentityPoolId", item.id)),
                        (
                            "Unauth access",
                            "yes" if d.get("AllowUnauthenticatedIdentities") else "no",
                        ),
                        ("Classic flow", "yes" if d.get("AllowClassicFlow") else "no"),
                        ("Auth role", (d.get("Roles") or {}).get("authenticated", "") or "—"),
                        ("Unauth role", (d.get("Roles") or {}).get("unauthenticated", "") or "—"),
                    ]
                )
            ]
            mappings = d.get("RoleMappings") or {}
            if mappings:
                parts.append(section("Role mappings"))
                for key, m in mappings.items():
                    if not isinstance(m, dict):
                        continue
                    parts.append(
                        kv_block(
                            [
                                ("Provider", key),
                                ("Type", m.get("Type", "") or "—"),
                                ("Role ARN", m.get("RoleArn", "") or "—"),
                                ("Ambiguous role", m.get("AmbiguousRoleResolution", "") or None),
                            ]
                        )
                    )
            return "\n".join(parts)
        return detail_fallback(d)

    async def links(self, item: Item) -> list[Link]:
        out: list[Link] = []
        if item.kind == "user_pool":
            try:
                d = await self.exec.call(
                    "cognito-idp", "describe_user_pool", UserPoolId=item.id, ttl=60
                )
                cfg = d.get("UserPool", {}).get("LambdaConfig", {}) or {}
            except ClientError:
                cfg = {}
            for trigger, arn in cfg.items():
                if arn:
                    fn = arn.split(":")[-1]
                    out.append(Link("lambda", f"Trigger {trigger}: {fn}", [], fn, kind="lambda"))
        if item.kind == "identity_pool":
            try:
                d = await self.exec.call(
                    "cognito-identity", "describe_identity_pool", IdentityPoolId=item.id, ttl=60
                )
                rm = d.get("RoleMappings") or {}
            except ClientError:
                rm = {}
            for key, m in rm.items():
                role_arn = m.get("RoleArn")
                if role_arn:
                    role_name = role_arn.split("/")[-1]
                    out.append(
                        Link("iam", f"Role: {role_name} ({key})", ["roles"], role_name, kind="role")
                    )
        return out

    def actions(self, item: Item) -> list[Action]:
        if item.kind == "user_pool":
            return [Action("clients", "List user pool clients", False)]
        return []

    async def run_action(self, action_id: str, item: Item) -> str:
        if action_id == "clients" and item.kind == "user_pool":
            resp = await self.exec.call(
                "cognito-idp", "list_user_pool_clients", UserPoolId=item.id, MaxResults=60, ttl=60
            )
            rows = [
                f"{c.get('ClientName', '')}  ({c.get('ClientId', '')})"
                for c in resp.get("UserPoolClients", [])
            ]
            return "User pool clients:\n" + ("\n".join(rows) if rows else "(none)")
        return await super().run_action(action_id, item)
