"""Lambda service: functions, config, log group + role links, invoke."""

from __future__ import annotations

from botocore.exceptions import ClientError

from fast_aws.executor import LoginRequired
from fast_aws.fmt import truncate
from fast_aws.models import Action, Item, Link, Page
from fast_aws.services.base import ResourceService


class LambdaService(ResourceService):
    key = "lambda"
    name = "Lambda"
    icon = "λ"

    async def list_page(self, path: list[str]) -> Page:
        resp = await self.exec.call("lambda", "list_functions", ttl=30)
        items = [
            Item(
                self.key,
                f.get("FunctionName", ""),
                f.get("FunctionName", ""),
                (
                    f.get("FunctionName", "") or "",
                    f.get("Runtime", "") or "",
                    f.get("State", "") or "",
                    f.get("LastModified", "") or "",
                ),
                kind="function",
                payload=f,
            )
            for f in resp.get("Functions", [])
        ]
        return Page(["Function", "Runtime", "State", "Modified"], items)

    async def detail(self, item: Item) -> dict:
        try:
            return await self.exec.call("lambda", "get_function", FunctionName=item.label, ttl=30)
        except ClientError:
            return item.payload

    async def links(self, item: Item) -> list[Link]:
        out: list[Link] = []
        if item.kind != "function":
            return out
        fn = item.label
        out.append(Link("logs", f"Log group /aws/lambda/{fn}", [f"/aws/lambda/{fn}"], "", kind="log_group"))

        role = item.payload.get("Role", "")
        if role:
            role_name = role.rstrip("/").split("/")[-1]
            out.append(Link("iam", f"Execution role {role_name}", ["roles"], role_name, kind="role"))

        try:
            mappings = await self.exec.call("lambda", "list_event_source_mappings", FunctionName=fn, ttl=60)
        except (ClientError, LoginRequired):
            mappings = {}
        for m in mappings.get("EventSourceMappings", []):
            arn = m.get("EventSourceArn", "")
            if ":table/" in arn:
                tname = arn.split(":table/")[-1]
                out.append(Link("dynamodb", f"DynamoDB stream {tname}", ["tables"], tname, kind="dynamodb"))
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
                "lambda", "invoke", FunctionName=item.label, Payload=b"{}", LogType="None", ttl=False
            )
            body = ""
            try:
                body = result["Payload"].read().decode()
            except Exception:
                pass
            status = result.get("StatusCode", "?")
            return f"Invoke → HTTP {status}\n\n{truncate(body, 1500)}"
        return await super().run_action(action_id, item)
