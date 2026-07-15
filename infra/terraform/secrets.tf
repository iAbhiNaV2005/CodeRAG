# ═══════════════════════════════════════════════════════════
# Secrets Manager
# ═══════════════════════════════════════════════════════════

resource "aws_secretsmanager_secret" "app_secrets" {
  name                    = "${var.project_name}/app-secrets"
  recovery_window_in_days = 0 # Allow immediate deletion for dev
  tags                    = { Name = "${var.project_name}-secrets" }
}

resource "aws_secretsmanager_secret_version" "app_secrets" {
  secret_id = aws_secretsmanager_secret.app_secrets.id
  secret_string = jsonencode({
    POSTGRES_URL      = "postgresql://coderag:${var.db_password}@postgres:5432/coderag"
    POSTGRES_PASSWORD = var.db_password
    GOOGLE_API_KEY    = var.google_api_key
    GITHUB_TOKEN      = var.github_token
    JWT_SECRET        = var.jwt_secret
    S3_BUCKET         = aws_s3_bucket.code_repos.id
  })
}

# ═══════════════════════════════════════════════════════════
# IAM Role for EC2
# ═══════════════════════════════════════════════════════════

resource "aws_iam_role" "ec2_role" {
  name = "${var.project_name}-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

# DynamoDB access
resource "aws_iam_role_policy" "dynamodb" {
  name = "dynamodb-access"
  role = aws_iam_role.ec2_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ]
      Resource = [
        aws_dynamodb_table.repos.arn,
        aws_dynamodb_table.sessions.arn,
        aws_dynamodb_table.rate_limits.arn,
      ]
    }]
  })
}

# S3 access
resource "aws_iam_role_policy" "s3" {
  name = "s3-access"
  role = aws_iam_role.ec2_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:ListBucket"]
      Resource = [
        aws_s3_bucket.code_repos.arn,
        "${aws_s3_bucket.code_repos.arn}/*"
      ]
    }]
  })
}

# Secrets Manager access
resource "aws_iam_role_policy" "secrets" {
  name = "secrets-access"
  role = aws_iam_role.ec2_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [aws_secretsmanager_secret.app_secrets.arn]
    }]
  })
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${var.project_name}-ec2-profile"
  role = aws_iam_role.ec2_role.name
}
