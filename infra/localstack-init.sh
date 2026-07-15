#!/bin/bash
# =============================================================
# LocalStack bootstrap — runs when LocalStack is ready
# Creates S3 bucket and DynamoDB tables for local development
# =============================================================

echo "Initializing LocalStack resources..."

# --- S3 Bucket ---
awslocal s3 mb s3://code-rag-repos

# --- DynamoDB: repos table ---
awslocal dynamodb create-table \
    --table-name repos \
    --attribute-definitions \
        AttributeName=repo_id,AttributeType=S \
    --key-schema \
        AttributeName=repo_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST

# Enable TTL on repos table
awslocal dynamodb update-time-to-live \
    --table-name repos \
    --time-to-live-specification "Enabled=true, AttributeName=ttl"

# --- DynamoDB: sessions table ---
awslocal dynamodb create-table \
    --table-name sessions \
    --attribute-definitions \
        AttributeName=session_id,AttributeType=S \
    --key-schema \
        AttributeName=session_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST

# Enable TTL on sessions table
awslocal dynamodb update-time-to-live \
    --table-name sessions \
    --time-to-live-specification "Enabled=true, AttributeName=ttl"

# --- DynamoDB: rate_limits table ---
awslocal dynamodb create-table \
    --table-name rate_limits \
    --attribute-definitions \
        AttributeName=key,AttributeType=S \
    --key-schema \
        AttributeName=key,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST

# Enable TTL on rate_limits table
awslocal dynamodb update-time-to-live \
    --table-name rate_limits \
    --time-to-live-specification "Enabled=true, AttributeName=ttl"

echo "LocalStack initialization complete."
