# The value of this variable set in GitHub Actions secrets, and read in pipeline using the env context TF_VAR_statefile_bucket_name: ${{ secrets.STATEFILE_BUCKET_NAME }}
# it is used in the state.tf file to configure the S3 backend for Terraform state files.
variable "statefile_bucket_name" {
  description = "Name of the S3 bucket to store Terraform state files"
  type        = string

}
# The value of this variable set in GitHub Actions secrets, and read in pipeline using the env context TF_VAR_statefile_bucket_region: ${{ secrets.STATEFILE_BUCKET_REGION }}
# it is used in the state.tf file to configure the S3 backend for Terraform state files.
variable "statefile_bucket_region" {
  description = "AWS region where the S3 bucket for Terraform state files is located"
  type        = string
}
