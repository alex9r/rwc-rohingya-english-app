# Public HTTPS entry point: API Gateway HTTP API -> VPC Link -> internal ALB.

terraform {
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

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "alb_listener_arn" {
  type = string
}

variable "alb_security_group_id" {
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

resource "aws_security_group" "vpc_link" {
  name        = "${var.name}-vpc-link"
  description = "API Gateway VPC Link: HTTP out to the internal ALB only"
  vpc_id      = var.vpc_id

  egress {
    description     = "HTTP to the internal ALB"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [var.alb_security_group_id]
  }
}

resource "aws_security_group_rule" "alb_from_vpc_link" {
  description              = "HTTP from the API Gateway VPC Link"
  type                     = "ingress"
  security_group_id        = var.alb_security_group_id
  source_security_group_id = aws_security_group.vpc_link.id
  protocol                 = "tcp"
  from_port                = 80
  to_port                  = 80
}

resource "aws_apigatewayv2_vpc_link" "this" {
  name               = var.name
  subnet_ids         = var.subnet_ids
  security_group_ids = [aws_security_group.vpc_link.id]
}

resource "aws_apigatewayv2_api" "this" {
  name          = var.name
  protocol_type = "HTTP"
  description   = "RWC Rohingya-English learning app API"
}

resource "aws_apigatewayv2_integration" "alb" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "ANY"
  integration_uri        = var.alb_listener_arn
  connection_type        = "VPC_LINK"
  connection_id          = aws_apigatewayv2_vpc_link.this.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 30000

  # The app logs this as its request ID, so API Gateway and app logs line up.
  request_parameters = {
    "overwrite:header.X-Request-ID" = "$context.requestId"
  }
}

resource "aws_apigatewayv2_route" "default" {
  #checkov:skip=CKV_AWS_309:No learner auth yet (spec §8 Q2); throttling is the only protection.
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.alb.id}"
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
