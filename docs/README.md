# Deployment & Testing Guide

Created a pipeline, this pipeline will provide platform with necessary resources: (no changes required)

1. Provision all AWS infrastructure via Terraform
2. Build and push the processor Docker image to ECR
3. Upload your zip to S3 (tagged with your GitHub org as `organization-id`)
4. S3 event auto-triggers Lambda validator
5. Lambda validates and launches an ECS Fargate task
6. Audit records written to DynamoDB at every step

## Depolyment

### Inside AWS

Login into AWS console with admin user credentials:

#### One time tasks at the beginning of the Project

- Create S3 bucket for Terraform state: `multitenant-platform-terraform-statefiles` in `us-east-1`

  Note: if you want to use differnet names than update in GitHub Repository Secrets (Settings → Secrets and variables → Actions)

- In IAM Create group with name `multitenant-platform-company-developers` and below permissions

Minimum IAM permissions for the group

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:*"],
      "Resource": "arn:aws:s3:::multitenant-platform-*" // if the Terraform statefile bucket name format different, than include in resource
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
    {
      "Effect": "Allow",
      "Action": ["ecs:*"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["ecr:*"],
      "Resource": "*"
    }
    {
      "Effect": "Allow",
      "Action": [
        "ec2:CreateSecurityGroup",
        "ec2:DeleteSecurityGroup",
        "ec2:AuthorizeSecurityGroupEgress",
        "ec2:RevokeSecurityGroupEgress",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSecurityGroupRules"
      ],
      "Resource": "*"
    }
  ]
}
```

Create Service Linked Role for ECS (AWSServiceRoleForECS):

    Go to IAM → Roles → Create role

    Select AWS service

    Under "Use case" search for Elastic Container Service

    Select Elastic Container Service (not ECS Task)

    Click Next through the rest and Create role

or

aws iam create-service-linked-role --aws-service-name ecs.amazonaws.com

#### Repetitive task of cloud admin (New employ want to use the platform and will send request to cloud admin)

- Create a user and add the user to the group (multitenant-platform-company-developers)
- Create access keys (Access key ID, Secret access key) to the user
- Send user details, access keys file, aws default region to the user

  From your AWS Admin, user get:
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `AWS_DEFAULT_REGION`
  - `VPC_ID`
  - `SUBNET_ID`

### Inside GitHub

Assume you are working in orgnization as a developer and you want to use this platform to process the zip file. You need to send the request to cloud admin. The admin will share the below key details:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION`
- `VPC_ID`
- `SUBNET_ID`

As a developer you need Github repo access to add GitHub Repository Secrets

Repository (Settings → Secrets and variables → Actions):

| Secret                  | Value      |
| ----------------------- | ---------- |
| `AWS_ACCESS_KEY_ID`     | From admin |
| `AWS_SECRET_ACCESS_KEY` | From admin |
| `AWS_DEFAULT_REGION`    | From admin |
| `VPC_ID`                | From admin |
| `SUBNET_ID`             | From admin |

Note:
It is not a best appraoch. I will find better options in future.

---

## Testing

After updating GitHub Repository Secrets using the information from the cloud admin, you can test the platform by following below steps;

### Step 1 — Prepare your zip file / Use available zip file

Any `.zip` file works. For testing, create a simple one:

```bash
echo "hello" > sample.txt
zip mydata.zip sample.txt
```

### Step 2 — Create a GitHub Release

1. Go to your repo → **Releases** → **Draft a new release**
2. Enter a tag (e.g. `v1.0.0`) and a title
3. **Drag and drop your `.zip` file** into the assets area
4. Click **Publish release**

### Step 3 — Monitor the workflow

Go to **Actions** → **Multitenant Platform Pipeline** to watch progress.

The pipeline runs these steps automatically:

1. Validates exactly one `.zip` is attached
2. Provisions all AWS infrastructure via Terraform
3. Builds and pushes Docker image to ECR
4. Uploads zip to S3 with `organization-id` tag
5. S3 event auto-triggers Lambda validator (no manual invoke)
6. Lambda validates and launches ECS Fargate task
7. Fargate container processes the zip and logs contents
8. All steps audited in DynamoDB

---

## Verify the Audit Trail

After the pipeline completes, query DynamoDB:

```bash
aws dynamodb query \
  --table-name multitenant-platform-dev-audit \
  --key-condition-expression "org_id = :oid" \
  --expression-attribute-values '{":oid":{"S":"<your-github-org>"}}' \
  --output table \
  --query 'Items[*].{Event:event_type.S,Status:status.S,Details:details.S}'
```

Expected audit trail:

+--------------------------------------------------------+-------------------+-----------------------------------------------------+----------+
| Details | Event | SK | Status |
+--------------------------------------------------------+-------------------+-----------------------------------------------------+----------+
| org-id=Pavan-Kumar-Adapala | size=123.45MB | VALIDATED | 2026-03-08T03:40:56.984963+00:00#VALIDATED | SUCCESS |
| ECS task: 358061bb19394a74b77535fe4acb2713 | PROCESSING_START | 2026-03-08T03:40:58.277635+00:00#PROCESSING_START | SUCCESS |
| Processed preprocessed_data.zip | 123.45 MB | 1 files | COMPLETE | 2026-03-08T03:41:19.040387+00:00#COMPLETE | SUCCESS |
+--------------------------------------------------------+-------------------+-----------------------------------------------------+----------+

View ECS logs in CloudWatch:

```
Log group: /ecs/multitenant-platform-dev-processor
```

---

## Teardown

Go to Actions in GitHub and select **Destroy Infrastructure** workflow (destroy.yml). Run the workflow manually by clicking **Run Workflow**
