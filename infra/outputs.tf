output "ecr_repo_url" {
  value = aws_ecr_repository.agentdesk.repository_url
}

output "rds_endpoint" {
  value = aws_db_instance.postgres.address
}

# output "alb_dns" {
#  value = aws_lb.alb.dns_name
# }

output "subnet_a" {
  value = aws_subnet.agentdesk_subnet.id
}

output "subnet_b" {
  value = aws_subnet.agentdesk_subnet_b.id
}

output "ecs_sg" {
  value = aws_security_group.ecs_task_sg.id
}
