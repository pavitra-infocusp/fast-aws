"""Validate list_page request kwargs against botocore's own input constraints.

A page size above an API's documented maximum fails at runtime with a
ValidationException, which is invisible until someone opens that service.
"""

from __future__ import annotations

import botocore.session
import pytest

from fast_aws.executor import Executor
from fast_aws.services import build_services
from fast_aws.services.apigateway import STAGES_DIR
from fast_aws.services.cognito import (
    CLIENTS_DIR,
    GROUPS_DIR,
    IDENTITY_DIR,
    POOLS_DIR,
    PROVIDERS_DIR,
)
from fast_aws.services.cognito import USERS_DIR as COGNITO_USERS_DIR
from fast_aws.services.iam import POLICIES_DIR, ROLES_DIR, USERS_DIR

# (service key, nav path) pairs covering every paginated listing.
LIST_LOCATIONS = [
    ("s3", []),
    ("s3", ["demo-bucket"]),
    ("lambda", []),
    ("dynamodb", ["tables"]),
    ("apigateway", []),
    ("apigateway", ["api1"]),
    ("apigateway", ["api1", STAGES_DIR]),
    ("cognito", [POOLS_DIR]),
    ("cognito", [IDENTITY_DIR]),
    ("cognito", [POOLS_DIR, "pool1", COGNITO_USERS_DIR]),
    ("cognito", [POOLS_DIR, "pool1", GROUPS_DIR]),
    ("cognito", [POOLS_DIR, "pool1", CLIENTS_DIR]),
    ("cognito", [POOLS_DIR, "pool1", PROVIDERS_DIR]),
    ("secretsmanager", []),
    ("ssm", []),
    ("iam", [USERS_DIR]),
    ("iam", [ROLES_DIR]),
    ("iam", [POLICIES_DIR]),
    ("logs", []),
    ("logs", ["/aws/lambda/fn"]),
]

_BOTO_SESSION = botocore.session.get_session()


def _op_name(fn: str) -> str:
    return "".join(part.capitalize() for part in fn.split("_"))


def _violations(service: str, fn: str, kwargs: dict) -> list[str]:
    """Return constraint violations for numeric members of this request."""
    try:
        model = _BOTO_SESSION.get_service_model(service)
        members = model.operation_model(_op_name(fn)).input_shape.members
    except Exception:
        return []
    out = []
    for name, value in kwargs.items():
        shape = members.get(name)
        if shape is None or not isinstance(value, int) or isinstance(value, bool):
            continue
        low, high = shape.metadata.get("min"), shape.metadata.get("max")
        if low is not None and value < low:
            out.append(f"{service}.{fn}: {name}={value} below min {low}")
        if high is not None and value > high:
            out.append(f"{service}.{fn}: {name}={value} above max {high}")
    return out


@pytest.mark.parametrize("service_key,path", LIST_LOCATIONS, ids=lambda v: str(v))
@pytest.mark.asyncio
async def test_list_page_kwargs_within_api_limits(service_key, path, monkeypatch):
    seen: list[tuple[str, str, dict]] = []

    async def record(self, service: str, fn: str, *args, **kwargs):
        kwargs.pop("ttl", None)
        kwargs.pop("no_cache", None)
        seen.append((service, fn, kwargs))
        return {}

    monkeypatch.setattr(Executor, "call", record)

    services = build_services(Executor(profile=None, region="us-east-1"))
    await services[service_key].list_page(list(path))

    problems = [p for svc, fn, kw in seen for p in _violations(svc, fn, kw)]
    assert not problems, "; ".join(problems)


# Locations that must forward a cursor, and the request kwarg carrying it.
CURSOR_KWARGS = [
    ("s3", [], "ContinuationToken"),
    ("s3", ["demo-bucket"], "ContinuationToken"),
    ("lambda", [], "Marker"),
    ("dynamodb", ["tables"], "ExclusiveStartTableName"),
    ("apigateway", [], "position"),
    ("apigateway", ["api1"], "position"),
    ("cognito", [POOLS_DIR], "NextToken"),
    ("cognito", [IDENTITY_DIR], "NextToken"),
    ("cognito", [POOLS_DIR, "pool1", COGNITO_USERS_DIR], "PaginationToken"),
    ("cognito", [POOLS_DIR, "pool1", GROUPS_DIR], "NextToken"),
    ("cognito", [POOLS_DIR, "pool1", CLIENTS_DIR], "NextToken"),
    ("cognito", [POOLS_DIR, "pool1", PROVIDERS_DIR], "NextToken"),
    ("secretsmanager", [], "NextToken"),
    ("ssm", [], "NextToken"),
    ("iam", [USERS_DIR], "Marker"),
    ("iam", [ROLES_DIR], "Marker"),
    ("iam", [POLICIES_DIR], "Marker"),
    ("logs", [], "nextToken"),
    ("logs", ["/aws/lambda/fn"], "nextToken"),
]


@pytest.mark.parametrize("service_key,path,token_kwarg", CURSOR_KWARGS, ids=lambda v: str(v))
@pytest.mark.asyncio
async def test_list_page_forwards_cursor(service_key, path, token_kwarg, monkeypatch):
    """A cursor must reach AWS under that API's token kwarg, not be dropped."""
    seen: list[tuple[str, str, dict]] = []

    async def record(self, service: str, fn: str, *args, **kwargs):
        kwargs.pop("ttl", None)
        kwargs.pop("no_cache", None)
        seen.append((service, fn, kwargs))
        return {}

    monkeypatch.setattr(Executor, "call", record)

    services = build_services(Executor(profile=None, region="us-east-1"))
    await services[service_key].list_page(list(path), cursor="TOKEN-123")

    assert any(kw.get(token_kwarg) == "TOKEN-123" for _, _, kw in seen), (
        f"{service_key} {path} did not forward the cursor as {token_kwarg}; saw {seen}"
    )
