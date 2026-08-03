"""Service registry: picker entries → (service key, initial nav path)."""

from __future__ import annotations

from fast_aws.executor import Executor
from fast_aws.models import Location
from fast_aws.services import (  # noqa: F401
    apigateway,
    cloudwatch,
    cognito,
    dynamodb,
    iam,
    lambda_,
    s3,
    secrets,
    ssm,
)

_SERVICE_CLASSES = [
    s3.S3Service,
    lambda_.LambdaService,
    dynamodb.DynamoDBService,
    apigateway.ApiGatewayService,
    cognito.CognitoService,
    secrets.SecretsService,
    ssm.SSMService,
    iam.IAMService,
    cloudwatch.CloudWatchService,
]

# Service picker entries: (service key, initial nav path, display label)
SIDEBAR: list[tuple[str, list[str], str]] = [
    ("s3", [], "S3"),
    ("lambda", [], "Lambda"),
    ("dynamodb", ["tables"], "DynamoDB"),
    ("apigateway", [], "API Gateway"),
    ("cognito", [], "Cognito"),
    ("secretsmanager", [], "Secrets Manager"),
    ("ssm", [], "SSM Param Store"),
    ("iam", [], "IAM"),
    ("logs", [], "CloudWatch Logs"),
]


def service_root(key: str) -> Location:
    """Location of a service's top level, as listed in the picker."""
    service_key, path, label = next(entry for entry in SIDEBAR if entry[0] == key)
    return Location(service_key, path, label=label)


def build_services(exec: Executor) -> dict[str, object]:
    services: dict[str, object] = {}
    for cls in _SERVICE_CLASSES:
        services[cls.key] = cls(exec)
    return services
