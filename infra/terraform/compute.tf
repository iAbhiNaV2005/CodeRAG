# EC2 instance that runs the complete backend stack:
# Gateway + FastAPI + PostgreSQL/pgvector via Docker Compose.

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
    volume_size = var.ec2_root_volume_gb
    volume_type = "gp3"
  }

  dynamic "instance_market_options" {
    for_each = var.use_spot_instance ? [1] : []
    content {
      market_type = "spot"

      spot_options {
        spot_instance_type             = "one-time"
        instance_interruption_behavior = "stop"
        max_price                      = var.spot_max_price != "" ? var.spot_max_price : null
      }
    }
  }

  user_data = base64encode(templatefile("${path.module}/user-data.sh", {
    aws_region     = var.aws_region
    secret_arn     = aws_secretsmanager_secret.app_secrets.arn
    pipeline_image = var.pipeline_image
    gateway_image  = var.gateway_image
  }))

  tags = { Name = "${var.project_name}-server" }
}

resource "aws_eip" "app" {
  domain = "vpc"

  tags = { Name = "${var.project_name}-server-ip" }
}

resource "aws_eip_association" "app" {
  instance_id   = aws_instance.app.id
  allocation_id = aws_eip.app.id
}
