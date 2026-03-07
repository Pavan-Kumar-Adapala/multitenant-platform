# multitenant-platform

## AWS Admin:

one time task:

- Already created a group with permissions:
  - group: multitenant-platform-company-developers

- Admin already created S3 bucket for backend state file

  ```
  bucket = "multitenant-platform-terraform-statefiles"
  region = "us-east-1"
  ```

- In GitHub Repo settings, **Actions secrets and variables** section created the below secrets.

  Repository secrets:
  - STATEFILE_BUCKET_NAME
  - STATEFILE_BUCKET_REGION

Upon the request, admin

- Will create user based on the request:

  Example:
  - user: multitenant-platform-company-pavan
  - Adding user to "multitenant-platform-company-developers" group
  - "created Access keys" to user for creating AWS services using AWS CLI
  - The AWS Security credentials will shared to developer

## Developers / Data scientists (technical people)

To trigger the pipeline, technical person need the information from the AWS Admin/Cloud admin. Contact could admin asking the following details

    Technical person need to make request:

        I am  <name> and <company> <your role> and  <project>. What kind of support he/her need?


    Asking details:

        - AWS Security credentials (Access key ID, Secret access key)
        - AWS Region for resources

Response from Admin:

- Created user (username) and add to the group (multitenant-platform-company-developers) and will provide (Access key ID, Secret access key) also Region.

How the techinal person use the platform (multitenant-platform)?

Inputs need to trigger pipeline

1. zip file path (uploading to this repo or using variables option in github actions)
2. AWS Access key ID
3. AWS Secret access key (2 and 3 are the secrets independent of other users so this pipeline trigger based on the user secrets and file path)

The pipeline will create infra to upload file and validate and process Execution and finally audit store in DynamoDB.
