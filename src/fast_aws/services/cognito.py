"""Cognito service: user pools and identity pools with Lambda trigger links."""

from __future__ import annotations

from botocore.exceptions import ClientError

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
                    Item(self.key, POOLS_DIR, "User Pools", ("User Pools",), kind="dir", is_dir=True, payload={}),
                    Item(self.key, IDENTITY_DIR, "Identity Pools", ("Identity Pools",), kind="dir", is_dir=True, payload={}),
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
        resp = await self.exec.call("cognito-identity", "list_identity_pools", MaxResults=60, ttl=60)
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
                d = await self.exec.call("cognito-idp", "describe_user_pool", UserPoolId=item.id, ttl=60)
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

    async def links(self, item: Item) -> list[Link]:
        out: list[Link] = []
        if item.kind == "user_pool":
            try:
                d = await self.exec.call("cognito-idp", "describe_user_pool", UserPoolId=item.id, ttl=60)
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
                    out.append(Link("iam", f"Role: {role_name} ({key})", ["roles"], role_name, kind="role"))
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
                f"{c.get('ClientName','')}  ({c.get('ClientId','')})"
                for c in resp.get("UserPoolClients", [])
            ]
            return "User pool clients:\n" + ("\n".join(rows) if rows else "(none)")
        return await super().run_action(action_id, item)
