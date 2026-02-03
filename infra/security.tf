resource "aws_security_group" "postgres_sg" {
  name        = "agentdesk-postgres-sg"
  description = "Allow Postgres from ECS"
  vpc_id      = aws_vpc.agentdesk_vpc.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_task_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
