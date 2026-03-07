variable "function_name" {
  description = "Name of the Lambda function"
  type        = string
}

variable "execution_role_arn" {
  description = "ARN of the IAM role the Lambda assumes"
  type        = string
}

variable "source_dir" {
  description = "Local directory containing Lambda source code"
  type        = string
}

variable "handler" {
  description = "Lambda handler in filename.function format"
  type        = string
  default     = "processor.handler"
}

variable "runtime" {
  description = "Lambda runtime"
  type        = string
  default     = "python3.12"
}

variable "timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 300
}

variable "environment_variables" {
  description = "Environment variables passed to the Lambda"
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Tags to apply to the Lambda function"
  type        = map(string)
  default     = {}
}
