output "ec2_public_ip" {
  description = "Elastic public IP attached to the EC2 instance"
  value       = aws_eip.app.public_ip
}

output "ec2_instance_id" {
  description = "EC2 instance ID, useful for stop/start to save credits."
  value       = aws_instance.app.id
}

output "ec2_public_dns" {
  description = "Public DNS of the EC2 instance"
  value       = aws_instance.app.public_dns
}

output "s3_bucket" {
  description = "S3 bucket name for code repos"
  value       = aws_s3_bucket.code_repos.id
}

output "gateway_url" {
  description = "Gateway API URL"
  value       = "http://${aws_eip.app.public_ip}:8080"
}

output "vercel_api_proxy_url" {
  description = "Set this as API_PROXY_URL in Vercel, then redeploy the frontend."
  value       = "http://${aws_eip.app.public_ip}:8080"
}

output "ssh_command" {
  description = "SSH command, if you supplied ec2_key_pair and have the matching private key."
  value       = "ssh ec2-user@${aws_eip.app.public_ip}"
}

output "secret_arn" {
  description = "Secrets Manager ARN"
  value       = aws_secretsmanager_secret.app_secrets.arn
}

output "auto_schedule" {
  description = "EC2 auto stop/start schedule status"
  value       = var.enable_auto_schedule ? "Enabled: stops at midnight IST, starts at 8 AM IST" : "Disabled"
}
