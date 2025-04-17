# variables.tf
variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "vpc_id" {
  description = "VPC ID where resources will be created"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t2.micro"
}

variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "devops-ai-assistant"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "ami_id" {
  type        = string
  default     = "ami-00a929b66ed6e0de6"
  description = "AMI ID for EC2 instance"
}

variable "ec2_subnet_id" {
  type        = string
  description = "Subnet ID in which EC2 instance need to be created."
}

variable "alb_subnet_ids" {
  type        = list(string)
  description = "List of subnet ID's in which ALB need to be created."
}