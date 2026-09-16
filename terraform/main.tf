# ── Root Terraform Configuration: ML Model & Deployment Workbench ─────────────

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }
}

# ── Root Variables with Default Configurations ───────────────────────────────

variable "aws_region" {
  type        = string
  description = "AWS deployment region"
  default     = "ap-south-1"
}

variable "project_prefix" {
  type        = string
  description = "Project name prefix applied to all resources"
  default     = "ml-benchmark"
}

variable "environment" {
  type        = string
  description = "Environment tier (e.g. dev, prod)"
  default     = "dev"
}

variable "custom_layer_arn" {
  type        = string
  description = "Optional pre-existing Lambda Layer ARN (e.g. AWS-managed Pandas layer). If empty, custom layer is provisioned."
  default     = ""
}

# ── Provider Configuration ───────────────────────────────────────────────────

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_prefix
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# ── 1. Storage Module ────────────────────────────────────────────────────────

module "storage" {
  source         = "./modules/storage"
  project_prefix = var.project_prefix
  environment    = var.environment
}

# ── 2. Database Module ───────────────────────────────────────────────────────

module "database" {
  source         = "./modules/database"
  project_prefix = var.project_prefix
  environment    = var.environment
}

# ── 3. Least-Privilege IAM Module ────────────────────────────────────────────

module "iam" {
  source             = "./modules/iam"
  project_prefix     = var.project_prefix
  environment        = var.environment
  s3_bucket_arn      = module.storage.bucket_arn
  dynamodb_table_arn = module.database.table_arn
}

# ── 4. Compute Module (Lambdas + Layer + API Gateway) ─────────────────────────

module "compute" {
  source                 = "./modules/compute"
  project_prefix         = var.project_prefix
  environment            = var.environment
  s3_bucket_name         = module.storage.bucket_name
  dynamodb_table_name    = module.database.table_name
  lambda_exec_role_arn   = module.iam.lambda_exec_role_arn
  sagemaker_exec_role_arn = module.iam.sagemaker_exec_role_arn
  custom_layer_arn       = var.custom_layer_arn
  backend_dir            = "${path.root}/../backend"
}

# ── 5. Frontend Hosting Module (S3 + CloudFront OAC) ─────────────────────────

module "frontend" {
  source         = "./modules/frontend"
  project_prefix = var.project_prefix
  environment    = var.environment
}

# ── Root Outputs ─────────────────────────────────────────────────────────────

output "website_url" {
  value       = module.frontend.website_url
  description = "Public HTTPS CloudFront URL for the web application"
}

output "api_gateway_url" {
  value       = module.compute.api_endpoint
  description = "Public HTTPS API Gateway invoke URL (set as CONFIG.API_BASE_URL in frontend)"
}

output "s3_artifacts_bucket" {
  value       = module.storage.bucket_name
  description = "S3 bucket storing datasets, models, splits, and batch transform outputs"
}

output "dynamodb_table_name" {
  value       = module.database.table_name
  description = "Single DynamoDB table name for experiments and results"
}

output "s3_frontend_bucket" {
  value       = module.frontend.s3_bucket_name
  description = "S3 bucket storing frontend static assets"
}

output "cloudfront_distribution_id" {
  value       = module.frontend.cloudfront_distribution_id
  description = "CloudFront Distribution ID for cache invalidations"
}
