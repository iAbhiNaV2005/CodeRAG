"""
DynamoDB client singleton.

Provides a shared boto3 DynamoDB resource for all dynamo modules.
Uses LocalStack endpoint for local development.
"""

import boto3
from src.config import get_settings

_dynamodb_resource = None


def get_dynamodb_resource():
    """Get or create the DynamoDB resource (singleton)."""
    global _dynamodb_resource
    if _dynamodb_resource is None:
        settings = get_settings()
        kwargs = {"region_name": settings.aws_region}
        if settings.aws_endpoint_url:
            kwargs["endpoint_url"] = settings.aws_endpoint_url
            kwargs["aws_access_key_id"] = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        _dynamodb_resource = boto3.resource("dynamodb", **kwargs)
    return _dynamodb_resource


def get_table(table_name: str):
    """Get a DynamoDB table by name."""
    return get_dynamodb_resource().Table(table_name)
