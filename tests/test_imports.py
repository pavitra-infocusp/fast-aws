"""Ensure every service module imports cleanly (catches SyntaxError early)."""

from __future__ import annotations

import importlib

import pytest

SERVICE_MODULES = [
    "fast_aws.services.apigateway",
    "fast_aws.services.cloudwatch",
    "fast_aws.services.cognito",
    "fast_aws.services.dynamodb",
    "fast_aws.services.iam",
    "fast_aws.services.lambda_",
    "fast_aws.services.s3",
    "fast_aws.services.secrets",
    "fast_aws.services.ssm",
]


@pytest.mark.parametrize("module", SERVICE_MODULES)
def test_service_module_imports(module: str) -> None:
    importlib.import_module(module)


def test_build_services_registry() -> None:
    from fast_aws.executor import Executor
    from fast_aws.services import SIDEBAR, build_services

    services = build_services(Executor(profile=None, region="us-east-1"))
    assert set(services) == {key for key, _, _ in SIDEBAR}
