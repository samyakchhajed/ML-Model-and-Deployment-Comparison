# ── Frontend Module: Direct S3 Static Website Hosting ────────────────────────
# Configured for instant deployment bypassing AWS account-level CloudFront verification holds

variable "project_prefix" {
  type        = string
  description = "Project name prefix"
  default     = "ml-benchmark"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
  default     = "dev"
}

resource "random_id" "frontend_suffix" {
  byte_length = 4
}

# ── 1. S3 Website Bucket ─────────────────────────────────────────────────────

resource "aws_s3_bucket" "site" {
  bucket        = "${var.project_prefix}-site-${var.environment}-${random_id.frontend_suffix.hex}"
  force_destroy = true

  tags = {
    Project     = var.project_prefix
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# ── 2. S3 Website Configuration with SPA Fallback ────────────────────────────

resource "aws_s3_bucket_website_configuration" "site_website" {
  bucket = aws_s3_bucket.site.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "index.html"
  }
}

# ── 3. Public Access Block (permit public read policy for website hosting) ──

resource "aws_s3_bucket_public_access_block" "site_public_block" {
  bucket = aws_s3_bucket.site.id

  block_public_acls       = true
  block_public_policy     = false
  ignore_public_acls      = true
  restrict_public_buckets = false
}

# ── 4. Public Read Bucket Policy for Website Hosting ────────────────────────

resource "aws_s3_bucket_policy" "site_policy" {
  bucket     = aws_s3_bucket.site.id
  depends_on = [aws_s3_bucket_public_access_block.site_public_block]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.site.arn}/*"
      }
    ]
  })
}

# ── 5. Outputs ───────────────────────────────────────────────────────────────

output "website_url" {
  value       = "http://${aws_s3_bucket_website_configuration.site_website.website_endpoint}"
  description = "Public URL for the frontend application"
}

output "s3_bucket_name" {
  value       = aws_s3_bucket.site.id
  description = "Name of the S3 static hosting bucket"
}
