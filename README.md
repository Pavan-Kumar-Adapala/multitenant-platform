# multitenant-platform

## Overview

A shared platform where technical person submit zip files for processing. Each run provisions infra, uploads the file, processes it via Lambda, and audits results in DynamoDB.

## AWS Admin (one-time setup)

- Created group `multitenant-platform-company-developers` (add least-privilege permissions — see below)
- Created S3 bucket for Terraform state: `multitenant-platform-terraform-statefiles` in `us-east-1`
- Added GitHub repo secrets: `STATEFILE_BUCKET_NAME`, `STATEFILE_BUCKET_REGION`

**Minimum IAM permissions for the group**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:*"],
      "Resource": "arn:aws:s3:::multitenant-platform-*"
    },
    {
      "Effect": "Allow",
      "Action": ["dynamodb:*"],
      "Resource": "arn:aws:dynamodb:*:*:table/multitenant-platform-*"
    },
    {
      "Effect": "Allow",
      "Action": ["lambda:*"],
      "Resource": "arn:aws:lambda:*:*:function:multitenant-platform-*"
    },
    {
      "Effect": "Allow",
      "Action": ["iam:*"],
      "Resource": "arn:aws:iam::*:role/multitenant-platform-*"
    },
    {
      "Effect": "Allow",
      "Action": ["logs:*"],
      "Resource": "arn:aws:logs:*:*:*"
    },
    { "Effect": "Allow", "Action": ["ecs:*"], "Resource": "*" },
    { "Effect": "Allow", "Action": ["ecr:*"], "Resource": "*" }
  ]
}
```

- In GitHub Repo settings, **Actions secrets and variables** section created the below secrets.

  Repository secrets:
  - STATEFILE_BUCKET_NAME
  - STATEFILE_BUCKET_REGION

Upon the request, admin

- Will create user based on the request

  Example:
  - user: multitenant-platform-company-pavan
  - Adding user to "multitenant-platform-company-developers" group
  - "created Access keys" to user for creating AWS services using AWS CLI
  - The AWS Security credentials will shared to developer

## Developers / Data scientists (how to run)

### Prerequisites

You need from the AWS Admin (Contact could admin asking the following details):

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION`

  Technical person need to make request:

        I am  <name> and <company> <your role> and  <project>. What kind of support he/her need?

### Run the pipeline

1. Go to **Actions** → **Multitenant Platform Pipeline** → **Run workflow**
2. Enter the path to your zip file in the repo (e.g. `data/mymodel.zip`)
3. Click **Run workflow**

The pipeline will:

1. Provision infrastructure (S3 bucket, Lambda, DynamoDB) via Terraform
2. Upload your zip file to S3
3. Trigger the Lambda to validate and process the file
4. Store the audit record in DynamoDB

Response from Admin:

- Created user (username) and add to the group (multitenant-platform-company-developers) and will provide (Access key ID, Secret access key) also Region.

How the techinal person use the platform (multitenant-platform)?

Inputs need to trigger pipeline

1. zip file path (uploading to this repo or using variables option in github actions)
2. AWS Access key ID
3. AWS Secret access key (2 and 3 are the secrets independent of other users so this pipeline trigger based on the user secrets and file path)

The pipeline will create infra to upload file and validate and process Execution and finally audit store in DynamoDB.
