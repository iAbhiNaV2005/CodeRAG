# ═══════════════════════════════════════════════════════════
# RDS PostgreSQL with pgvector
# ═══════════════════════════════════════════════════════════

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet"
  subnet_ids = [aws_subnet.public_a.id, aws_subnet.public_b.id]
  tags       = { Name = "${var.project_name}-db-subnet" }
}

resource "aws_db_instance" "postgres" {
  identifier     = "${var.project_name}-db"
  engine         = "postgres"
  engine_version = "16.3"
  instance_class = "db.t3.micro"

  allocated_storage = 20
  storage_encrypted = false

  db_name  = "coderag"
  username = "coderag"
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  skip_final_snapshot     = true
  backup_retention_period = 0

  tags = { Name = "${var.project_name}-db" }
}

# ═══════════════════════════════════════════════════════════
# DynamoDB Tables
# ═══════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════
# S3 Bucket for code storage
# ═══════════════════════════════════════════════════════════

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
      days = 30
    }
  }
}
