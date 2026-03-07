terraform {
  backend "s3" {
    bucket       = var.statefile_bucket_name
    region       = var.statefile_bucket_region
    key          = "dev/terraform.tfstate"
    use_lockfile = true
    encrypt      = true
  }
}


# terraform {
#   backend "s3" {
#     # bucket and region injected at `terraform init` via -backend-config flags in pipeline.yml
#     # Values come from GitHub secrets: STATEFILE_BUCKET_NAME and STATEFILE_BUCKET_REGION
#     # terraform init -backend-config="bucket=${{ secrets.STATEFILE_BUCKET_NAME }}" -backend-config="region=${{ secrets.STATEFILE_BUCKET_REGION }}"
#     key          = "dev/terraform.tfstate"
#     use_lockfile = true
#     encrypt      = true
#   }
# }
