"""API Gateway service: REST APIs, resources, stages, Lambda integration links."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from fast_aws.fmt import (
    describe_fallback,
    detail_fallback,
    fmt_http_method,
    fmt_time,
    http_method_markup,
    kv,
    kv_block,
    section,
    tree_label,
    tree_prefix,
)
from fast_aws.models import Item, Link, Page
from fast_aws.services.base import ResourceService

STAGES_DIR = "__stages"
_DIR_LABELS = {STAGES_DIR: "Stages"}


def _lambda_from_uri(uri: str) -> str | None:
    if "lambda" not in uri or "functions/" not in uri:
        return None
    seg = uri.split("functions/")[-1].split("/")[0]
    # arn:...:function:name or arn:...:function:name:version|alias
    if ":function:" in seg:
        return seg.split(":function:", 1)[1].split(":", 1)[0]
    return seg.split(":")[-1]


def _resource_tree_items(api: str, resources: list[dict[str, Any]]) -> list[Item]:
    """Flatten the API resource tree into indented path / method rows."""
    by_id = {r.get("id", ""): r for r in resources if r.get("id")}
    children: dict[str | None, list[dict[str, Any]]] = {}
    for r in resources:
        parent = r.get("parentId")
        if parent not in by_id:
            parent = None
        children.setdefault(parent, []).append(r)

    for kids in children.values():
        kids.sort(key=lambda r: (r.get("pathPart") or r.get("path") or "").lower())

    items: list[Item] = []

    def emit(r: dict[str, Any], continues: list[bool], *, is_last: bool, bare: bool) -> None:
        rid = r.get("id", "")
        path = r.get("path", "/")
        name = r.get("pathPart") or path or "/"
        methods = sorted((r.get("resourceMethods") or {}).keys())
        sub = children.get(rid, [])

        if bare:
            prefix = ""
            next_continues: list[bool] = []
        else:
            prefix = tree_prefix(continues, is_last)
            next_continues = continues + [not is_last]

        items.append(
            Item(
                "apigateway",
                rid,
                path,
                (tree_label(prefix, name), "path"),
                kind="resource",
                payload={"api_id": api, **r},
            )
        )

        for mi, method in enumerate(methods):
            last_under = mi == len(methods) - 1 and not sub
            items.append(
                Item(
                    "apigateway",
                    f"{rid}:{method}",
                    f"{method.upper()} {path}",
                    (
                        fmt_http_method(
                            method, prefix=tree_prefix(next_continues, last_under)
                        ),
                        "method",
                    ),
                    kind="method",
                    payload={
                        "api_id": api,
                        "resource_id": rid,
                        "http_method": method,
                        "path": path,
                    },
                )
            )

        for si, child in enumerate(sub):
            emit(
                child,
                next_continues,
                is_last=si == len(sub) - 1,
                bare=False,
            )

    roots = children.get(None, [])
    for i, r in enumerate(roots):
        emit(
            r,
            [],
            is_last=i == len(roots) - 1,
            bare=len(roots) == 1,
        )
    return items


class ApiGatewayService(ResourceService):
    key = "apigateway"
    name = "API Gateway"
    icon = "🔁"

    def path_label(self, segment: str) -> str:
        return _DIR_LABELS.get(segment, segment)

    async def list_page(self, path: list[str]) -> Page:
        if not path:
            resp = await self.exec.call("apigateway", "get_rest_apis", ttl=60)
            items = [
                Item(
                    self.key,
                    a.get("id", ""),
                    a.get("name", a.get("id", "")),
                    (a.get("name", a.get("id", "")), fmt_time(a.get("createdDate"))),
                    kind="api",
                    is_dir=True,
                    payload=a,
                )
                for a in resp.get("items", [])
            ]
            return Page(["API name", "Created"], items)

        api = path[0]
        if len(path) == 1:
            resp = await self.exec.call(
                "apigateway", "get_resources", restApiId=api, limit=500, ttl=60
            )
            items = [
                Item(
                    self.key,
                    STAGES_DIR,
                    "── Stages ──",
                    ("── Stages ──", ""),
                    kind="dir",
                    is_dir=True,
                    payload={"api_id": api},
                )
            ]
            items.extend(_resource_tree_items(api, resp.get("items", [])))
            return Page(["Resource", "Type"], items)

        if path[1] != STAGES_DIR:
            return Page(["Value"], [])

        resp = await self.exec.call("apigateway", "get_stages", restApiId=api, ttl=60)
        items = [
            Item(
                self.key,
                s.get("stageName", ""),
                s.get("stageName", ""),
                (
                    s.get("stageName", ""),
                    s.get("deploymentId", "") or "",
                    fmt_time(s.get("lastUpdatedDate")),
                ),
                kind="stage",
                payload=s,
            )
            for s in resp.get("item", [])
        ]
        return Page(["Stage", "Deployment", "Updated"], items)

    async def detail(self, item: Item) -> dict:
        if item.kind == "resource":
            try:
                return await self.exec.call(
                    "apigateway",
                    "get_resource",
                    restApiId=item.payload.get("api_id", ""),
                    resourceId=item.id,
                    ttl=60,
                )
            except ClientError:
                return item.payload
        if item.kind == "method":
            try:
                return await self.exec.call(
                    "apigateway",
                    "get_method",
                    restApiId=item.payload.get("api_id", ""),
                    resourceId=item.payload.get("resource_id", ""),
                    httpMethod=item.payload.get("http_method", ""),
                    ttl=60,
                )
            except ClientError:
                return item.payload
        return item.payload

    def describe(self, item: Item, detail: Any) -> str:
        d = detail if isinstance(detail, dict) else {}
        if item.kind == "api":
            return kv_block(
                [
                    ("Name", d.get("name", item.label)),
                    ("ID", d.get("id", "") or "—"),
                    ("Created", fmt_time(d.get("createdDate")) or "—"),
                ]
            )
        if item.kind == "resource":
            methods = d.get("resourceMethods") or {}
            method_labels = (
                " ".join(http_method_markup(m) for m in sorted(methods)) or "—"
            )
            return "\n".join(
                [
                    kv("Path", d.get("path", "/")),
                    f"[#94a3b8]Methods:[/] {method_labels}",
                    kv("ID", d.get("id", item.id)),
                ]
            )
        if item.kind == "method":
            integ = d.get("methodIntegration") or {}
            method = item.payload.get("http_method", "") or item.label
            return "\n".join(
                [
                    f"[#94a3b8]Method:[/] {http_method_markup(method)}",
                    kv("Path", item.payload.get("path", "/") or "—"),
                    kv("Integration", integ.get("type", "") or "—"),
                    kv("URI", integ.get("uri", "") or "—"),
                ]
            )
        if item.kind == "stage":
            return kv_block(
                [
                    ("Stage", d.get("stageName", item.label)),
                    ("Deployment", d.get("deploymentId", "") or "—"),
                    ("Updated", fmt_time(d.get("lastUpdatedDate")) or "—"),
                ]
            )
        return describe_fallback(d)

    def detail_body(self, item: Item, detail: Any) -> str:
        d = detail if isinstance(detail, dict) else {}
        if item.kind == "api":
            return kv_block(
                [
                    ("Name", d.get("name", item.label)),
                    ("ID", d.get("id", "") or "—"),
                    ("Description", d.get("description", "") or "—"),
                    ("Created", fmt_time(d.get("createdDate")) or "—"),
                    ("Version", d.get("version", "") or "—"),
                    (
                        "Endpoint",
                        ", ".join(d.get("endpointConfiguration", {}).get("types", []) or []) or "—",
                    ),
                    ("API key source", d.get("apiKeySource", "") or "—"),
                ]
            )
        if item.kind == "resource":
            methods = d.get("resourceMethods") or {}
            method_labels = (
                " ".join(http_method_markup(m) for m in sorted(methods)) or "—"
            )
            parts = [
                "\n".join(
                    [
                        kv("Path", d.get("path", item.payload.get("path", "/"))),
                        kv("ID", d.get("id", item.id)),
                        kv("Parent", d.get("parentId", "") or "—"),
                        f"[#94a3b8]Methods:[/] {method_labels}",
                    ]
                )
            ]
            if methods:
                parts.append(section("Integrations"))
                for method, conf in sorted(methods.items()):
                    if not isinstance(conf, dict):
                        parts.append(
                            f"{http_method_markup(method)}  [#94a3b8](no config)[/]"
                        )
                        continue
                    integ = conf.get("methodIntegration") or {}
                    lines = [
                        f"{http_method_markup(method)}  "
                        f"{integ.get('type', '') or '—'}",
                        kv("URI", integ.get("uri", "") or "—"),
                    ]
                    if integ.get("httpMethod"):
                        lines.append(kv("HTTP method", integ.get("httpMethod")))
                    parts.append("\n".join(lines))
            return "\n".join(parts)
        if item.kind == "method":
            integ = d.get("methodIntegration") or {}
            method = item.payload.get("http_method") or d.get("httpMethod") or ""
            return "\n".join(
                [
                    f"[#94a3b8]Method:[/] {http_method_markup(method)}",
                    kv("Path", item.payload.get("path", "/") or "—"),
                    kv("Resource ID", item.payload.get("resource_id", "") or "—"),
                    kv("Authorization", d.get("authorizationType", "") or "—"),
                    kv("API key required", "yes" if d.get("apiKeyRequired") else "no"),
                    kv("Integration", integ.get("type", "") or "—"),
                    kv("Integration HTTP", integ.get("httpMethod", "") or "—"),
                    kv("URI", integ.get("uri", "") or "—"),
                ]
            )
        if item.kind == "stage":
            vars_ = d.get("variables") or {}
            parts = [
                kv_block(
                    [
                        ("Stage", d.get("stageName", item.label)),
                        ("Deployment", d.get("deploymentId", "") or "—"),
                        ("Description", d.get("description", "") or "—"),
                        ("Created", fmt_time(d.get("createdDate")) or "—"),
                        ("Updated", fmt_time(d.get("lastUpdatedDate")) or "—"),
                        ("Tracing", "on" if (d.get("tracingEnabled")) else "off"),
                        ("Cache cluster", d.get("cacheClusterStatus", "") or "—"),
                    ]
                )
            ]
            if vars_:
                parts.append(section("Stage variables"))
                parts.append(kv_block([(k, v) for k, v in sorted(vars_.items())]))
            return "\n".join(parts)
        return detail_fallback(d)

    async def links(self, item: Item) -> list[Link]:
        out: list[Link] = []
        if item.kind == "method":
            api = item.payload.get("api_id", "")
            try:
                conf = await self.exec.call(
                    "apigateway",
                    "get_method",
                    restApiId=api,
                    resourceId=item.payload.get("resource_id", ""),
                    httpMethod=item.payload.get("http_method", ""),
                    ttl=60,
                )
            except ClientError:
                return out
            uri = (conf.get("methodIntegration") or {}).get("uri", "")
            fn = _lambda_from_uri(uri)
            if fn:
                method = item.payload.get("http_method", "").upper()
                out.append(Link("lambda", f"Lambda: {fn} ({method})", [], fn, kind="lambda"))
            return out
        if item.kind != "resource":
            return out
        api = item.payload.get("api_id", "")
        try:
            res = await self.exec.call(
                "apigateway", "get_resource", restApiId=api, resourceId=item.id, ttl=60
            )
        except ClientError:
            return out
        for method, conf in (res.get("resourceMethods") or {}).items():
            uri = (conf.get("methodIntegration") or {}).get("uri", "")
            fn = _lambda_from_uri(uri)
            if fn:
                out.append(
                    Link("lambda", f"Lambda: {fn} ({method.upper()})", [], fn, kind="lambda")
                )
        return out

    async def run_action(self, action_id: str, item: Item) -> str:
        return await super().run_action(action_id, item)
