resource "aws_ecs_task_definition" "qdrant" {
  family                   = "agentdesk-qdrant"
  cpu                      = "512"
  memory                   = "1024"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
  {
    name      = "qdrant"
    image     = "qdrant/qdrant:v1.15.3"
    essential = true

    portMappings = [
      {
        containerPort = 6333
        protocol      = "tcp"
      }
    ]

    environment = [
      {
        name  = "QDRANT__SERVICE__HOST"
        value = "0.0.0.0"
      }
    ]
  }
])
}

resource "aws_ecs_service" "qdrant" {
  name            = "agentdesk-qdrant"
  cluster         = aws_ecs_cluster.agentdesk.id
  task_definition = aws_ecs_task_definition.qdrant.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  enable_execute_command = true

  network_configuration {
    subnets         = [aws_subnet.agentdesk_subnet.id, aws_subnet.agentdesk_subnet_b.id]
    security_groups = [aws_security_group.ecs_task_sg.id]
    assign_public_ip = true
  }

  service_registries {
    registry_arn = aws_service_discovery_service.qdrant.arn
  }

  depends_on = [
    aws_service_discovery_service.qdrant
  ]
}

resource "aws_service_discovery_service" "qdrant" {
  name = "qdrant"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.agentdesk.id

    dns_records {
      ttl  = 10
      type = "A"
    }
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}
