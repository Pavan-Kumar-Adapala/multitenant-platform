variable "role_name" {
  description = "Name of the IAM role for Lambda"
  type        = string
}

variable "upload_bucket_arn" {
  description = "ARN of the S3 upload bucket"
  type        = string
}

variable "audit_table_arn" {
  description = "ARN of the DynamoDB audit table"
  type        = string
}

variable "ecs_cluster_arn" {
  description = "ARN of the ECS cluster the Lambda will launch tasks into"
  type        = string
}

variable "ecs_task_def_arn" {
  description = "ARN of the ECS task definition to run"
  type        = string
}

variable "ecs_task_role_arn" {
  description = "ARN of the ECS task IAM role (passed to ECS at launch)"
  type        = string
}

variable "ecs_exec_role_arn" {
  description = "ARN of the ECS task execution IAM role (passed to ECS at launch)"
  type        = string
}

variable "tags" {
  description = "Tags to apply to the IAM role"
  type        = map(string)
  default     = {}
}
