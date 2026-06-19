"""
Initialize DynamoDB tables for local development.

Run after docker-compose up:
    python -m src.init_dynamo
"""

import boto3
from botocore.exceptions import ClientError


def create_tables(endpoint_url: str = "http://localhost:8001"):
    """Create all required DynamoDB tables."""
    ddb = boto3.client(
        "dynamodb",
        endpoint_url=endpoint_url,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )

    tables = [
        {
            "TableName": "repos",
            "KeySchema": [{"AttributeName": "repo_id", "KeyType": "HASH"}],
            "AttributeDefinitions": [
                {"AttributeName": "repo_id", "AttributeType": "S"}
            ],
            "BillingMode": "PAY_PER_REQUEST",
        },
        {
            "TableName": "sessions",
            "KeySchema": [{"AttributeName": "session_id", "KeyType": "HASH"}],
            "AttributeDefinitions": [
                {"AttributeName": "session_id", "AttributeType": "S"}
            ],
            "BillingMode": "PAY_PER_REQUEST",
        },
        {
            "TableName": "rate_limits",
            "KeySchema": [{"AttributeName": "key", "KeyType": "HASH"}],
            "AttributeDefinitions": [
                {"AttributeName": "key", "AttributeType": "S"}
            ],
            "BillingMode": "PAY_PER_REQUEST",
        },
    ]

    for table_def in tables:
        name = table_def["TableName"]
        try:
            ddb.create_table(**table_def)
            print(f"  [+] Created table: {name}")
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceInUseException":
                print(f"  [=] Table already exists: {name}")
            else:
                raise

    # Enable TTL on each table
    ttl_attrs = {
        "repos": "ttl",
        "sessions": "ttl",
        "rate_limits": "ttl",
    }
    for table_name, attr_name in ttl_attrs.items():
        try:
            ddb.update_time_to_live(
                TableName=table_name,
                TimeToLiveSpecification={
                    "Enabled": True,
                    "AttributeName": attr_name,
                },
            )
            print(f"  [+] TTL enabled on {table_name}.{attr_name}")
        except ClientError:
            pass  # DynamoDB Local may not support TTL fully

    print("\nDynamoDB tables ready.")


if __name__ == "__main__":
    print("Initializing DynamoDB tables...")
    create_tables()
