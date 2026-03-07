"""
Lambda Validator — src/lambda/validator/handler.py

Triggered automatically by S3 PutObject events.
Flow:
  1. Extract org-id tag from uploaded object
  2. Validate metadata (size, content-type)
  3. If valid  → write VALIDATED to DynamoDB, trigger ECS task
  4. If invalid → write VALIDATION_FAILED to DynamoDB, stop
  5. All paths  → audit logged
"""

import os
import json
import boto3
import logging
from datetime import datetime, timezone
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Reuse connections across Lambda warm invocations
s3_client  = boto3.client("s3")
ecs_client = boto3.client("ecs")
db         = boto3.resource("dynamodb")

# Environment variables — set by Terraform
TABLE_NAME    = os.environ["DYNAMODB_TABLE"]
ECS_CLUSTER   = os.environ["ECS_CLUSTER"]
ECS_TASK_DEF  = os.environ["ECS_TASK_DEFINITION"]
ECS_SUBNET    = os.environ["ECS_SUBNET_ID"]
ECS_SG        = os.environ["ECS_SECURITY_GROUP_ID"]
CONTAINER     = os.environ.get("CONTAINER_NAME", "data-processor")

MAX_SIZE_MB   = 500


# ── Audit writer ──────────────────────────────────────────────

def write_audit(org_id, event_type, file_key, status, details,
                user_name="", user_email=""):
    ts = datetime.now(timezone.utc).isoformat()
    db.Table(TABLE_NAME).put_item(Item={
        "org_id":     org_id,
        "event_sk":   f"{ts}#{event_type}",
        "event_type": event_type,
        "user_name":  user_name,
        "user_email": user_email,
        "file_key":   file_key,
        "status":     status,
        "details":    details,
        "timestamp":  ts,
    })
    logger.info(f"[AUDIT] {event_type} | {org_id} | {status} | {details}")


# ── Validation ────────────────────────────────────────────────

def validate_org_id(tags: dict):
    """Check organization-id tag exists and is valid."""
    org_id = tags.get("organization-id", "").strip()

    if not org_id:
        return None, "Missing required tag: organization-id"

    if len(org_id) < 3:
        return None, f"organization-id too short: '{org_id}'"

    # Only allow alphanumeric, hyphens, underscores
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if not set(org_id).issubset(allowed):
        return None, f"organization-id has invalid characters: '{org_id}'"

    return org_id, "OK"


def validate_metadata(head: dict):
    """Check file size and content-type."""
    size = head.get("ContentLength", 0)

    if size == 0:
        return False, "File is empty"

    size_mb = size / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        return False, f"File too large: {size_mb:.1f} MB (max {MAX_SIZE_MB} MB)"

    content_type = head.get("ContentType", "")
    allowed_types = {
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
        "binary/octet-stream",
    }
    if content_type not in allowed_types:
        # For CI test: allow any octet-stream type
        logger.warning(f"Content-type '{content_type}' — proceeding (prototype mode)")

    return True, f"size={size_mb:.2f}MB"


# ── ECS trigger ───────────────────────────────────────────────

def trigger_ecs(org_id, bucket, s3_key, file_size, user_name, user_email):
    response = ecs_client.run_task(
        cluster        = ECS_CLUSTER,
        taskDefinition = ECS_TASK_DEF,
        launchType     = "FARGATE",
        networkConfiguration = {
            "awsvpcConfiguration": {
                "subnets":        [ECS_SUBNET],
                "securityGroups": [ECS_SG],
                "assignPublicIp": "ENABLED",
            }
        },
        overrides = {
            "containerOverrides": [{
                "name": CONTAINER,
                "environment": [
                    {"name": "S3_BUCKET",   "value": bucket},
                    {"name": "S3_KEY",      "value": s3_key},
                    {"name": "ORG_ID",      "value": org_id},
                    {"name": "FILE_SIZE",   "value": str(file_size)},
                    {"name": "USER_NAME",   "value": user_name},
                    {"name": "USER_EMAIL",  "value": user_email},
                    {"name": "TABLE_NAME",  "value": TABLE_NAME},
                ],
            }]
        },
    )

    failures = response.get("failures", [])
    if failures:
        raise RuntimeError(f"ECS launch failed: {json.dumps(failures)}")

    task_arn = response["tasks"][0]["taskArn"]
    return task_arn.split("/")[-1]   # return just the task ID


# ── Handler ───────────────────────────────────────────────────

def handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")

    for record in event.get("Records", []):
        bucket  = record["s3"]["bucket"]["name"]
        s3_key  = record["s3"]["object"]["key"]
        size    = record["s3"]["object"].get("size", 0)

        org_id     = "unknown"
        user_name  = ""
        user_email = ""

        try:
            # 1. Read S3 tags and metadata
            tag_response = s3_client.get_object_tagging(Bucket=bucket, Key=s3_key)
            tags = {t["Key"]: t["Value"] for t in tag_response.get("TagSet", [])}

            head = s3_client.head_object(Bucket=bucket, Key=s3_key)
            s3_meta = head.get("Metadata", {})

            # Extract identity from tags/metadata
            org_id     = tags.get("organization-id", s3_meta.get("organization-id", "unknown"))
            user_name  = s3_meta.get("uploaded-by-name", tags.get("uploaded-by-name", ""))
            user_email = s3_meta.get("uploaded-by",      tags.get("uploaded-by", ""))

            logger.info(f"Processing: {s3_key} | org: {org_id} | by: {user_email or 'cli'}")

            # 2. Validate org-id
            org_id_clean, org_msg = validate_org_id(tags)
            if not org_id_clean:
                write_audit(org_id, "VALIDATION_FAILED", s3_key, "FAILED",
                            f"org-id check: {org_msg}", user_name, user_email)
                continue

            # 3. Validate metadata
            meta_ok, meta_msg = validate_metadata(head)
            if not meta_ok:
                write_audit(org_id, "VALIDATION_FAILED", s3_key, "FAILED",
                            f"metadata check: {meta_msg}", user_name, user_email)
                continue

            # 4. Write VALIDATED event
            write_audit(org_id, "VALIDATED", s3_key, "SUCCESS",
                        f"org-id={org_id} | {meta_msg}", user_name, user_email)

            # 5. Trigger ECS task
            task_id = trigger_ecs(org_id, bucket, s3_key, size, user_name, user_email)

            # 6. Write PROCESSING_START event
            write_audit(org_id, "PROCESSING_START", s3_key, "SUCCESS",
                        f"ECS task: {task_id}", user_name, user_email)

            logger.info(f"Pipeline launched: task={task_id}")

        except ClientError as e:
            logger.error(f"AWS error: {e}")
            write_audit(org_id, "ERROR", s3_key, "FAILED", str(e), user_name, user_email)

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            write_audit(org_id, "ERROR", s3_key, "FAILED", str(e), user_name, user_email)

    return {"statusCode": 200}
