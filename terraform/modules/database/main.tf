# ── Database Module: DynamoDB Single-Table ───────────────────────────────────────

variable "project_prefix" {
  type        = string
  description = "Project name prefix for resource naming"
  default     = "ml-benchmark"
}

variable "environment" {
  type        = string
  description = "Deployment environment (e.g. dev, prod)"
  default     = "dev"
}

resource "aws_dynamodb_table" "experiments" {
  name         = "${var.project_prefix}-experiments-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Project     = var.project_prefix
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

output "table_name" {
  value       = aws_dynamodb_table.experiments.name
  description = "Name of the DynamoDB table"
}

output "table_arn" {
  value       = aws_dynamodb_table.experiments.arn
  description = "ARN of the DynamoDB table"
}
