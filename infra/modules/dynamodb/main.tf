resource "aws_dynamodb_table" "this" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"

  # PK: org_id  — the organisation that uploaded the file
  # SK: event_sk — timestamp#event_type  (written by handler.py and process.py)
  hash_key  = "org_id"
  range_key = "event_sk"

  attribute {
    name = "org_id"
    type = "S"
  }

  attribute {
    name = "event_sk"
    type = "S"
  }

  # Encrypt all data at rest
  server_side_encryption {
    enabled = true
  }

  # Enable point-in-time recovery for auditability
  point_in_time_recovery {
    enabled = true
  }

  tags = var.tags
}
