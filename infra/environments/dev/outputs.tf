output "upload_bucket_name" {
  description = "S3 bucket where zip files are uploaded"
  value       = module.s3.bucket_id
}

output "processor_function_name" {
  description = "Lambda function name used for processing"
  value       = module.lambda.function_name
}

output "audit_table_name" {
  description = "DynamoDB table storing execution audit records"
  value       = module.dynamodb.table_name
}
