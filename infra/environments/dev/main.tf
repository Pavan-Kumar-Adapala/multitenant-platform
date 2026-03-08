# ---------- Terraform configuration for the "dev" environment ----------
locals {
  prefix = "${var.project_name}-${var.environment}"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ---------- Default VPC & subnets (used for Fargate task networking) ----------
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# ---------- S3 Upload Bucket ----------
module "s3" {
  source      = "../../modules/s3"
  bucket_name = "${local.prefix}-uploads"
  tags        = local.tags
}

# ---------- DynamoDB Audit Table ----------
module "dynamodb" {
  source     = "../../modules/dynamodb"
  table_name = "${local.prefix}-audit"
  tags       = local.tags
}

# ---------- ECR Repository (stores the processor Docker image) ----------
resource "aws_ecr_repository" "processor" {
  name                 = "${local.prefix}-processor"
  image_tag_mutability = "MUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = local.tags
}

# ------------ CloudWatch Log Group for ECS Fargate tasks ----------------
resource "aws_cloudwatch_log_group" "ecs_processor" {
  name              = "/ecs/${local.prefix}-processor"
  retention_in_days = 14
  tags              = local.tags
}

# ------------ Security Group for ECS Fargate tasks (egress-only) ----------------
resource "aws_security_group" "ecs" {
  name        = "${local.prefix}-ecs-sg"
  description = "Egress-only SG for Fargate processor tasks — no inbound allowed"
  vpc_id      = data.aws_vpc.default.id

  egress {
    description = "Allow outbound to S3, DynamoDB, ECR, CloudWatch"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

# ------------ ECS Fargate Cluster -----------------
resource "aws_ecs_cluster" "this" {
  name = "${local.prefix}-cluster"
  tags = local.tags
}

# ------------ ECS Task Execution Role (ECR pull + CloudWatch logs) -----------------
resource "aws_iam_role" "ecs_execution" {
  name = "${local.prefix}-ecs-execution-role"
  tags = local.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ------------ ECS Task Role (least-privilege: S3 download + DynamoDB write only) -----------------
resource "aws_iam_role" "ecs_task" {
  name = "${local.prefix}-ecs-task-role"
  tags = local.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "ecs_task" {
  name = "${local.prefix}-ecs-task-policy"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3DownloadUploadedFile"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${module.s3.bucket_arn}/uploads/*"
      },
      {
        Sid      = "DynamoDBWriteAudit"
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = module.dynamodb.table_arn
      }
    ]
  })
}

# ------------ ECS Fargate Task Definition -----------------
resource "aws_ecs_task_definition" "processor" {
  family                   = "${local.prefix}-processor"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256" # 0.25 vCPU
  memory                   = "512" # 512 MB
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn
  tags                     = local.tags

  container_definitions = jsonencode([{
    name      = "data-processor"
    image     = "${aws_ecr_repository.processor.repository_url}:latest"
    essential = true

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.ecs_processor.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])

  depends_on = [aws_cloudwatch_log_group.ecs_processor]
}

# ------------ Lambda IAM Role (with permissions to read from S3, write to DynamoDB, and run ECS tasks) -----------------
module "iam" {
  source            = "../../modules/iam"
  role_name         = "${local.prefix}-lambda-role"
  upload_bucket_arn = module.s3.bucket_arn
  audit_table_arn   = module.dynamodb.table_arn
  ecs_cluster_arn   = aws_ecs_cluster.this.arn
  ecs_task_def_arn  = aws_ecs_task_definition.processor.arn
  ecs_task_role_arn = aws_iam_role.ecs_task.arn
  ecs_exec_role_arn = aws_iam_role.ecs_execution.arn
  tags              = local.tags
}

# ------------ Lambda Validator (auto-triggered by S3 events) -----------------
module "lambda" {
  source             = "../../modules/lambda"
  function_name      = "${local.prefix}-validator"
  execution_role_arn = module.iam.lambda_role_arn
  source_dir         = "${path.root}/../../../src/lambda/validator"
  handler            = "handler.handler"
  runtime            = "python3.12"
  timeout            = 60
  tags               = local.tags

  environment_variables = {
    DYNAMODB_TABLE        = module.dynamodb.table_name
    ECS_CLUSTER           = aws_ecs_cluster.this.arn
    ECS_TASK_DEFINITION   = aws_ecs_task_definition.processor.arn
    ECS_SUBNET_ID         = data.aws_subnets.default.ids[0]
    ECS_SECURITY_GROUP_ID = aws_security_group.ecs.id
    CONTAINER_NAME        = "data-processor"
  }
}

# ------------ Allow S3 to invoke Lambda -----------------
resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = module.s3.bucket_arn
}

# ------------ S3 event notification → Lambda (on every .zip upload) -----------------
resource "aws_s3_bucket_notification" "uploads" {
  bucket = module.s3.bucket_id

  lambda_function {
    lambda_function_arn = module.lambda.function_arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
    filter_suffix       = ".zip"
  }

  depends_on = [aws_lambda_permission.allow_s3]
}
