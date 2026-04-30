output "ecr_repository_url" {
  description = "ECR repository URL for the application image."
  value       = aws_ecr_repository.app.repository_url
}

output "app_runner_service_url" {
  description = "Public App Runner service URL."
  value       = aws_apprunner_service.app.service_url
}

output "app_runner_service_arn" {
  description = "App Runner service ARN."
  value       = aws_apprunner_service.app.arn
}
