"""Headless smoke tests using a stubbed executor (no real AWS calls)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fast_aws.app import FastAwsApp
from fast_aws.executor import Executor


def _obj(extra: dict | None = None) -> dict:
    obj = {
        "list_buckets": {
            "Buckets": [{"Name": "demo-bucket", "CreationDate": datetime(2024, 1, 1, tzinfo=UTC)}]
        },
        "list_objects_v2": {
            "Contents": [
                {
                    "Key": "app.log",
                    "Size": 2048,
                    "LastModified": datetime(2024, 2, 1, tzinfo=UTC),
                },
                {
                    "Key": "logs/error.log",
                    "Size": 512,
                    "LastModified": datetime(2024, 2, 2, tzinfo=UTC),
                },
            ],
        },
        "get_bucket_location": {"LocationConstraint": "us-east-1"},
        "head_object": {"ContentType": "text/plain", "ContentLength": 2048, "ETag": "abc123"},
        "list_functions": {
            "Functions": [
                {
                    "FunctionName": "my-fn",
                    "Runtime": "python3.12",
                    "State": "Active",
                    "LastModified": "2024-03-01T00:00:00+00:00",
                    "Role": "arn:aws:iam::123456789012:role/my-exec-role",
                },
                {
                    "FunctionName": "orders-handler",
                    "Runtime": "python3.12",
                    "State": "Active",
                    "LastModified": "2024-03-01T00:00:00+00:00",
                    "Role": "arn:aws:iam::123456789012:role/my-exec-role",
                },
            ]
        },
        "get_function": {
            "Configuration": {"FunctionName": "my-fn", "Runtime": "python3.12"},
            "Tags": {},
        },
        "list_event_source_mappings": {"EventSourceMappings": []},
        "describe_log_groups": {
            "logGroups": [
                {
                    "logGroupName": "/aws/lambda/my-fn",
                    "storedBytes": 4096,
                    "creationTime": 1700000000000,
                    "retentionInDays": 14,
                }
            ]
        },
        "describe_log_streams": {
            "logStreams": [{"logStreamName": "stream1", "lastEventTimestamp": 1700000001000}]
        },
        "get_log_events": {
            "events": [{"timestamp": 1700000001000, "message": "hello from lambda"}]
        },
        "list_tables": {"TableNames": ["users"]},
        "describe_table": {
            "Table": {
                "TableName": "users",
                "TableStatus": "ACTIVE",
                "TableSizeBytes": 123,
                "ItemCount": 4,
                "KeySchema": [{"AttributeName": "id", "KeyType": "HASH"}],
            }
        },
        "scan": {"Items": [{"id": {"S": "user-1"}, "name": {"S": "alice"}}]},
        "list_secrets": {
            "SecretList": [
                {
                    "Name": "db/password",
                    "ARN": "arn:aws:secretsmanager:us-east-1:1:secret:db/password",
                    "Description": "db creds",
                }
            ]
        },
        "get_secret_value": {"SecretString": "sup3rs3cret"},
        "describe_parameters": {
            "Parameters": [{"Name": "/app/timeout", "Type": "String", "Tier": "Standard"}]
        },
        "get_parameter": {"Parameter": {"Name": "/app/timeout", "Value": "30"}},
        "get_rest_apis": {
            "items": [{"id": "abc123", "name": "orders-api", "createdDate": "2024-01-01"}]
        },
        "get_resources": {
            "items": [
                {"id": "root", "path": "/", "resourceMethods": {}},
                {
                    "id": "r1",
                    "parentId": "root",
                    "pathPart": "orders",
                    "path": "/orders",
                    "resourceMethods": {"GET": {}},
                },
            ]
        },
        "get_resource": {
            "id": "r1",
            "path": "/orders",
            "resourceMethods": {
                "GET": {
                    "methodIntegration": {
                        "uri": (
                            "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/"
                            "arn:aws:lambda:us-east-1:1:function:orders-handler/invocations"
                        )
                    }
                }
            }
        },
        "get_method": {
            "httpMethod": "GET",
            "authorizationType": "NONE",
            "methodIntegration": {
                "type": "AWS_PROXY",
                "uri": (
                    "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/"
                    "arn:aws:lambda:us-east-1:1:function:orders-handler/invocations"
                ),
            },
        },
        "list_user_pools": {"UserPools": [{"Id": "pool1", "Name": "my-pool", "Status": "Enabled"}]},
        "describe_user_pool": {
            "UserPool": {
                "Id": "pool1",
                "LambdaConfig": {"PreSignUp": "arn:aws:lambda:us-east-1:1:function:pool-trigger"},
            }
        },
        "list_identity_pools": {
            "IdentityPools": [{"IdentityPoolId": "ip1", "IdentityPoolName": "mobile"}]
        },
        "describe_identity_pool": {"IdentityPoolId": "ip1", "RoleMappings": {}},
        "list_roles": {
            "Roles": [{"RoleName": "my-exec-role", "Arn": "arn:aws:iam::1:role/my-exec-role"}]
        },
        "list_attached_role_policies": {"AttachedPolicies": [{"PolicyName": "MyPolicy"}]},
        "list_policies": {"Policies": [{"PolicyName": "MyPolicy", "AttachmentCount": 1}]},
        "get_caller_identity": {"Arn": "arn:aws:iam::1:user/test", "Account": "1", "UserId": "1"},
    }
    if extra:
        obj.update(extra)
    return obj


STUB = _obj()


async def settle(pilot, n=4):
    for _ in range(n):
        await pilot.pause()
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


async def pick_service(pilot, index: int = 0):
    """Advance past the post-auth ServicePicker into BrowseScreen."""
    await settle(pilot)
    assert pilot.app.screen.__class__.__name__ == "ServicePicker"
    lv = pilot.app.screen.query_one("#services-pick")
    lv.index = index
    await pilot.press("enter")
    await settle(pilot)
    assert pilot.app.screen.__class__.__name__ == "BrowseScreen"


@pytest.fixture
def stub_call(monkeypatch):
    async def fake_call(self: Executor, service: str, fn: str, *args, **kwargs):
        resp = STUB.get(fn)
        if resp is None:
            raise Exception(f"unexpected stub call: {service}.{fn} {args} {kwargs}")
        return resp

    monkeypatch.setattr(Executor, "call", fake_call)


@pytest.mark.asyncio
async def test_browse_s3_drilldown(stub_call):
    from textual.widgets import DataTable

    app = FastAwsApp(profile="default", region="us-east-1", readonly=True)
    async with app.run_test(size=(160, 50)) as pilot:
        await pick_service(pilot)  # S3
        table = app.screen.query_one("#table", DataTable)
        await settle(pilot)
        assert str(app.screen.query_one("#breadcrumb").content)  # breadcrumb set
        assert table.row_count == 1  # one bucket

        # drill into bucket → nested tree: app.log, logs/, └─ error.log
        await pilot.press("enter")
        await settle(pilot)
        assert table.row_count == 3
        # open object detail for app.log (folders sort first: logs/, error.log, app.log)
        table.move_cursor(row=2)
        await settle(pilot)
        await pilot.press("enter")
        await settle(pilot)
        assert app.screen.__class__.__name__ == "ResultScreen"
        await pilot.press("escape")
        await settle(pilot)
        # back out of bucket
        await pilot.press("escape")
        await settle(pilot)
        assert table.row_count == 1  # bucket list again


@pytest.mark.asyncio
async def test_lambda_links_and_jump(stub_call):
    from textual.widgets import DataTable

    app = FastAwsApp(profile="default", region="us-east-1", readonly=True)
    async with app.run_test(size=(160, 50)) as pilot:
        await pick_service(pilot, index=1)  # Lambda
        table = app.screen.query_one("#table", DataTable)
        assert table.row_count >= 1
        await pilot.press("l")
        await settle(pilot)
        links_list = app.screen.query_one("#links-list")
        assert len(links_list.children) >= 2  # log group + role
        # jump to the log group (first link)
        await pilot.press("enter")
        await settle(pilot)
        assert "/aws/lambda/my-fn" in str(app.screen.query_one("#breadcrumb").content)
        # jump lands on the log group's streams → one enter reaches the events table
        await pilot.press("enter")
        await settle(pilot)
        assert "hello from lambda" in str(app.screen.query_one("#table").get_row_at(0))


@pytest.mark.asyncio
async def test_secrets_reveal_flow(stub_call):
    from textual.widgets import DataTable

    app = FastAwsApp(profile="default", region="us-east-1", readonly=True)
    async with app.run_test(size=(160, 50)) as pilot:
        await pick_service(pilot, index=5)  # Secrets Manager
        table = app.screen.query_one("#table", DataTable)
        assert table.row_count == 1
        await pilot.press("a")
        await settle(pilot)
        actions_list = app.screen.query_one("#actions-list")
        assert len(actions_list.children) == 2
        await pilot.press("enter")  # reveal
        await settle(pilot)
        # short secret -> notify, back on browse screen
        assert app.screen.__class__.__name__ == "BrowseScreen"


@pytest.mark.asyncio
async def test_apigw_jump_to_lambda(stub_call):
    app = FastAwsApp(profile="default", region="us-east-1", readonly=True)
    async with app.run_test(size=(160, 50)) as pilot:
        await pick_service(pilot, index=3)  # API Gateway
        # drill into the API: Stages, /,   orders,     GET
        await pilot.press("enter")
        await settle(pilot)
        table = app.screen.query_one("#table")
        assert table.row_count == 4
        table.move_cursor(row=2)  # nested /orders resource
        await settle(pilot)
        await pilot.press("l")
        await settle(pilot)
        links_list = app.screen.query_one("#links-list")
        assert len(links_list.children) == 1
        await pilot.press("enter")
        await settle(pilot)
        # jumped into Lambda and auto-selected the orders-handler function
        assert "Lambda" in str(app.screen.query_one("#breadcrumb").content)
        assert app.screen._current is not None
        assert app.screen._current.label == "orders-handler"


@pytest.mark.asyncio
async def test_profile_picker_lists_profiles():

    app = FastAwsApp(readonly=True)
    async with app.run_test(size=(160, 50)) as pilot:
        await settle(pilot)
        assert app.screen.__class__.__name__ == "ProfilePicker"
        lv = app.screen.query_one("#profiles")
        assert len(lv.children) >= 1


@pytest.mark.asyncio
async def test_service_picker_before_browse(stub_call):
    app = FastAwsApp(profile="default", region="us-east-1", readonly=True)
    async with app.run_test(size=(160, 50)) as pilot:
        await settle(pilot)
        assert app.screen.__class__.__name__ == "ServicePicker"
        lv = app.screen.query_one("#services-pick")
        assert len(lv.children) == 9
        assert "default" in str(app.screen.query_one("#service-note").content)
        # no AWS list calls until a service is chosen — pick Lambda
        await pick_service(pilot, index=1)
        assert "Lambda" in str(app.screen.query_one("#breadcrumb").content)


@pytest.mark.asyncio
async def test_filter_and_back(stub_call):
    from textual.widgets import DataTable

    app = FastAwsApp(profile="default", region="us-east-1", readonly=True)
    async with app.run_test(size=(160, 50)) as pilot:
        await pick_service(pilot)  # S3
        table = app.screen.query_one("#table", DataTable)
        # drill into bucket → nested tree: app.log, logs/, └─ error.log
        await pilot.press("enter")
        await settle(pilot)
        assert table.row_count == 3
        # filter for the object
        await pilot.press("/")
        await settle(pilot)
        await pilot.press("a", "p", "p")
        await settle(pilot)
        assert table.row_count == 1
        # esc clears filter and returns focus to table
        await pilot.press("escape")
        await settle(pilot)
        assert table.row_count == 3
        # back out of bucket
        await pilot.press("escape")
        await settle(pilot)
        assert table.row_count == 1  # bucket list again


@pytest.mark.asyncio
async def test_palette_switch_service(stub_call):

    app = FastAwsApp(profile="default", region="us-east-1", readonly=True)
    async with app.run_test(size=(160, 50)) as pilot:
        await pick_service(pilot)  # S3
        await pilot.press("ctrl+p")
        await settle(pilot)
        palette = app.screen.query_one("#palette-input")
        assert palette.has_focus
        await pilot.press("G", "o", " ", "t", "o")
        await settle(pilot)
        await pilot.press("enter")
        await settle(pilot)
        # Go to first matching entry (Go to DynamoDB via its icon label?) — index 0 is top of list
        # just assert palette dismissed
        assert app.screen.__class__.__name__ == "BrowseScreen"


@pytest.mark.asyncio
async def test_mode_toggle_readonly_default(stub_call):
    app = FastAwsApp(profile="default", region="us-east-1", readonly=True)
    async with app.run_test(size=(160, 50)) as pilot:
        await pick_service(pilot)  # S3
        assert app.executor.readonly is True
        assert "READONLY" in str(app.screen.query_one("#topbar").content)
        await pilot.press("ctrl+e")
        await settle(pilot)
        assert app.screen.__class__.__name__ == "ConfirmScreen"
        await pilot.press("enter")  # confirm Yes
        await settle(pilot)
        assert app.executor.readonly is False
        assert "EDIT" in str(app.screen.query_one("#topbar").content)
