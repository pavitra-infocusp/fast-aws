"""API Gateway service: REST APIs, resources, stages, Lambda integration links."""

from __future__ import annotations

from botocore.exceptions import ClientError

from fast_aws.models import Item, Link, Page
from fast_aws.services.base import ResourceService

STAGES_DIR = "__stages"


def _lambda_from_uri(uri: str) -> str | None:
    if "lambda" not in uri or "functions/" not in uri:
        return None
    seg = uri.split("functions/")[-1].split("/")[0]
    return seg.split(":")[-1]


class ApiGatewayService(ResourceService):
    key = "apigateway"
    name = "API Gateway"
    icon = "🔁"

    async def list_page(self, path: list[str]) -> Page:
        if not path:
            resp = await self.exec.call("apigateway", "get_rest_apis", ttl=60)
            items = [
                Item(
                    self.key,
                    a.get("id", ""),
                    a.get("name", a.get("id", "")),
                    (a.get("createdDate", "") or "",),
                    kind="api",
                    is_dir=True,
                    payload=a,
                )
                for a in resp.get("items", [])
            ]
            return Page(["API name", "Created"], items)

        api = path[0]
        if len(path) == 1:
            resp = await self.exec.call("apigateway", "get_resources", restApiId=api, limit=500, ttl=60)
            items = [
                Item(self.key, STAGES_DIR, "── Stages ──", ("",), kind="dir", is_dir=True, payload={"api_id": api})
            ]
            for r in resp.get("items", []):
                methods = "/".join(sorted((r.get("resourceMethods") or {}).keys()))
                items.append(
                    Item(
                        self.key,
                        r.get("id", ""),
                        r.get("path", "/"),
                        (methods,),
                        kind="resource",
                        is_dir=True,
                        payload={"api_id": api, **r},
                    )
                )
            return Page(["Path", "Methods"], items)

        # Stages
        resp = await self.exec.call("apigateway", "get_stages", restApiId=api, ttl=60)
        items = [
            Item(
                self.key,
                s.get("stageName", ""),
                s.get("stageName", ""),
                (s.get("deploymentId", "") or "", s.get("lastUpdatedDate", "") or ""),
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
        return item.payload

    async def links(self, item: Item) -> list[Link]:
        out: list[Link] = []
        if item.kind != "resource":
            return out
        api = item.payload.get("api_id", "")
        try:
            res = await self.exec.call("apigateway", "get_resource", restApiId=api, resourceId=item.id, ttl=60)
        except ClientError:
            return out
        for method, conf in (res.get("resourceMethods") or {}).items():
            uri = (conf.get("methodIntegration") or {}).get("uri", "")
            fn = _lambda_from_uri(uri)
            if fn:
                out.append(Link("lambda", f"Lambda: {fn} ({method.upper()})", [], fn, kind="lambda"))
        return out

    async def run_action(self, action_id: str, item: Item) -> str:
        return await super().run_action(action_id, item)
