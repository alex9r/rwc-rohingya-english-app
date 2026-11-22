# The first group becomes GitHub repository variables (Settings -> Variables -> Actions).

output "AWS_ROLE_ARN" {
  description = "GitHub variable AWS_ROLE_ARN: the role deploy.yml assumes."
  value       = module.iam.github_deploy_role_arn
}

output "ECR_REPOSITORY" {
  description = "GitHub variable ECR_REPOSITORY."
  value       = module.ecr.repository_name
}

output "LAMBDA_FUNCTION" {
  description = "GitHub variable LAMBDA_FUNCTION."
  value       = local.function_name
}

output "API_URL" {
  description = "GitHub variable API_URL, and EXPO_PUBLIC_API_URL for the app."
  value       = module.api.api_url
}

output "loader_role_arn" {
  description = "Assume this to run `python -m app.dynamo_load` against AWS."
  value       = module.iam.loader_role_arn
}

output "table_name" {
  description = "VOCAB_TABLE for the loader (the data stack's content table)."
  value       = data.aws_dynamodb_table.content.name
}

output "dashboard_url" {
  value = module.monitoring.dashboard_url
}

output "alerts_topic_arn" {
  value = module.monitoring.alerts_topic_arn
}
