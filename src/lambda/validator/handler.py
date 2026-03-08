"""
Lambda Validator — src/lambda/validator/handler.py

Triggered automatically by S3 PutObject events.
Flow:
  1. Extract org-id tag from uploaded object
  2. Validate metadata (size, content-type)
  3. If valid   -> write VALIDATED to DynamoDB, trigger ECS Fargate task
  4. If invalid -> write VALIDATION_FAILED to DynamoDB, stop
  5. All paths  -> audit logged
"""

import os
import json
import boto3
import logging
from datetime import datetime, timezone
from botocore.exceptions import ClientError

# --------------------- Logger setup --------------------------
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def log_section(title):
    logger.info("=" * 60)
    logger.info(f"  {title}")
    logger.info("=" * 60)

def log_kv(key, value):
    logger.info(f"  {key:<25} : {value}")

# --------------------- AWS clients (reused across warm invocations) ---------------------------
s3_client  = boto3.client("s3")
ecs_client = boto3.client("ecs")
db         = boto3.resource("dynamodb")

# --------------------- Environment variables (set by Terraform) ---------------------------
TABLE_NAME   = os.environ["DYNAMODB_TABLE"]
ECS_CLUSTER  = os.environ["ECS_CLUSTER"]
ECS_TASK_DEF = os.environ["ECS_TASK_DEFINITION"]
ECS_SUBNET   = os.environ["ECS_SUBNET_ID"]
ECS_SG       = os.environ["ECS_SECURITY_GROUP_ID"]
CONTAINER    = os.environ.get("CONTAINER_NAME", "data-processor")

MAX_SIZE_MB  = 500


# --------------------- Audit writer --------------------------

def write_audit(org_id, event_type, file_key, status, details,
                user_name="", user_email=""):
    ts = datetime.now(timezone.utc).isoformat()
    item = {
        "org_id":     org_id,
        "event_sk":   f"{ts}#{event_type}",
        "event_type": event_type,
        "user_name":  user_name,
        "user_email": user_email,
        "file_key":   file_key,
        "status":     status,
        "details":    details,
        "timestamp":  ts,
    }
    db.Table(TABLE_NAME).put_item(Item=item)
    logger.info(f"[AUDIT] event={event_type} | org={org_id} | status={status} | {details}")


# --------------------- Validation helpers --------------------------

def validate_org_id(tags: dict):
    org_id = tags.get("organization-id", "").strip()
    logger.info(f"  Validating org-id: '{org_id}'")

    if not org_id:
        return None, "Missing required tag: organization-id"
    if len(org_id) < 3:
        return None, f"organization-id too short: '{org_id}'"

    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if not set(org_id).issubset(allowed):
        return None, f"organization-id has invalid characters: '{org_id}'"

    logger.info(f"  org-id valid: '{org_id}'")
    return org_id, "OK"


def validate_metadata(head: dict):
    size = head.get("ContentLength", 0)
    content_type = head.get("ContentType", "unknown")
    size_mb = size / (1024 * 1024)

    logger.info(f"  File size        : {size_mb:.3f} MB ({size} bytes)")
    logger.info(f"  Content-Type     : {content_type}")

    if size == 0:
        return False, "File is empty"
    if size_mb > MAX_SIZE_MB:
        return False, f"File too large: {size_mb:.1f} MB (max {MAX_SIZE_MB} MB)"

    allowed_types = {
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
        "binary/octet-stream",
    }
    if content_type not in allowed_types:
        logger.warning(f"  Content-type '{content_type}' not in allowed list — proceeding")

    logger.info(f"  Metadata valid: size={size_mb:.2f}MB")
    return True, f"size={size_mb:.2f}MB"


# --------------------- ECS trigger --------------------------

def trigger_ecs(org_id, bucket, s3_key, file_size, user_name, user_email):
    logger.info("  Launching ECS Fargate task...")
    log_kv("Cluster",        ECS_CLUSTER)
    log_kv("Task definition", ECS_TASK_DEF)
    log_kv("Subnet",          ECS_SUBNET)
    log_kv("Security group",  ECS_SG)
    log_kv("Container",       CONTAINER)

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
    task_id  = task_arn.split("/")[-1]

    logger.info(f"  ECS task launched successfully")
    log_kv("Task ARN", task_arn)
    log_kv("Task ID",  task_id)

    return task_id


# --------------------- Main handler --------------------------

def handler(event, context):
    log_section("LAMBDA VALIDATOR — START")
    logger.info(f"  Function     : {context.function_name}")
    logger.info(f"  Request ID   : {context.aws_request_id}")
    logger.info(f"  Records      : {len(event.get('Records', []))}")
    logger.info(f"  Raw event    : {json.dumps(event)}")

    for idx, record in enumerate(event.get("Records", [])):
        bucket = record["s3"]["bucket"]["name"]
        s3_key = record["s3"]["object"]["key"]
        size   = record["s3"]["object"].get("size", 0)

        org_id     = "unknown"
        user_name  = ""
        user_email = ""

        log_section(f"RECORD {idx + 1} — PROCESSING")
        log_kv("Bucket",   bucket)
        log_kv("S3 key",   s3_key)
        log_kv("Size",     f"{size} bytes ({size / 1024 / 1024:.3f} MB)")

        try:
            # --------------------- 1. Read S3 tags and object metadata ------------------------------
            logger.info("")
            logger.info("  [1/4] Reading S3 tags and metadata...")

            tag_response = s3_client.get_object_tagging(Bucket=bucket, Key=s3_key)
            tags = {t["Key"]: t["Value"] for t in tag_response.get("TagSet", [])}

            head    = s3_client.head_object(Bucket=bucket, Key=s3_key)
            s3_meta = head.get("Metadata", {})

            org_id     = tags.get("organization-id", s3_meta.get("organization-id", "unknown"))
            user_name  = s3_meta.get("uploaded-by-name", tags.get("uploaded-by-name", ""))
            user_email = s3_meta.get("uploaded-by",      tags.get("uploaded-by", ""))

            logger.info(f"  Tags     : {json.dumps(tags)}")
            logger.info(f"  Metadata : {json.dumps(s3_meta)}")
            log_kv("org_id",     org_id)
            log_kv("user_name",  user_name or "(not set)")
            log_kv("user_email", user_email or "(not set)")

            # --------------------- 2. Validate org-id tag (required) ------------------------------
            logger.info("")
            logger.info("  [2/4] Validating organization-id tag...")

            org_id_clean, org_msg = validate_org_id(tags)
            if not org_id_clean:
                logger.warning(f"  VALIDATION FAILED: {org_msg}")
                write_audit(org_id, "VALIDATION_FAILED", s3_key, "FAILED",
                            f"org-id check: {org_msg}", user_name, user_email)
                continue

            # --------------------- 3. Validate file metadata (size, content-type) ------------------------------
            logger.info("")
            logger.info("  [3/4] Validating file metadata...")

            meta_ok, meta_msg = validate_metadata(head)
            if not meta_ok:
                logger.warning(f"  VALIDATION FAILED: {meta_msg}")
                write_audit(org_id, "VALIDATION_FAILED", s3_key, "FAILED",
                            f"metadata check: {meta_msg}", user_name, user_email)
                continue

            # --------------------- 4. Write VALIDATED + launch ECS task ------------------------------
            logger.info("")
            logger.info("  [4/4] Validation passed — writing audit + launching ECS...")

            write_audit(org_id, "VALIDATED", s3_key, "SUCCESS",
                        f"org-id={org_id} | {meta_msg}", user_name, user_email)

            task_id = trigger_ecs(org_id, bucket, s3_key, size, user_name, user_email)

            write_audit(org_id, "PROCESSING_START", s3_key, "SUCCESS",
                        f"ECS Fargate task: {task_id}", user_name, user_email)

            log_section("LAMBDA VALIDATOR — COMPLETE")
            logger.info(f"  Status  : SUCCESS")
            logger.info(f"  Org ID  : {org_id}")
            logger.info(f"  File    : {s3_key}")
            logger.info(f"  Task ID : {task_id}")

        except ClientError as e:
            logger.error(f"  AWS ClientError: {e}")
            write_audit(org_id, "ERROR", s3_key, "FAILED", str(e), user_name, user_email)

        except Exception as e:
            logger.error(f"  Unexpected error: {e}", exc_info=True)
            write_audit(org_id, "ERROR", s3_key, "FAILED", str(e), user_name, user_email)

    return {"statusCode": 200}
