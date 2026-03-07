terraform {
  backend "s3" {
    bucket       = "var.statefile_bucket_name"
    key          = "dev/terraform.tfstate"
    region       = "var.statefile_bucket_region"
    use_lockfile = true
    encrypt      = true
  }
}
