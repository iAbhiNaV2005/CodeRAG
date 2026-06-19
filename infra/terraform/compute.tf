# ═══════════════════════════════════════════════════════════
# EC2 Instance (t3.small) — runs FastAPI + Gateway via Docker
# ═══════════════════════════════════════════════════════════

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.ec2_instance_type
  subnet_id              = aws_subnet.public_a.id
  vpc_security_group_ids = [aws_security_group.ec2.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name
  key_name               = var.ec2_key_pair != "" ? var.ec2_key_pair : null

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  user_data = base64encode(templatefile("${path.module}/user-data.sh", {
    aws_region  = var.aws_region
    secret_arn  = aws_secretsmanager_secret.app_secrets.arn
    db_endpoint = aws_db_instance.postgres.endpoint
    s3_bucket   = aws_s3_bucket.code_repos.id
  }))

  tags = { Name = "${var.project_name}-server" }

  depends_on = [aws_db_instance.postgres]
}
