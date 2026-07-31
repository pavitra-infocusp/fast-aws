"""IAM service: users, roles, policies; role → policy links."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from fast_aws.fmt import describe_fallback, fmt_time, truncate
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
                    Item(self.key, USERS_DIR, "Users", ("Users",), kind="dir", is_dir=True, payload={}),
                    Item(self.key, ROLES_DIR, "Roles", ("Roles",), kind="dir", is_dir=True, payload={}),
                    Item(self.key, POLICIES_DIR, "Policies (customer)", ("Policies (customer)",), kind="dir", is_dir=True, payload={}),
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
                    (u.get("UserName", ""), fmt_time(u.get("CreateDate"))),
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
                    (r.get("RoleName", "") or "", truncate(r.get("Arn", ""), 48)),
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
                (p.get("PolicyName", ""), str(p.get("AttachmentCount", 0))),
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

    def describe(self, item: Item, detail: Any) -> str:
        d = detail if isinstance(detail, dict) else {}
        if item.kind == "role":
            doc = d.get("Trust policy") or d.get("AssumeRolePolicyDocument") or {}
            principals = set()
            services = set()
            for stmt in doc.get("Statement", []):
                for p in (stmt.get("Principal") or {}).values():
                    ps = p if isinstance(p, list) else [p]
                    for x in ps:
                        if isinstance(x, str) and ":" in x:
                            principals.add(x.split(":")[1].lower())
                        elif isinstance(x, str):
                            principals.add(x.lower())
            services |= {p for p in principals if p.endswith(".amazonaws.com") or p.endswith(".amazonaws.com.cn")}
            trust = ", ".join(sorted(services)) or ", ".join(sorted(principals)) or "—"
            return "\n".join(
                p
                for p in [
                    f"[#94a3b8]Role:[/] {d.get('RoleName', item.label)}",
                    f"[#94a3b8]Path:[/] {d.get('Path', '/')}",
                    f"[#94a3b8]Created:[/] {fmt_time(d.get('CreateDate'))}",
                    f"[#94a3b8]Max session:[/] {d.get('MaxSessionDuration', '')} s" if d.get("MaxSessionDuration") else None,
                    f"[#94a3b8]Trusted:[/] {truncate(trust, 60)}",
                ]
                if p
            )
        if item.kind == "user":
            groups = (d.get("GroupList") or d.get("Groups") or [])
            return "\n".join(
                [
                    f"[#94a3b8]User:[/] {d.get('UserName', item.label)}",
                    f"[#94a3b8]Created:[/] {fmt_time(d.get('CreateDate'))}",
                    f"[#94a3b8]ARN:[/] {truncate(d.get('Arn', ''), 48)}",
                    f"[#94a3b8]Groups:[/] {truncate(', '.join(groups) or '—', 50)}",
                ]
            )
        if item.kind == "policy":
            return "\n".join(
                [
                    f"[#94a3b8]Policy:[/] {d.get('PolicyName', item.label)}",
                    f"[#94a3b8]Attachments:[/] {d.get('AttachmentCount', 0)}",
                    f"[#94a3b8]Versions:[/] {d.get('DefaultVersionId', '') or '—'}",
                    f"[#94a3b8]Created:[/] {fmt_time(d.get('CreateDate'))}",
                    f"[#94a3b8]Updated:[/] {fmt_time(d.get('UpdateDate'))}",
                ]
            )
        return describe_fallback(d)

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
