variable "table_name" {
  description = "Name of the DynamoDB audit table"
  type        = string
}

variable "tags" {
  description = "Tags to apply to the table"
  type        = map(string)
  default     = {}
}
