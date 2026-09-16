# ── Frontend Module: S3 Static Hosting + CloudFront OAC ────────────────────────

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

resource "aws_s3_bucket_public_access_block" "site_public_block" {
  bucket = aws_s3_bucket.site.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site_encryption" {
  bucket = aws_s3_bucket.site.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# ── 2. CloudFront Origin Access Control (OAC) ────────────────────────────────

resource "aws_cloudfront_origin_access_control" "oac" {
  name                              = "${var.project_prefix}-oac-${var.environment}"
  description                       = "OAC for ML benchmark frontend S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ── 3. CloudFront CDN Distribution ───────────────────────────────────────────

resource "aws_cloudfront_distribution" "cdn" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.oac.id
  }

  default_cache_behavior {
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # AWS Managed CachingOptimized Policy
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }

  # SPA Client-Side Routing Fallbacks (Hash routing / index.html fallback)
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Project     = var.project_prefix
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# ── 4. S3 Bucket Policy for CloudFront OAC ───────────────────────────────────

resource "aws_s3_bucket_policy" "site_policy" {
  bucket = aws_s3_bucket.site.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowCloudFrontOACReadOnly"
        Effect    = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.site.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.cdn.arn
          }
        }
      }
    ]
  })
}

# ── 5. Outputs ───────────────────────────────────────────────────────────────

output "website_url" {
  value       = "https://${aws_cloudfront_distribution.cdn.domain_name}"
  description = "Public HTTPS URL for the frontend application"
}

output "cloudfront_domain_name" {
  value       = aws_cloudfront_distribution.cdn.domain_name
  description = "CloudFront distribution domain name"
}

output "cloudfront_distribution_id" {
  value       = aws_cloudfront_distribution.cdn.id
  description = "CloudFront distribution ID (used for cache invalidation)"
}

output "s3_bucket_name" {
  value       = aws_s3_bucket.site.id
  description = "Name of the S3 static hosting bucket"
}
