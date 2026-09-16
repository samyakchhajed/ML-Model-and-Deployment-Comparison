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

variable "s3_bucket_name" {
  type        = string
  description = "Name of the S3 artifacts bucket"
}

variable "dynamodb_table_name" {
  type        = string
  description = "Name of the DynamoDB table"
}

variable "lambda_exec_role_arn" {
  type        = string
  description = "ARN of the Lambda execution IAM role"
}

variable "sagemaker_exec_role_arn" {
  type        = string
  description = "ARN of the SageMaker execution IAM role"
}

variable "custom_layer_arn" {
  type        = string
  description = "Optional pre-existing Lambda Layer ARN (e.g. AWS-managed Pandas/Scikit-learn layer). If empty, a custom layer is provisioned."
  default     = ""
}

variable "backend_dir" {
  type        = string
  description = "Path to the backend source code directory"
  default     = "../backend"
}
