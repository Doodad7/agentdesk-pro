# random suffix for bucket/names (optional)
resource "random_id" "suffix" {
  byte_length = 4
}

########################################
# ECR repository
########################################
resource "aws_ecr_repository" "agentdesk" {
  name = "agentdesk"
  force_delete = true
  image_scanning_configuration {
    scan_on_push = false
  }
  tags = {
    project = "agentdesk"
  }
}

########################################
# Custom VPC (replaces default VPC)
########################################
resource "aws_vpc" "agentdesk_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "agentdesk-vpc"
  }
}

resource "aws_subnet" "agentdesk_subnet" {
  vpc_id                  = aws_vpc.agentdesk_vpc.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "eu-north-1a"

  tags = {
    Name = "agentdesk-subnet"
  }
}

# Add a second subnet in another Availability Zone
resource "aws_subnet" "agentdesk_subnet_b" {
  vpc_id                  = aws_vpc.agentdesk_vpc.id
  cidr_block              = "10.0.2.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "eu-north-1b"

  tags = {
    Name = "agentdesk-subnet-b"
  }
}

# Update your DB subnet group to include both
resource "aws_db_subnet_group" "agentdesk_db_subnet_group" {
  name       = "agentdesk-db-subnet-group-${random_id.suffix.hex}"
  subnet_ids = [
    aws_subnet.agentdesk_subnet.id,
    aws_subnet.agentdesk_subnet_b.id
  ]
  tags = {
    Name    = "agentdesk-db-subnet-group"
    project = "agentdesk"
  }
}

resource "aws_internet_gateway" "agentdesk_igw" {
  vpc_id = aws_vpc.agentdesk_vpc.id

  tags = {
    Name = "agentdesk-igw"
  }
}

resource "aws_route_table" "agentdesk_rt" {
  vpc_id = aws_vpc.agentdesk_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.agentdesk_igw.id
  }

  tags = {
    Name = "agentdesk-rt"
  }
}

resource "aws_route_table_association" "agentdesk_rta" {
  subnet_id      = aws_subnet.agentdesk_subnet.id
  route_table_id = aws_route_table.agentdesk_rt.id
}

########################################
# Security Group for ALB and ECS tasks
# Keep minimal ALB SG (so Terraform will not try to destroy it)
########################################
resource "aws_security_group" "alb_sg" {
  name        = "agentdesk-alb-sg-${random_id.suffix.hex}"
  description = "Allow HTTP"
  vpc_id      = aws_vpc.agentdesk_vpc.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ecs_task_sg" {
  name        = "agentdesk-ecs-sg-${random_id.suffix.hex}"
  description = "Allow traffic from ALB to container"
  vpc_id      = aws_vpc.agentdesk_vpc.id

  # Match the existing live SG: allow ingress *from* ALB security group
  ingress {
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    # security_groups = [aws_security_group.alb_sg.id]
    cidr_blocks = ["0.0.0.0/0"]   # allow public access
  }

  ########################################################################################
  ingress {
  description = "Allow ECS tasks to talk to each other (Qdrant)"
  from_port   = 6333
  to_port     = 6333
  protocol    = "tcp"
  self        = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

########################################
# RDS Postgres (small)
########################################
resource "aws_db_instance" "postgres" {
  identifier          = "agentdesk-postgres-${random_id.suffix.hex}"
  engine              = "postgres"
  instance_class      = "db.t3.micro"   
  allocated_storage   = var.db_allocated_storage
  db_name             = "agentdesk"
  username            = var.db_username
  password            = var.db_password
  skip_final_snapshot = true
  publicly_accessible = true

  db_subnet_group_name = aws_db_subnet_group.agentdesk_db_subnet_group.name
  vpc_security_group_ids = [aws_security_group.postgres_sg.id]
}

########################################
# IAM role for ECS task execution
########################################
data "aws_iam_policy_document" "ecs_task_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_task_role" {
  name = "agentdesk_ecs_task_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_exec_policy" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role" "ecs_task_execution_role" {
  name               = "agentdesk_ecs_task_exec_role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy_attachment" "cw_logs_attach" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"
}

resource "aws_cloudwatch_log_group" "ecs_agentdesk" {
  name              = "/ecs/agentdesk"
  retention_in_days = 7
}

########################################
# ECS cluster
########################################
resource "aws_ecs_cluster" "agentdesk" {
  name = "agentdesk-cluster"
}

##########################
# Application Load Balancer (ALB)
##########################

resource "aws_lb" "alb" {
  name               = "agentdesk-alb-${random_id.suffix.hex}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_sg.id]
  subnets            = [aws_subnet.agentdesk_subnet.id, aws_subnet.agentdesk_subnet_b.id]

  enable_deletion_protection = false

  tags = {
    project = "agentdesk"
  }
}

resource "aws_lb_target_group" "tg" {
  name        = "agentdesk-tg-${random_id.suffix.hex}"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.agentdesk_vpc.id
  target_type = "ip" # for awsvpc Fargate tasks we use IP target type

  health_check {
    path                = "/ping"
    protocol            = "HTTP"
    matcher             = "200-399"
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 5
    interval            = 20
  }

  tags = {
    project = "agentdesk"
  }
}

resource "aws_lb_listener" "listener" {
  load_balancer_arn = aws_lb.alb.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.tg.arn
  }
}

########################################
# ECS Task Definition (Fargate)
########################################
resource "aws_ecs_task_definition" "task" {
  family                   = "agentdesk-task"
  cpu                      = "1024"      
  memory                   = "2048"      
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    ###############################
    # 1) Main FastAPI container
    ###############################
    {
      name  = "agentdesk"
      image = "${aws_ecr_repository.agentdesk.repository_url}:latest"
      essential = true
      cpu       = 512
      memory    = 512

      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "POSTGRES_DB",     value = "agentdesk" },
        { name = "POSTGRES_USER",   value = "agentdesk" },
        { name = "POSTGRES_PASSWORD", value = var.db_password },
        { name = "POSTGRES_HOST",  value = aws_db_instance.postgres.address },

        # Local Qdrant + Redis
        { name = "QDRANT_URL", value = "http://qdrant.agentdesk.local:6333" },
        { name = "REDIS_HOST", value = "127.0.0.1" },
        { name = "REDIS_PORT", value = "6379" }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = "/ecs/agentdesk"
          awslogs-region        = "eu-north-1"
          awslogs-stream-prefix = "ecs"
        }
      }
    },

    ###############################
    # 3) Redis sidecar
    ###############################
    {
      name       = "redis"
      image      = "redis:7"
      essential  = true
      cpu        = 128
      memory     = 256

      portMappings = [
        {
          containerPort = 6379
          hostPort      = 6379
          protocol      = "tcp"
        }
      ]
    }
  ])
}



########################################
# ECS Service (Fargate) - no ALB integration for now
########################################
resource "aws_ecs_service" "service" {
  name            = "agentdesk-service"
  cluster         = aws_ecs_cluster.agentdesk.id
  task_definition = aws_ecs_task_definition.task.arn
  desired_count   = var.ecs_desired_count
  launch_type     = "FARGATE"
  enable_execute_command = true

  network_configuration {
    subnets          = [aws_subnet.agentdesk_subnet.id, aws_subnet.agentdesk_subnet_b.id]
    assign_public_ip = true
    security_groups  = [aws_security_group.ecs_task_sg.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.tg.arn
    container_name   = "agentdesk"
    container_port   = var.container_port
  }

  depends_on = [aws_lb_listener.listener]

  service_registries {
  registry_arn = aws_service_discovery_service.api.arn
  }
}

########################################
# Ensure subnet_b route table association (so public subnets have a route)
resource "aws_route_table_association" "agentdesk_rta_b" {
  subnet_id      = aws_subnet.agentdesk_subnet_b.id
  route_table_id = aws_route_table.agentdesk_rt.id
}

output "alb_dns" {
  value = aws_lb.alb.dns_name
  description = "ALB DNS name to access the service"
}

resource "aws_service_discovery_private_dns_namespace" "agentdesk" {
  name = "agentdesk.local"
  vpc  = aws_vpc.agentdesk_vpc.id
}
