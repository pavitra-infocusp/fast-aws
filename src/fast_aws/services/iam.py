"""IAM service: users, roles, policies; role → policy links."""

from __future__ import annotations

from botocore.exceptions import ClientError

from fast_aws.fmt import fmt_time
from fast_aws.models import Item, Link, Page
from fast_aws.services.base import ResourceService

USERS_DIR = "__users"
ROLES_DIR = "__roles"
POLICIES_DIR = "__policies"


class IAMService(ResourceService):
    key = "iam"
    name = "IAM"
    icon = "🪪"

    async def list_page(self, path: list[str]) -> Page:
        if not path:
            return Page(
                ["Type"],
                [
                    Item(self.key, USERS_DIR, "Users", (), kind="dir", is_dir=True, payload={}),
                    Item(self.key, ROLES_DIR, "Roles", (), kind="dir", is_dir=True, payload={}),
                    Item(self.key, POLICIES_DIR, "Policies (customer)", (), kind="dir", is_dir=True, payload={}),
                ],
            )

        kind = path[0]
        if kind == USERS_DIR:
            resp = await self.exec.call("iam", "list_users", ttl=60)
            items = [
                Item(
                    self.key,
                    u.get("UserName", ""),
                    u.get("UserName", ""),
                    (fmt_time(u.get("CreateDate")),),
                    kind="user",
                    payload=u,
                )
                for u in resp.get("Users", [])
            ]
            return Page(["User", "Created"], items)

        if kind == ROLES_DIR:
            resp = await self.exec.call("iam", "list_roles", ttl=60)
            items = [
                Item(
                    self.key,
                    r.get("RoleName", ""),
                    r.get("RoleName", ""),
                    (r.get("Arn", "") or "",),
                    kind="role",
                    payload=r,
                )
                for r in resp.get("Roles", [])
            ]
            return Page(["Role", "ARN"], items)

        resp = await self.exec.call("iam", "list_policies", Scope="Local", ttl=60)
        items = [
            Item(
                self.key,
                p.get("PolicyName", ""),
                p.get("PolicyName", ""),
                (str(p.get("AttachmentCount", 0)),),
                kind="policy",
                payload=p,
            )
            for p in resp.get("Policies", [])
        ]
        return Page(["Policy", "Attachments"], items)

    async def detail(self, item: Item) -> dict:
        if item.kind == "role":
            doc = item.payload.get("AssumeRolePolicyDocument", {})
            return {
                **item.payload,
                "Trust policy": doc,
            }
        return item.payload

    async def links(self, item: Item) -> list[Link]:
        out: list[Link] = []
        if item.kind == "role":
            try:
                resp = await self.exec.call("iam", "list_attached_role_policies", RoleName=item.id, ttl=60)
            except ClientError:
                resp = {}
            for p in resp.get("AttachedPolicies", []):
                out.append(Link("iam", f"Policy: {p.get('PolicyName', '')}", [POLICIES_DIR], p.get("PolicyName", ""), kind="policy"))
        if item.kind == "user":
            try:
                resp = await self.exec.call("iam", "list_user_policies", UserName=item.id, ttl=60)
            except ClientError:
                resp = {}
            for p in resp.get("PolicyNames", []):
                out.append(Link("iam", f"Inline policy: {p}", [POLICIES_DIR], p, kind="policy"))
        return out
