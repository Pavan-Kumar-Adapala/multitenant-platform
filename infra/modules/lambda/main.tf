data "archive_file" "this" {
  type        = "zip"
  output_path = "${path.module}/builds/processor.zip"
  source_dir  = var.source_dir
}

resource "aws_lambda_function" "this" {
  function_name    = var.function_name
  role             = var.execution_role_arn
  handler          = var.handler
  runtime          = var.runtime
  filename         = data.archive_file.this.output_path
  source_code_hash = data.archive_file.this.output_base64sha256
  timeout          = var.timeout

  environment {
    variables = var.environment_variables
  }

  tags = var.tags
}
