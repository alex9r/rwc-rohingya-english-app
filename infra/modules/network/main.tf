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

variable "cidr_block" {
  type    = string
  default = "10.20.0.0/16"
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

resource "aws_vpc" "this" {
  #checkov:skip=CKV2_AWS_11:VPC flow logs are deferred to keep cost down; see docs/aws-architecture.md §8.
  cidr_block           = var.cidr_block
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = var.name }
}

# No rules: nothing should ever use the default security group.
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id
}

# Private subnets only. Nothing in this VPC has a public IP or a route to the internet;
# AWS services are reached through the endpoints below.
resource "aws_subnet" "private" {
  count = length(local.azs)

  vpc_id            = aws_vpc.this.id
  availability_zone = local.azs[count.index]
  cidr_block        = cidrsubnet(var.cidr_block, 4, count.index)

  tags = { Name = "${var.name}-private-${local.azs[count.index]}" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  tags = { Name = "${var.name}-private" }
}

resource "aws_route_table_association" "private" {
  count = length(aws_subnet.private)

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# Gateway endpoints (free): S3 for ECR image layers, DynamoDB for the lexicon.
resource "aws_vpc_endpoint" "gateway" {
  for_each = toset(["s3", "dynamodb"])

  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.region}.${each.key}"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = { Name = "${var.name}-${each.key}" }
}

resource "aws_security_group" "endpoints" {
  name        = "${var.name}-endpoints"
  description = "HTTPS from inside the VPC to the interface endpoints"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "HTTPS from the VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.cidr_block]
  }
}

# Interface endpoints (billed per AZ-hour): pull images and write logs without a NAT gateway.
resource "aws_vpc_endpoint" "interface" {
  for_each = toset(["ecr.api", "ecr.dkr", "logs"])

  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${var.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true

  tags = { Name = "${var.name}-${each.key}" }
}

output "vpc_id" {
  value = aws_vpc.this.id
}

output "cidr_block" {
  value = aws_vpc.this.cidr_block
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "gateway_prefix_list_ids" {
  description = "S3 and DynamoDB prefix lists, for security group egress rules."
  value       = [for endpoint in aws_vpc_endpoint.gateway : endpoint.prefix_list_id]
}
