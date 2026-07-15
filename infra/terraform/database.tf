# DynamoDB tables and S3 bucket used by the backend.
# PostgreSQL/pgvector now runs on the EC2 instance to avoid a separate RDS bill.

resource "aws_dynamodb_table" "repos" {
  name         = "repos"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "repo_id"

  attribute {
    name = "repo_id"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = { Name = "${var.project_name}-repos" }
}

resource "aws_dynamodb_table" "sessions" {
  name         = "sessions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "session_id"

  attribute {
    name = "session_id"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = { Name = "${var.project_name}-sessions" }
}

resource "aws_dynamodb_table" "rate_limits" {
  name         = "rate_limits"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "key"

  attribute {
    name = "key"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = { Name = "${var.project_name}-rate-limits" }
}

resource "aws_s3_bucket" "code_repos" {
  bucket_prefix = "${var.project_name}-repos-"
  force_destroy = true
  tags          = { Name = "${var.project_name}-repos" }
}

resource "aws_s3_bucket_lifecycle_configuration" "code_repos" {
  bucket = aws_s3_bucket.code_repos.id

  rule {
    id     = "expire-old-repos"
    status = "Enabled"

    filter {}

    expiration {
      days = var.s3_expiration_days
    }
  }
}
