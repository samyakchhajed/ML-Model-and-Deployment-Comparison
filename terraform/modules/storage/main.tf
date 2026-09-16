# ── Storage Module: S3 Artifacts Bucket ──────────────────────────────────────────

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

variable "cors_allowed_origins" {
  type        = list(string)
  description = "Allowed origins for S3 CORS"
  default     = ["*"]
}

resource "random_id" "storage_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "artifacts" {
  bucket        = "${var.project_prefix}-artifacts-${var.environment}-${random_id.storage_suffix.hex}"
  force_destroy = true

  tags = {
    Project     = var.project_prefix
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_s3_bucket_versioning" "artifacts_versioning" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts_encryption" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts_public_block" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_cors_configuration" "artifacts_cors" {
  bucket = aws_s3_bucket.artifacts.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST", "HEAD"]
    allowed_origins = var.cors_allowed_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

output "bucket_name" {
  value       = aws_s3_bucket.artifacts.id
  description = "Name of the S3 artifacts bucket"
}

output "bucket_arn" {
  value       = aws_s3_bucket.artifacts.arn
  description = "ARN of the S3 artifacts bucket"
}
