resource "aws_iam_role" "lambda" {
  name = var.role_name
  tags = var.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "lambda" {
  name = "${var.role_name}-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # ── S3: read uploads + read object tags (org-id validation) ─────────
      {
        Sid    = "S3ReadUploads"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectTagging",
          "s3:HeadObject",
          "s3:ListBucket",
        ]
        Resource = [
          var.upload_bucket_arn,
          "${var.upload_bucket_arn}/*",
        ]
      },

      # ── DynamoDB: write audit records ───────────────────────────────────
      {
        Sid      = "DynamoDBWriteAudit"
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = var.audit_table_arn
      },

      # ── ECS Fargate: launch and describe processor tasks ─────────────────
      {
        Sid    = "ECSRunTask"
        Effect = "Allow"
        Action = ["ecs:RunTask", "ecs:DescribeTasks"]
        Resource = [
          var.ecs_task_def_arn,
          var.ecs_cluster_arn,
        ]
      },

      # ── IAM: pass task + execution roles to ECS (least-privilege) ────────
      {
        Sid    = "ECSPassRoles"
        Effect = "Allow"
        Action = ["iam:PassRole"]
        Resource = [
          var.ecs_task_role_arn,
          var.ecs_exec_role_arn,
        ]
        Condition = {
          StringEquals = {
            "iam:PassedToService" = "ecs-tasks.amazonaws.com"
          }
        }
      },

      # ── CloudWatch Logs ──────────────────────────────────────────────────
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
    ]
  })
}
