variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name prefix for all resources"
  type        = string
  default     = "code-rag"
}

variable "db_password" {
  description = "PostgreSQL master password"
  type        = string
  sensitive   = true
}

variable "jwt_secret" {
  description = "JWT signing secret (min 32 chars)"
  type        = string
  sensitive   = true
}

variable "google_api_key" {
  description = "Google AI API key for Gemini"
  type        = string
  sensitive   = true
}

variable "github_token" {
  description = "GitHub personal access token"
  type        = string
  sensitive   = true
  default     = ""
}

variable "ec2_key_pair" {
  description = "EC2 SSH key pair name"
  type        = string
  default     = ""
}

variable "ec2_instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.small"
}

variable "ec2_root_volume_gb" {
  description = "Size of the root EBS volume in GB."
  type        = number
  default     = 30
}

variable "use_spot_instance" {
  description = "Use an EC2 Spot instance. Cheaper, but demo availability is less predictable."
  type        = bool
  default     = false
}

variable "spot_max_price" {
  description = "Optional max hourly Spot price. Leave empty to use the current Spot market price."
  type        = string
  default     = ""
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed to SSH to the EC2 instance. Replace with your IP/32 for better security."
  type        = string
  default     = "0.0.0.0/0"
}

variable "allowed_api_cidr" {
  description = "CIDR allowed to reach the public gateway on port 8080."
  type        = string
  default     = "0.0.0.0/0"
}

variable "pipeline_image" {
  description = "Container image for the FastAPI RAG pipeline."
  type        = string
  default     = "ghcr.io/iabhinav2005/coderag-pipeline:latest"
}

variable "gateway_image" {
  description = "Container image for the Spring Boot gateway."
  type        = string
  default     = "ghcr.io/iabhinav2005/coderag-gateway:latest"
}

variable "s3_expiration_days" {
  description = "Days to keep raw fetched repository files in S3."
  type        = number
  default     = 7
}
