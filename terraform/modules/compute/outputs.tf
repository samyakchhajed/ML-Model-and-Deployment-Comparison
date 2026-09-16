output "api_endpoint" {
  value       = aws_apigatewayv2_stage.default.invoke_url
  description = "HTTP API Gateway stage invoke URL"
}

output "api_id" {
  value       = aws_apigatewayv2_api.http_api.id
  description = "ID of the API Gateway HTTP API"
}

output "experiments_lambda_arn" {
  value       = aws_lambda_function.experiments.arn
  description = "ARN of the experiments Lambda function"
}

output "user_model_worker_lambda_arn" {
  value       = aws_lambda_function.user_model_worker.arn
  description = "ARN of the user_model_worker Lambda function"
}

output "sagemaker_deployer_lambda_arn" {
  value       = aws_lambda_function.sagemaker_deployer.arn
  description = "ARN of the sagemaker_deployer Lambda function"
}

output "autopilot_lambda_arn" {
  value       = aws_lambda_function.autopilot.arn
  description = "ARN of the autopilot Lambda function"
}

output "inference_lambda_arn" {
  value       = aws_lambda_function.inference.arn
  description = "ARN of the inference Lambda function"
}
