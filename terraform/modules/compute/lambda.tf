# ── Compute Module: Lambda Functions & ML Layer ─────────────────────────────

locals {
  ml_layer_arns = var.custom_layer_arn != "" ? [var.custom_layer_arn] : (length(aws_lambda_layer_version.ml_layer) > 0 ? [aws_lambda_layer_version.ml_layer[0].arn] : [])
}

# ── 1. Shared ML Layer (Provisioned when custom_layer_arn is empty) ──────────────

data "archive_file" "ml_layer_fallback" {
  count       = var.custom_layer_arn == "" ? 1 : 0
  type        = "zip"
  output_path = "${path.module}/build/ml_layer_fallback.zip"

  source {
    content  = "# Python 3.11 Lambda Layer placeholder\n"
    filename = "python/requirements-info.txt"
  }
}

resource "aws_lambda_layer_version" "ml_layer" {
  count               = var.custom_layer_arn == "" ? 1 : 0
  filename            = fileexists("${path.module}/build/ml_layer.zip") ? "${path.module}/build/ml_layer.zip" : data.archive_file.ml_layer_fallback[0].output_path
  source_code_hash    = fileexists("${path.module}/build/ml_layer.zip") ? filebase64sha256("${path.module}/build/ml_layer.zip") : data.archive_file.ml_layer_fallback[0].output_base64sha256
  layer_name          = "${var.project_prefix}-ml-layer-${var.environment}"
  compatible_runtimes = ["python3.11"]
  description         = "ML dependencies: scikit-learn==1.4.2, numpy==1.26.4, pandas==2.2.2"
}

# ── 2. Lambda Archives ──────────────────────────────────────────────────────────

data "archive_file" "experiments_zip" {
  type        = "zip"
  output_path = "${path.module}/build/experiments.zip"

  source_dir = "${var.backend_dir}/experiments"
}

data "archive_file" "user_model_worker_zip" {
  type        = "zip"
  output_path = "${path.module}/build/user_model_worker.zip"

  source_dir = "${var.backend_dir}/user_model_worker"
}

data "archive_file" "autopilot_zip" {
  type        = "zip"
  output_path = "${path.module}/build/autopilot.zip"

  source_dir = "${var.backend_dir}/autopilot"
}

data "archive_file" "inference_zip" {
  type        = "zip"
  output_path = "${path.module}/build/inference.zip"

  source_dir = "${var.backend_dir}/inference"
}

# ── 3. Lambda Functions ─────────────────────────────────────────────────────────

# 3.1 Experiments Lambda (Uses ML Layer for pandas & train/test split)
resource "aws_lambda_function" "experiments" {
  function_name    = "${var.project_prefix}-experiments-${var.environment}"
  role             = var.lambda_exec_role_arn
  runtime          = "python3.11"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.experiments_zip.output_path
  source_code_hash = data.archive_file.experiments_zip.output_base64sha256
  timeout          = 60
  memory_size      = 512
  layers           = local.ml_layer_arns

  environment {
    variables = {
      ARTIFACTS_BUCKET     = var.s3_bucket_name
      DYNAMODB_TABLE       = var.dynamodb_table_name
      USER_MODEL_WORKER_FN = "${var.project_prefix}-user-model-worker-${var.environment}"
      SAGEMAKER_EXEC_ROLE  = var.sagemaker_exec_role_arn
    }
  }

  tags = {
    Project     = var.project_prefix
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# 3.2 User Model Worker Lambda (Uses ML Layer for model unpickling & inference)
resource "aws_lambda_function" "user_model_worker" {
  function_name    = "${var.project_prefix}-user-model-worker-${var.environment}"
  role             = var.lambda_exec_role_arn
  runtime          = "python3.11"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.user_model_worker_zip.output_path
  source_code_hash = data.archive_file.user_model_worker_zip.output_base64sha256
  timeout          = 60
  memory_size      = 1024
  layers           = local.ml_layer_arns

  environment {
    variables = {
      ARTIFACTS_BUCKET = var.s3_bucket_name
    }
  }

  tags = {
    Project     = var.project_prefix
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# 3.3 SageMaker Deployer Lambda (NO Layer - standard library + runtime boto3)
resource "aws_lambda_function" "sagemaker_deployer" {
  function_name    = "${var.project_prefix}-sagemaker-deployer-${var.environment}"
  role             = var.lambda_exec_role_arn
  runtime          = "python3.11"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.experiments_zip.output_path
  source_code_hash = data.archive_file.experiments_zip.output_base64sha256
  timeout          = 60
  memory_size      = 256
  layers           = []

  environment {
    variables = {
      ARTIFACTS_BUCKET    = var.s3_bucket_name
      DYNAMODB_TABLE      = var.dynamodb_table_name
      SAGEMAKER_EXEC_ROLE = var.sagemaker_exec_role_arn
    }
  }

  tags = {
    Project     = var.project_prefix
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# 3.4 Autopilot Lambda (NO Layer - standard library + runtime boto3)
resource "aws_lambda_function" "autopilot" {
  function_name    = "${var.project_prefix}-autopilot-${var.environment}"
  role             = var.lambda_exec_role_arn
  runtime          = "python3.11"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.autopilot_zip.output_path
  source_code_hash = data.archive_file.autopilot_zip.output_base64sha256
  timeout          = 60
  memory_size      = 256
  layers           = []

  environment {
    variables = {
      ARTIFACTS_BUCKET    = var.s3_bucket_name
      DYNAMODB_TABLE      = var.dynamodb_table_name
      SAGEMAKER_EXEC_ROLE = var.sagemaker_exec_role_arn
      AUTOPILOT_OUTPUT_S3 = "autopilot-output"
    }
  }

  tags = {
    Project     = var.project_prefix
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# 3.5 Inference / Evaluation Lambda (Uses ML Layer for pandas & sklearn evaluation metrics)
resource "aws_lambda_function" "inference" {
  function_name    = "${var.project_prefix}-inference-${var.environment}"
  role             = var.lambda_exec_role_arn
  runtime          = "python3.11"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.inference_zip.output_path
  source_code_hash = data.archive_file.inference_zip.output_base64sha256
  timeout          = 900
  memory_size      = 1024
  layers           = local.ml_layer_arns

  environment {
    variables = {
      ARTIFACTS_BUCKET     = var.s3_bucket_name
      DYNAMODB_TABLE       = var.dynamodb_table_name
      BATCH_TRANSFORM_ROLE = var.sagemaker_exec_role_arn
      BATCH_OUTPUT_PREFIX  = "batch-output"
    }
  }

  tags = {
    Project     = var.project_prefix
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# ── 4. Dedicated CloudWatch Log Groups ───────────────────────────────────────────
# Explicit log group provisioning ensures immediate logging without permission errors
# and guarantees clean teardown during terraform destroy.

resource "aws_cloudwatch_log_group" "experiments" {
  name              = "/aws/lambda/${aws_lambda_function.experiments.function_name}"
  retention_in_days = 14

  tags = {
    Project     = var.project_prefix
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_cloudwatch_log_group" "user_model_worker" {
  name              = "/aws/lambda/${aws_lambda_function.user_model_worker.function_name}"
  retention_in_days = 14

  tags = {
    Project     = var.project_prefix
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_cloudwatch_log_group" "sagemaker_deployer" {
  name              = "/aws/lambda/${aws_lambda_function.sagemaker_deployer.function_name}"
  retention_in_days = 14

  tags = {
    Project     = var.project_prefix
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_cloudwatch_log_group" "autopilot" {
  name              = "/aws/lambda/${aws_lambda_function.autopilot.function_name}"
  retention_in_days = 14

  tags = {
    Project     = var.project_prefix
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_cloudwatch_log_group" "inference" {
  name              = "/aws/lambda/${aws_lambda_function.inference.function_name}"
  retention_in_days = 14

  tags = {
    Project     = var.project_prefix
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}
