# The API on ECS Fargate behind an internal ALB, in private subnets across two AZs.

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

variable "region" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "vpc_cidr" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "gateway_prefix_list_ids" {
  type = list(string)
}

variable "image" {
  description = "Initial image. Later images are deployed by GitHub Actions, not Terraform."
  type        = string
}

variable "execution_role_arn" {
  type = string
}

variable "task_role_arn" {
  type = string
}

variable "cpu" {
  type = number
}

variable "memory" {
  type = number
}

variable "desired_count" {
  description = "Minimum tasks. 0 only for the very first apply, before an image exists."
  type        = number
}

variable "max_count" {
  type = number
}

variable "environment" {
  description = "Container environment variables."
  type        = map(string)
}

variable "log_retention_days" {
  type = number
}

variable "alb_deletion_protection" {
  type = bool
}

resource "aws_cloudwatch_log_group" "api" {
  #checkov:skip=CKV_AWS_158:AWS-managed encryption; the app keeps learner data out of logs (spec §5.1).
  #checkov:skip=CKV_AWS_338:30-day retention is intentional for application logs.
  name              = "/ecs/${var.name}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_cluster" "this" {
  name = var.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  # Writable scratch space (uploads spool to /tmp); the root filesystem is read-only.
  volume {
    name = "tmp"
  }

  container_definitions = jsonencode([{
    name                   = "api"
    image                  = var.image
    essential              = true
    readonlyRootFilesystem = true
    user                   = "10001"
    portMappings           = [{ containerPort = 8000, protocol = "tcp" }]
    environment            = [for key, value in var.environment : { name = key, value = value }]
    mountPoints            = [{ sourceVolume = "tmp", containerPath = "/tmp" }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "api"
      }
    }
  }])
}

# ------------------------------------------------------------ networking

resource "aws_security_group" "alb" {
  name        = "${var.name}-alb"
  description = "Internal ALB. Ingress from the VPC Link is added by the api module."
  vpc_id      = var.vpc_id
}

resource "aws_security_group_rule" "alb_to_tasks" {
  description              = "ALB to API tasks"
  type                     = "egress"
  security_group_id        = aws_security_group.alb.id
  source_security_group_id = aws_security_group.tasks.id
  protocol                 = "tcp"
  from_port                = 8000
  to_port                  = 8000
}

resource "aws_security_group" "tasks" {
  name        = "${var.name}-tasks"
  description = "API tasks: HTTP from the ALB only, HTTPS out to AWS endpoints only"
  vpc_id      = var.vpc_id

  ingress {
    description     = "HTTP from the ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "HTTPS to the interface endpoints (ECR, Logs)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description     = "HTTPS to the S3 and DynamoDB gateway endpoints"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    prefix_list_ids = var.gateway_prefix_list_ids
  }
}

resource "aws_lb" "api" {
  #checkov:skip=CKV_AWS_91:ALB access logs are deferred; API Gateway access logs cover requests.
  #checkov:skip=CKV2_AWS_28:No WAF: the ALB is internal and only reachable through API Gateway.
  name                       = "${var.name}-api"
  internal                   = true
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.alb.id]
  subnets                    = var.subnet_ids
  drop_invalid_header_fields = true
  enable_deletion_protection = var.alb_deletion_protection
}

resource "aws_lb_target_group" "api" {
  name                 = "${var.name}-api"
  port                 = 8000
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = var.vpc_id
  deregistration_delay = 30

  health_check {
    path                = "/health"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "http" {
  #checkov:skip=CKV_AWS_2:TLS ends at API Gateway; this listener is internal (VPC Link only).
  #checkov:skip=CKV_AWS_103:TLS ends at API Gateway; this listener is internal (VPC Link only).
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# --------------------------------------------------------------- service

resource "aws_ecs_service" "api" {
  name                              = "${var.name}-api"
  cluster                           = aws_ecs_cluster.this.id
  task_definition                   = aws_ecs_task_definition.api.arn
  desired_count                     = var.desired_count
  launch_type                       = "FARGATE"
  health_check_grace_period_seconds = 120

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  # Roll back automatically if a new image never becomes healthy.
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # GitHub Actions deploys new task definitions, and autoscaling owns the task count.
  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [aws_lb_listener.http]
}

resource "aws_appautoscaling_target" "api" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = var.desired_count
  max_capacity       = var.desired_count == 0 ? 0 : var.max_count
}

resource "aws_appautoscaling_policy" "cpu" {
  name               = "${var.name}-api-cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.api.service_namespace
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension

  target_tracking_scaling_policy_configuration {
    target_value = 60

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "service_name" {
  value = aws_ecs_service.api.name
}

output "service_arn" {
  value = aws_ecs_service.api.id
}

output "task_family" {
  value = aws_ecs_task_definition.api.family
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.api.name
}

output "log_group_arn" {
  value = aws_cloudwatch_log_group.api.arn
}

output "alb_listener_arn" {
  value = aws_lb_listener.http.arn
}

output "alb_security_group_id" {
  value = aws_security_group.alb.id
}

output "alb_arn_suffix" {
  value = aws_lb.api.arn_suffix
}

output "target_group_arn_suffix" {
  value = aws_lb_target_group.api.arn_suffix
}
