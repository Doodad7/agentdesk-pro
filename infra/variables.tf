variable "aws_region" {
  type    = string
  default = "eu-north-1"
}

variable "ecr_image_tag" {
  type    = string
  default = "latest"
}

variable "db_username" {
  type    = string
  default = "agentdesk"
}

variable "db_password" {
  type        = string
  description = "Postgres password"
  sensitive   = true
}

variable "db_allocated_storage" {
  type    = number
  default = 20
}

variable "ecs_desired_count" {
  type    = number
  default = 1
}

variable "container_port" {
  type    = number
  default = 8000
}
