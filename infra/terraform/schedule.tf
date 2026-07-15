# ═══════════════════════════════════════════════════════════
# EC2 Auto Stop/Start Schedule (saves compute cost overnight)
#
# Stops the EC2 instance at midnight IST (18:30 UTC) and
# starts it at 8:00 AM IST (02:30 UTC), Monday-Sunday.
#
# When stopped, compute billing pauses but EBS (pgvector data)
# persists. The Elastic IP stays attached and free.
# ═══════════════════════════════════════════════════════════

variable "enable_auto_schedule" {
  description = "Enable automatic EC2 stop/start to save overnight compute costs."
  type        = bool
  default     = true
}

variable "schedule_stop_cron" {
  description = "Cron expression (UTC) to stop the EC2 instance. Default: midnight IST = 18:30 UTC."
  type        = string
  default     = "cron(30 18 * * ? *)"
}

variable "schedule_start_cron" {
  description = "Cron expression (UTC) to start the EC2 instance. Default: 8 AM IST = 02:30 UTC."
  type        = string
  default     = "cron(30 2 * * ? *)"
}

# ── IAM Role for Lambda ─────────────────────────────────────

resource "aws_iam_role" "scheduler" {
  count = var.enable_auto_schedule ? 1 : 0
  name  = "${var.project_name}-ec2-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "scheduler_ec2" {
  count = var.enable_auto_schedule ? 1 : 0
  name  = "ec2-stop-start"
  role  = aws_iam_role.scheduler[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ec2:StopInstances", "ec2:StartInstances"]
      Resource = aws_instance.app.arn
    }]
  })
}

resource "aws_iam_role_policy_attachment" "scheduler_logs" {
  count      = var.enable_auto_schedule ? 1 : 0
  role       = aws_iam_role.scheduler[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ── Lambda Functions ─────────────────────────────────────────

data "archive_file" "stop_lambda" {
  count       = var.enable_auto_schedule ? 1 : 0
  type        = "zip"
  output_path = "${path.module}/.terraform/lambda_stop.zip"

  source {
    content  = <<-PYTHON
import boto3, os
def handler(event, context):
    ec2 = boto3.client('ec2', region_name=os.environ['AWS_REGION'])
    instance_id = os.environ['INSTANCE_ID']
    ec2.stop_instances(InstanceIds=[instance_id])
    print(f"Stopped instance {instance_id}")
    return {"status": "stopped", "instance_id": instance_id}
PYTHON
    filename = "lambda_function.py"
  }
}

data "archive_file" "start_lambda" {
  count       = var.enable_auto_schedule ? 1 : 0
  type        = "zip"
  output_path = "${path.module}/.terraform/lambda_start.zip"

  source {
    content  = <<-PYTHON
import boto3, os
def handler(event, context):
    ec2 = boto3.client('ec2', region_name=os.environ['AWS_REGION'])
    instance_id = os.environ['INSTANCE_ID']
    ec2.start_instances(InstanceIds=[instance_id])
    print(f"Started instance {instance_id}")
    return {"status": "started", "instance_id": instance_id}
PYTHON
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "stop_ec2" {
  count         = var.enable_auto_schedule ? 1 : 0
  function_name = "${var.project_name}-stop-ec2"
  role          = aws_iam_role.scheduler[0].arn
  handler       = "lambda_function.handler"
  runtime       = "python3.12"
  timeout       = 30
  filename      = data.archive_file.stop_lambda[0].output_path

  source_code_hash = data.archive_file.stop_lambda[0].output_base64sha256

  environment {
    variables = {
      INSTANCE_ID = aws_instance.app.id
    }
  }

  tags = { Name = "${var.project_name}-stop-ec2" }
}

resource "aws_lambda_function" "start_ec2" {
  count         = var.enable_auto_schedule ? 1 : 0
  function_name = "${var.project_name}-start-ec2"
  role          = aws_iam_role.scheduler[0].arn
  handler       = "lambda_function.handler"
  runtime       = "python3.12"
  timeout       = 30
  filename      = data.archive_file.start_lambda[0].output_path

  source_code_hash = data.archive_file.start_lambda[0].output_base64sha256

  environment {
    variables = {
      INSTANCE_ID = aws_instance.app.id
    }
  }

  tags = { Name = "${var.project_name}-start-ec2" }
}

# ── EventBridge Schedules ────────────────────────────────────

resource "aws_cloudwatch_event_rule" "stop_ec2" {
  count               = var.enable_auto_schedule ? 1 : 0
  name                = "${var.project_name}-stop-ec2"
  description         = "Stop Code RAG EC2 at midnight IST to save compute costs"
  schedule_expression = var.schedule_stop_cron

  tags = { Name = "${var.project_name}-stop-schedule" }
}

resource "aws_cloudwatch_event_rule" "start_ec2" {
  count               = var.enable_auto_schedule ? 1 : 0
  name                = "${var.project_name}-start-ec2"
  description         = "Start Code RAG EC2 at 8 AM IST"
  schedule_expression = var.schedule_start_cron

  tags = { Name = "${var.project_name}-start-schedule" }
}

resource "aws_cloudwatch_event_target" "stop_ec2" {
  count     = var.enable_auto_schedule ? 1 : 0
  rule      = aws_cloudwatch_event_rule.stop_ec2[0].name
  target_id = "stop-ec2"
  arn       = aws_lambda_function.stop_ec2[0].arn
}

resource "aws_cloudwatch_event_target" "start_ec2" {
  count     = var.enable_auto_schedule ? 1 : 0
  rule      = aws_cloudwatch_event_rule.start_ec2[0].name
  target_id = "start-ec2"
  arn       = aws_lambda_function.start_ec2[0].arn
}

resource "aws_lambda_permission" "stop_ec2" {
  count         = var.enable_auto_schedule ? 1 : 0
  statement_id  = "AllowEventBridgeStop"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.stop_ec2[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.stop_ec2[0].arn
}

resource "aws_lambda_permission" "start_ec2" {
  count         = var.enable_auto_schedule ? 1 : 0
  statement_id  = "AllowEventBridgeStart"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.start_ec2[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.start_ec2[0].arn
}
