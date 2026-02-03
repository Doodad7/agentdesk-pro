resource "aws_ecs_task_definition" "ingestion" {
  family                   = "agentdesk-ingestion"
  cpu                      = "1024"
  memory                   = "2048"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn

  container_definitions = jsonencode([
    #################################
    # Ingestion container
    #################################
    {
      name      = "ingestion"
      image     = "${aws_ecr_repository.agentdesk.repository_url}:latest"
      essential = true

      command = [
        "python",
        "services/ingestion/ingest_token_chunks.py"
      ]

      environment = [
        { name = "POSTGRES_DB", value = "agentdesk" },
        { name = "POSTGRES_USER", value = "agentdesk" },
        { name = "POSTGRES_PASSWORD", value = "supersecret" },
        { name = "POSTGRES_HOST", value = aws_db_instance.postgres.address },

        { name = "QDRANT_URL", value = "http://qdrant.agentdesk.local:6333" }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = "/ecs/agentdesk"
          awslogs-region        = "eu-north-1"
          awslogs-stream-prefix = "ingestion"
        }
      }
    },

  ])
}

resource "null_resource" "run_ingestion" {
  depends_on = [
    aws_ecs_task_definition.ingestion,
    aws_ecs_service.service,
    aws_db_instance.postgres
  ]

  provisioner "local-exec" {
    command = "aws ecs run-task --cluster ${aws_ecs_cluster.agentdesk.name} --launch-type FARGATE --task-definition ${aws_ecs_task_definition.ingestion.arn} --network-configuration awsvpcConfiguration={subnets=[${aws_subnet.agentdesk_subnet.id},${aws_subnet.agentdesk_subnet_b.id}],securityGroups=[${aws_security_group.ecs_task_sg.id}],assignPublicIp=ENABLED}"
  }
}

