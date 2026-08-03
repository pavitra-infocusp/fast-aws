"""S3 service: buckets and nested object-tree browsing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError

from fast_aws.fmt import (
    describe_fallback,
    detail_fallback,
    fmt_bytes,
    fmt_time,
    kv_block,
    section,
    theme_var,
    tree_label,
    tree_prefix,
    truncate,
)
from fast_aws.models import Action, Item, Link, Page
from fast_aws.services.base import ResourceService


def _folder_style() -> str:
    return f"bold {theme_var('text-primary', '#7dd3fc')}"


class _Node:
    __slots__ = ("name", "kids", "obj", "full_key")

    def __init__(self, name: str):
        self.name = name
        self.kids: dict[str, _Node] = {}
        self.obj: dict[str, Any] | None = None
        self.full_key = ""


def _insert_key(root: _Node, obj: dict[str, Any], *, base_prefix: str) -> None:
    key = obj.get("Key", "")
    if not key or key == base_prefix:
        return
    rel = key[len(base_prefix) :] if base_prefix and key.startswith(base_prefix) else key
    if not rel:
        return
    parts = [p for p in rel.split("/") if p]
    if not parts:
        return
    node = root
    for i, part in enumerate(parts):
        if part not in node.kids:
            node.kids[part] = _Node(part)
        node = node.kids[part]
        node.full_key = base_prefix + "/".join(parts[: i + 1])
        if i < len(parts) - 1:
            node.full_key += "/"
    if key.endswith("/"):
        node.full_key = key
        node.obj = obj
    else:
        node.full_key = key
        node.obj = obj


def _is_folder(node: _Node) -> bool:
    return bool(node.kids) or bool(node.obj and str(node.obj.get("Key", "")).endswith("/"))


def _object_tree_items(
    bucket: str, objects: list[dict[str, Any]], *, base_prefix: str = ""
) -> list[Item]:
    """Build a nested file/folder tree with indent guides from flat object keys."""
    root = _Node("")
    for obj in objects:
        _insert_key(root, obj, base_prefix=base_prefix)

    items: list[Item] = []

    def _sort_key(n: _Node) -> tuple[bool, str]:
        return (_is_folder(n) is False, n.name.lower())

    def emit(node: _Node, continues: list[bool], *, is_last: bool, bare: bool) -> None:
        folder = _is_folder(node)
        if bare:
            prefix = ""
            next_continues: list[bool] = []
        else:
            prefix = tree_prefix(continues, is_last)
            next_continues = continues + [not is_last]

        name = f"{node.name}/" if folder else node.name
        if folder:
            prefix_key = node.full_key if node.full_key.endswith("/") else f"{node.full_key}/"
            items.append(
                Item(
                    "s3",
                    prefix_key,
                    prefix_key,
                    (tree_label(prefix, name, style=_folder_style()), "", ""),
                    kind="prefix",
                    payload={"Bucket": bucket, "Prefix": prefix_key},
                )
            )
            kids = sorted(node.kids.values(), key=_sort_key)
            for i, child in enumerate(kids):
                emit(child, next_continues, is_last=i == len(kids) - 1, bare=False)
            return

        obj = node.obj or {}
        items.append(
            Item(
                "s3",
                node.full_key,
                node.full_key,
                (
                    tree_label(prefix, name),
                    fmt_bytes(obj.get("Size", 0)),
                    fmt_time(obj.get("LastModified")),
                ),
                kind="object",
                payload={"Bucket": bucket, **obj},
            )
        )

    top = sorted(root.kids.values(), key=_sort_key)
    for i, node in enumerate(top):
        emit(node, [], is_last=i == len(top) - 1, bare=len(top) == 1)
    return items


class S3Service(ResourceService):
    key = "s3"
    name = "S3"
    icon = "🪣"

    async def list_page(self, path: list[str]) -> Page:
        if not path:
            resp = await self.exec.call("s3", "list_buckets", ttl=60)
            items = [
                Item(
                    self.key,
                    b["Name"],
                    b["Name"],
                    (b["Name"], fmt_time(b.get("CreationDate"))),
                    kind="bucket",
                    is_dir=True,
                    payload={"Name": b["Name"], "CreationDate": b.get("CreationDate")},
                )
                for b in resp.get("Buckets", [])
            ]
            return Page(["Bucket", "Created"], items)

        bucket = path[0]
        prefix = path[1] if len(path) > 1 else ""
        resp = await self.exec.call(
            "s3", "list_objects_v2", Bucket=bucket, Prefix=prefix, MaxKeys=1000
        )
        return Page(
            ["Key", "Size", "Last modified"],
            _object_tree_items(bucket, resp.get("Contents", []), base_prefix=prefix),
        )

    async def detail(self, item: Item) -> dict:
        if item.kind == "object":
            try:
                meta = await self.exec.call(
                    "s3", "head_object", Bucket=item.payload["Bucket"], Key=item.label, ttl=30
                )
            except ClientError:
                return item.payload
            return {
                **item.payload,
                **{
                    k: v
                    for k, v in meta.items()
                    if k
                    in (
                        "ContentType",
                        "ContentLength",
                        "StorageClass",
                        "ETag",
                        "Metadata",
                        "LastModified",
                        "VersionId",
                    )
                },
            }
        if item.kind == "bucket":
            try:
                loc = await self.exec.call("s3", "get_bucket_location", Bucket=item.label, ttl=300)
                item.payload["Region"] = loc.get("LocationConstraint") or "us-east-1"
            except ClientError:
                pass
        return item.payload

    async def links(self, item: Item) -> list[Link]:
        return []

    def describe(self, item: Item, detail: Any) -> str:
        d = detail if isinstance(detail, dict) else {}
        if item.kind == "object":
            return kv_block(
                [
                    ("Bucket", d.get("Bucket", "")),
                    ("Key", truncate(item.label, 80)),
                    ("Size", fmt_bytes(d.get("ContentLength"))),
                    ("Modified", fmt_time(d.get("LastModified"))),
                    ("Type", d.get("ContentType", "") or "—"),
                    ("Class", d.get("StorageClass", "STANDARD")),
                    ("ETag", truncate(d.get("ETag", ""), 32)),
                ]
            )
        if item.kind == "bucket":
            return kv_block(
                [
                    ("Bucket", item.label),
                    ("Region", d.get("Region") or "(default)"),
                    ("Created", fmt_time(d.get("CreationDate"))),
                ]
            )
        if item.kind == "prefix":
            return kv_block(
                [
                    ("Bucket", d.get("Bucket", "")),
                    ("Prefix", d.get("Prefix", item.label)),
                ]
            )
        return describe_fallback(d)

    def detail_body(self, item: Item, detail: Any) -> str:
        d = detail if isinstance(detail, dict) else {}
        if item.kind == "object":
            parts = [
                kv_block(
                    [
                        ("Bucket", d.get("Bucket", "")),
                        ("Key", item.label),
                        ("Size", fmt_bytes(d.get("ContentLength") or d.get("Size"))),
                        ("Modified", fmt_time(d.get("LastModified"))),
                        ("Type", d.get("ContentType", "") or "—"),
                        ("Class", d.get("StorageClass", "STANDARD")),
                        ("ETag", d.get("ETag", "") or "—"),
                        ("Version", d.get("VersionId", "") or "—"),
                    ]
                )
            ]
            meta = d.get("Metadata") or {}
            if isinstance(meta, dict) and meta:
                parts.append(section("Metadata"))
                parts.append(kv_block([(k, v) for k, v in meta.items()]))
            return "\n".join(parts)
        if item.kind == "bucket":
            return kv_block(
                [
                    ("Bucket", item.label),
                    ("Region", d.get("Region") or "(default)"),
                    ("Created", fmt_time(d.get("CreationDate"))),
                ]
            )
        if item.kind == "prefix":
            return kv_block(
                [
                    ("Bucket", d.get("Bucket", "")),
                    ("Prefix", d.get("Prefix", item.label)),
                ]
            )
        return detail_fallback(d)

    def actions(self, item: Item) -> list[Action]:
        if item.kind == "object":
            return [Action("download", "Download object", False)]
        return []

    async def run_action(self, action_id: str, item: Item) -> str:
        if action_id == "download" and item.kind == "object":
            bucket, key = item.payload["Bucket"], item.label
            body = await self.exec.call("s3", "get_object", Bucket=bucket, Key=key, ttl=False)
            data = body["Body"].read()
            dest = Path("downloads") / bucket / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return f"Downloaded {fmt_bytes(len(data))} → {dest}"
        return await super().run_action(action_id, item)
