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

variable "tags" {
  description = "Tags to apply to the IAM role"
  type        = map(string)
  default     = {}
}
