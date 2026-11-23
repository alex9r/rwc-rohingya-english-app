# Public HTTPS entry point: API Gateway HTTP API -> the API's Lambda function ("live" alias).

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80"
    }
  }
}

variable "name" {
  type = string
}

variable "function_name" {
  type = string
}

variable "alias_name" {
  description = "API Gateway calls this alias; the deploy workflow moves it between versions."
  type        = string
}

variable "alias_invoke_arn" {
  type = string
}

variable "throttle_rate" {
  description = "Steady-state requests per second across the whole API."
  type        = number
}

variable "throttle_burst" {
  type = number
}

variable "log_retention_days" {
  type = number
}

resource "aws_apigatewayv2_api" "this" {
  name          = var.name
  protocol_type = "HTTP"
  description   = "RWC Rohingya-English learning app API"
}

# Payload 2.0: the Lambda Web Adapter in the image turns these events back into plain
# HTTP requests for uvicorn, and passes requestContext (with API Gateway's request ID)
# in the x-amzn-request-context header, which app.observability logs.
resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = var.alias_invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000 # HTTP API maximum
}

resource "aws_apigatewayv2_route" "default" {
  #checkov:skip=CKV_AWS_309:No learner auth yet (spec §8 Q2); throttling is the only protection.
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.function_name
  qualifier     = var.alias_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*"
}

resource "aws_cloudwatch_log_group" "access" {
  #checkov:skip=CKV_AWS_158:AWS-managed encryption; access logs hold no request bodies or IPs.
  #checkov:skip=CKV_AWS_338:30-day retention is intentional for access logs.
  name              = "/aws/apigateway/${var.name}"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit    = var.throttle_rate
    throttling_burst_limit   = var.throttle_burst
    detailed_metrics_enabled = true
  }

  # No source IPs, query strings or bodies (learner privacy, spec §5.1).
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.access.arn
    format = jsonencode({
      requestId          = "$context.requestId"
      path               = "$context.path"
      method             = "$context.httpMethod"
      status             = "$context.status"
      latencyMs          = "$context.responseLatency"
      integrationStatus  = "$context.integration.status"
      integrationLatency = "$context.integration.latency"
      integrationError   = "$context.integration.error"
      responseLength     = "$context.responseLength"
    })
  }
}

output "api_id" {
  value = aws_apigatewayv2_api.this.id
}

output "api_url" {
  value = aws_apigatewayv2_api.this.api_endpoint
}

output "stage_name" {
  value = aws_apigatewayv2_stage.default.name
}
