# ── Compute Module: API Gateway HTTP API (v2) ──────────────────────────────────

resource "aws_apigatewayv2_api" "http_api" {
  name          = "${var.project_prefix}-api-${var.environment}"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "OPTIONS", "PUT", "DELETE"]
    allow_headers = ["*"]
    max_age       = 300
  }

  tags = {
    Project     = var.project_prefix
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = "$default"
  auto_deploy = true

  tags = {
    Project     = var.project_prefix
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# ── Integrations ─────────────────────────────────────────────────────────────

resource "aws_apigatewayv2_integration" "experiments" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.experiments.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "autopilot" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.autopilot.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "inference" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.inference.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# ── Routes: Experiments ───────────────────────────────────────────────────────

resource "aws_apigatewayv2_route" "get_experiments" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /experiments"
  target    = "integrations/${aws_apigatewayv2_integration.experiments.id}"
}

resource "aws_apigatewayv2_route" "post_experiments" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /experiments"
  target    = "integrations/${aws_apigatewayv2_integration.experiments.id}"
}

resource "aws_apigatewayv2_route" "get_experiment_by_id" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /experiments/{id}"
  target    = "integrations/${aws_apigatewayv2_integration.experiments.id}"
}

resource "aws_apigatewayv2_route" "post_experiment_model" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /experiments/{id}/model"
  target    = "integrations/${aws_apigatewayv2_integration.experiments.id}"
}

resource "aws_apigatewayv2_route" "post_deploy_lambda" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /experiments/{id}/deploy/lambda"
  target    = "integrations/${aws_apigatewayv2_integration.experiments.id}"
}

resource "aws_apigatewayv2_route" "post_deploy_sagemaker" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /experiments/{id}/deploy/sagemaker"
  target    = "integrations/${aws_apigatewayv2_integration.experiments.id}"
}

# ── Routes: Autopilot ─────────────────────────────────────────────────────────

resource "aws_apigatewayv2_route" "post_autopilot_start" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /experiments/{id}/autopilot/start"
  target    = "integrations/${aws_apigatewayv2_integration.autopilot.id}"
}

resource "aws_apigatewayv2_route" "get_autopilot_status" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /experiments/{id}/autopilot/status"
  target    = "integrations/${aws_apigatewayv2_integration.autopilot.id}"
}

# ── Routes: Inference & Comparison ───────────────────────────────────────────

resource "aws_apigatewayv2_route" "post_compare" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /experiments/{id}/compare"
  target    = "integrations/${aws_apigatewayv2_integration.inference.id}"
}

resource "aws_apigatewayv2_route" "get_results" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /experiments/{id}/results"
  target    = "integrations/${aws_apigatewayv2_integration.inference.id}"
}

# ── Lambda Permissions for API Gateway ───────────────────────────────────────

resource "aws_lambda_permission" "api_gw_experiments" {
  statement_id  = "AllowAPIGatewayInvokeExperiments"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.experiments.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "api_gw_autopilot" {
  statement_id  = "AllowAPIGatewayInvokeAutopilot"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.autopilot.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "api_gw_inference" {
  statement_id  = "AllowAPIGatewayInvokeInference"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.inference.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}
