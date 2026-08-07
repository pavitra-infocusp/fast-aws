"""IAM service: users, roles, policies; role → policy links."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from fast_aws.fmt import (
    describe_fallback,
    detail_fallback,
    fmt_time,
    kv,
    kv_block,
    section,
    truncate,
)
from fast_aws.models import Item, Link, Page
from fast_aws.services.base import ResourceService

USERS_DIR = "__users"
ROLES_DIR = "__roles"
POLICIES_DIR = "__policies"


def _trust_summary(doc: dict) -> str:
    principals: set[str] = set()
    for stmt in doc.get("Statement", []) if isinstance(doc, dict) else []:
        for p in (stmt.get("Principal") or {}).values():
            ps = p if isinstance(p, list) else [p]
            for x in ps:
                if isinstance(x, str) and ":" in x:
                    principals.add(x.split(":")[1].lower())
                elif isinstance(x, str):
                    principals.add(x.lower())
    services = {
        p for p in principals if p.endswith(".amazonaws.com") or p.endswith(".amazonaws.com.cn")
    }
    return ", ".join(sorted(services)) or ", ".join(sorted(principals)) or "—"


def _fmt_principal(principal: Any) -> str:
    if isinstance(principal, dict):
        parts = []
        for k, v in principal.items():
            vs = v if isinstance(v, list) else [v]
            parts.append(f"{k}: {', '.join(str(x) for x in vs)}")
        return "; ".join(parts)
    if isinstance(principal, list):
        return ", ".join(str(x) for x in principal)
    return str(principal) if principal else "—"


def _fmt_action(action: Any) -> str:
    if isinstance(action, list):
        return ", ".join(str(a) for a in action)
    return str(action) if action else "—"


def _render_policy_statements(doc: Any) -> list[str]:
    if not isinstance(doc, dict):
        return [str(doc)] if doc else ["(empty)"]
    stmts = doc.get("Statement") or []
    if isinstance(stmts, dict):
        stmts = [stmts]
    lines: list[str] = []
    for i, stmt in enumerate(stmts, 1):
        if not isinstance(stmt, dict):
            lines.append(kv(f"Statement {i}", str(stmt)))
            continue
        lines.append(
            kv_block(
                [
                    (f"Statement {i}", stmt.get("Sid", "") or f"#{i}"),
                    ("Effect", stmt.get("Effect", "") or "—"),
                    ("Principal", _fmt_principal(stmt.get("Principal"))),
                    ("Action", _fmt_action(stmt.get("Action"))),
                    ("Resource", _fmt_action(stmt.get("Resource"))),
                    ("Condition", str(stmt.get("Condition")) if stmt.get("Condition") else None),
                ]
            )
        )
    return lines or ["(no statements)"]


class IAMService(ResourceService):
    key = "iam"
    name = "IAM"
    icon = "🪪"

    async def list_page(self, path: list[str], *, cursor: str | None = None) -> Page:
        if not path:
            return Page(
                ["Type"],
                [
                    Item(
                        self.key,
                        USERS_DIR,
                        "Users",
                        ("Users",),
                        kind="dir",
                        is_dir=True,
                        payload={},
                    ),
                    Item(
                        self.key,
                        ROLES_DIR,
                        "Roles",
                        ("Roles",),
                        kind="dir",
                        is_dir=True,
                        payload={},
                    ),
                    Item(
                        self.key,
                        POLICIES_DIR,
                        "Policies (customer)",
                        ("Policies (customer)",),
                        kind="dir",
                        is_dir=True,
                        payload={},
                    ),
                ],
            )

        kind = path[0]
        if kind == USERS_DIR:
            kwargs: dict[str, Any] = {"MaxItems": 100, "ttl": 60}
            if cursor:
                kwargs["Marker"] = cursor
            resp = await self.exec.call("iam", "list_users", **kwargs)
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
            next_cursor = resp.get("Marker") if resp.get("IsTruncated") else None
            return Page(["User", "Created"], items, cursor=next_cursor)

        if kind == ROLES_DIR:
            kwargs = {"MaxItems": 100, "ttl": 60}
            if cursor:
                kwargs["Marker"] = cursor
            resp = await self.exec.call("iam", "list_roles", **kwargs)
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
            next_cursor = resp.get("Marker") if resp.get("IsTruncated") else None
            return Page(["Role", "ARN"], items, cursor=next_cursor)

        kwargs = {"Scope": "Local", "MaxItems": 100, "ttl": 60}
        if cursor:
            kwargs["Marker"] = cursor
        resp = await self.exec.call("iam", "list_policies", **kwargs)
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
        next_cursor = resp.get("Marker") if resp.get("IsTruncated") else None
        return Page(["Policy", "Attachments"], items, cursor=next_cursor)

    async def detail(self, item: Item) -> dict:
        if item.kind == "role":
            doc = item.payload.get("AssumeRolePolicyDocument", {})
            return {
                **item.payload,
                "Trust policy": doc,
            }
        if item.kind == "policy":
            out = dict(item.payload)
            arn = item.payload.get("Arn")
            version = item.payload.get("DefaultVersionId")
            if arn and version:
                try:
                    resp = await self.exec.call(
                        "iam",
                        "get_policy_version",
                        PolicyArn=arn,
                        VersionId=version,
                        ttl=60,
                    )
                    out["Policy document"] = (resp.get("PolicyVersion") or {}).get("Document", {})
                except ClientError:
                    pass
            return out
        return item.payload

    def describe(self, item: Item, detail: Any) -> str:
        d = detail if isinstance(detail, dict) else {}
        if item.kind == "role":
            doc = d.get("Trust policy") or d.get("AssumeRolePolicyDocument") or {}
            trust = _trust_summary(doc if isinstance(doc, dict) else {})
            return kv_block(
                [
                    ("Role", d.get("RoleName", item.label)),
                    ("Path", d.get("Path", "/")),
                    ("Created", fmt_time(d.get("CreateDate"))),
                    (
                        "Max session",
                        f"{d['MaxSessionDuration']} s" if d.get("MaxSessionDuration") else None,
                    ),
                    ("Trusted", truncate(trust, 60)),
                ]
            )
        if item.kind == "user":
            groups = d.get("GroupList") or d.get("Groups") or []
            return kv_block(
                [
                    ("User", d.get("UserName", item.label)),
                    ("Created", fmt_time(d.get("CreateDate"))),
                    ("ARN", truncate(d.get("Arn", ""), 48)),
                    ("Groups", truncate(", ".join(groups) or "—", 50)),
                ]
            )
        if item.kind == "policy":
            return kv_block(
                [
                    ("Policy", d.get("PolicyName", item.label)),
                    ("Attachments", d.get("AttachmentCount", 0)),
                    ("Versions", d.get("DefaultVersionId", "") or "—"),
                    ("Created", fmt_time(d.get("CreateDate"))),
                    ("Updated", fmt_time(d.get("UpdateDate"))),
                ]
            )
        return describe_fallback(d)

    def detail_body(self, item: Item, detail: Any) -> str:
        d = detail if isinstance(detail, dict) else {}
        if item.kind == "role":
            doc = d.get("Trust policy") or d.get("AssumeRolePolicyDocument") or {}
            parts = [
                kv_block(
                    [
                        ("Role", d.get("RoleName", item.label)),
                        ("ARN", d.get("Arn", "") or "—"),
                        ("Path", d.get("Path", "/")),
                        ("Created", fmt_time(d.get("CreateDate"))),
                        (
                            "Max session",
                            f"{d['MaxSessionDuration']} s" if d.get("MaxSessionDuration") else "—",
                        ),
                        ("Description", d.get("Description", "") or "—"),
                        ("Trusted", _trust_summary(doc if isinstance(doc, dict) else {})),
                    ]
                ),
                section("Trust policy"),
                *_render_policy_statements(doc),
            ]
            return "\n".join(parts)
        if item.kind == "user":
            groups = d.get("GroupList") or d.get("Groups") or []
            return kv_block(
                [
                    ("User", d.get("UserName", item.label)),
                    ("ARN", d.get("Arn", "") or "—"),
                    ("Path", d.get("Path", "/") or "/"),
                    ("Created", fmt_time(d.get("CreateDate"))),
                    ("Password last used", fmt_time(d.get("PasswordLastUsed")) or "—"),
                    ("Groups", ", ".join(groups) or "—"),
                ]
            )
        if item.kind == "policy":
            parts = [
                kv_block(
                    [
                        ("Policy", d.get("PolicyName", item.label)),
                        ("ARN", d.get("Arn", "") or "—"),
                        ("Path", d.get("Path", "/") or "/"),
                        ("Attachments", d.get("AttachmentCount", 0)),
                        ("Default version", d.get("DefaultVersionId", "") or "—"),
                        ("Created", fmt_time(d.get("CreateDate"))),
                        ("Updated", fmt_time(d.get("UpdateDate"))),
                        ("Description", d.get("Description", "") or "—"),
                    ]
                )
            ]
            doc = d.get("Policy document")
            if doc:
                parts.append(section("Policy document"))
                parts.extend(_render_policy_statements(doc))
            return "\n".join(parts)
        return detail_fallback(d)

    async def links(self, item: Item) -> list[Link]:
        out: list[Link] = []
        if item.kind == "role":
            try:
                resp = await self.exec.call(
                    "iam",
                    "list_attached_role_policies",
                    RoleName=item.id,
                    MaxItems=100,
                    ttl=60,
                )
            except ClientError:
                resp = {}
            for p in resp.get("AttachedPolicies", []):
                out.append(
                    Link(
                        "iam",
                        f"Policy: {p.get('PolicyName', '')}",
                        [POLICIES_DIR],
                        p.get("PolicyName", ""),
                        kind="policy",
                    )
                )
        if item.kind == "user":
            try:
                resp = await self.exec.call(
                    "iam", "list_user_policies", UserName=item.id, MaxItems=100, ttl=60
                )
            except ClientError:
                resp = {}
            for p in resp.get("PolicyNames", []):
                out.append(Link("iam", f"Inline policy: {p}", [POLICIES_DIR], p, kind="policy"))
        return out
