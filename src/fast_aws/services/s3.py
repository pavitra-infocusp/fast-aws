"""S3 service: buckets and prefix-based object browsing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError

from fast_aws.fmt import describe_fallback, fmt_bytes, fmt_time, truncate
from fast_aws.models import Action, Item, Link, Page
from fast_aws.services.base import ResourceService


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
            "s3", "list_objects_v2", Bucket=bucket, Prefix=prefix, Delimiter="/", MaxKeys=1000
        )
        items: list[Item] = []
        for p in resp.get("CommonPrefixes", []):
            pre = p["Prefix"]
            items.append(
                Item(
                    self.key,
                    pre,
                    pre,
                    (pre, "", ""),
                    kind="prefix",
                    is_dir=True,
                    payload={"Bucket": bucket, "Prefix": pre},
                )
            )
        for o in resp.get("Contents", []):
            key = o["Key"]
            items.append(
                Item(
                    self.key,
                    key,
                    key,
                    (key, fmt_bytes(o.get("Size", 0)), fmt_time(o.get("LastModified"))),
                    kind="object",
                    is_dir=False,
                    payload={"Bucket": bucket, **o},
                )
            )
        items.sort(key=lambda i: (not i.is_dir, i.label.lower()))
        return Page(["Key", "Size", "Last modified"], items)

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
            return "\n".join(
                [
                    f"[#94a3b8]Bucket:[/] {d.get('Bucket', '')}",
                    f"[#94a3b8]Key:[/] {truncate(item.label, 80)}",
                    f"[#94a3b8]Size:[/] {fmt_bytes(d.get('ContentLength'))}",
                    f"[#94a3b8]Modified:[/] {fmt_time(d.get('LastModified'))}",
                    f"[#94a3b8]Type:[/] {d.get('ContentType', '') or '—'}",
                    f"[#94a3b8]Class:[/] {d.get('StorageClass', 'STANDARD')}",
                    f"[#94a3b8]ETag:[/] {truncate(d.get('ETag', ''), 32)}",
                ]
            )
        if item.kind == "bucket":
            return "\n".join(
                [
                    f"[#94a3b8]Bucket:[/] {item.label}",
                    f"[#94a3b8]Region:[/] {d.get('Region') or '(default)'}",
                    f"[#94a3b8]Created:[/] {fmt_time(d.get('CreationDate'))}",
                ]
            )
        return describe_fallback(d)

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
