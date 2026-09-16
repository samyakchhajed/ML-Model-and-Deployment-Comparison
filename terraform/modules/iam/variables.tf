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

variable "s3_bucket_arn" {
  type        = string
  description = "ARN of the S3 artifacts bucket"
}

variable "dynamodb_table_arn" {
  type        = string
  description = "ARN of the DynamoDB table"
}
