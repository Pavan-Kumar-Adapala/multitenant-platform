output "upload_bucket_name" {
  description = "S3 bucket where zip files are uploaded"
  value       = module.s3.bucket_id
}

output "processor_function_name" {
  description = "Lambda validator function name"
  value       = module.lambda.function_name
}

output "audit_table_name" {
  description = "DynamoDB table storing execution audit records"
  value       = module.dynamodb.table_name
}

output "ecr_repository_url" {
  description = "ECR repository URL — used by CI to push the processor Docker image"
  value       = aws_ecr_repository.processor.repository_url
}

output "ecs_cluster_name" {
  description = "ECS Fargate cluster name"
  value       = aws_ecs_cluster.this.name
}
