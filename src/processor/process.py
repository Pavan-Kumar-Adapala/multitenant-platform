"""
Processor — src/processor/process.py

Runs inside ECS Fargate container.
Downloads the uploaded zip from S3, logs its contents, writes COMPLETE to DynamoDB.
"""

import os
import sys
import boto3
import zipfile
import logging
import tempfile
from datetime import datetime, timezone
from botocore.exceptions import ClientError

# ── Logger ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger()

def log_section(title):
    logger.info("=" * 60)
    logger.info(f"  {title}")
    logger.info("=" * 60)

def log_kv(key, value):
    logger.info(f"  {key:<25} : {value}")

# ── Environment variables ─────────────────────────────────────────────────────
S3_BUCKET  = os.environ["S3_BUCKET"]
S3_KEY     = os.environ["S3_KEY"]
ORG_ID     = os.environ["ORG_ID"]
FILE_SIZE  = int(os.environ.get("FILE_SIZE", 0))
USER_NAME  = os.environ.get("USER_NAME", "")
USER_EMAIL = os.environ.get("USER_EMAIL", "")
TABLE_NAME = os.environ["TABLE_NAME"]

s3 = boto3.client("s3")
db = boto3.resource("dynamodb")


# ── Audit writer ──────────────────────────────────────────────────────────────

def write_audit(event_type, status, details):
    ts = datetime.now(timezone.utc).isoformat()
    db.Table(TABLE_NAME).put_item(Item={
        "org_id":     ORG_ID,
        "event_sk":   f"{ts}#{event_type}",
        "event_type": event_type,
        "user_name":  USER_NAME,
        "user_email": USER_EMAIL,
        "file_key":   S3_KEY,
        "status":     status,
        "details":    details,
        "timestamp":  ts,
    })
    logger.info(f"[AUDIT] event={event_type} | status={status} | {details}")


# ── Processor ─────────────────────────────────────────────────────────────────

def process_file(tmp_path):
    file_name = os.path.basename(S3_KEY)
    size_mb   = FILE_SIZE / (1024 * 1024)

    log_section("PROCESSING REPORT")
    log_kv("File",          file_name)
    log_kv("S3 key",        S3_KEY)
    log_kv("S3 bucket",     S3_BUCKET)
    log_kv("Size",          f"{size_mb:.3f} MB ({FILE_SIZE} bytes)")
    log_kv("Org ID",        ORG_ID)
    log_kv("Uploaded by",   f"{USER_NAME} <{USER_EMAIL}>" if USER_EMAIL else "(not set)")
    log_kv("Local path",    tmp_path)
    logger.info("")

    logger.info("  Opening zip archive...")
    with zipfile.ZipFile(tmp_path, "r") as zf:
        entries = zf.infolist()
        total_uncompressed = sum(e.file_size for e in entries)
        total_compressed   = sum(e.compress_size for e in entries)

        log_kv("Files in archive",    len(entries))
        log_kv("Uncompressed total",  f"{total_uncompressed / 1024 / 1024:.3f} MB")
        log_kv("Compressed total",    f"{total_compressed / 1024 / 1024:.3f} MB")
        if total_uncompressed > 0:
            ratio = (1 - total_compressed / total_uncompressed) * 100
            log_kv("Compression ratio", f"{ratio:.1f}%")
        logger.info("")
        logger.info("  Archive contents:")
        logger.info(f"  {'#':<5} {'Filename':<45} {'Size (KB)':>10}  {'Compressed':>10}  {'Type'}")
        logger.info("  " + "-" * 80)

        for i, zi in enumerate(entries, 1):
            kb            = zi.file_size / 1024
            compressed_kb = zi.compress_size / 1024
            is_dir        = zi.filename.endswith("/")
            ftype         = "DIR" if is_dir else "FILE"
            logger.info(
                f"  {i:<5} {zi.filename:<45} {kb:>10.1f}  {compressed_kb:>10.1f}  {ftype}"
            )

    logger.info("")
    log_section("PROCESSING COMPLETE")
    log_kv("Total files",   len(entries))
    log_kv("Total size",    f"{size_mb:.3f} MB")
    log_kv("Status",        "SUCCESS")

    return len(entries)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log_section("ECS FARGATE PROCESSOR — START")
    log_kv("S3 Bucket",   S3_BUCKET)
    log_kv("S3 Key",      S3_KEY)
    log_kv("Org ID",      ORG_ID)
    log_kv("File size",   f"{FILE_SIZE / 1024 / 1024:.3f} MB")
    log_kv("User",        f"{USER_NAME} <{USER_EMAIL}>" if USER_EMAIL else "(not set)")
    log_kv("DynamoDB",    TABLE_NAME)
    logger.info("")

    file_name = os.path.basename(S3_KEY)

    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = os.path.join(tmpdir, file_name)

        try:
            # ── Download from S3 ──────────────────────────────────────────
            logger.info(f"  [1/3] Downloading from S3...")
            log_kv("Source",  f"s3://{S3_BUCKET}/{S3_KEY}")
            log_kv("Dest",    local_path)

            s3.download_file(S3_BUCKET, S3_KEY, local_path)

            downloaded_size = os.path.getsize(local_path)
            log_kv("Downloaded", f"{downloaded_size / 1024 / 1024:.3f} MB")
            logger.info(f"  Download complete")
            logger.info("")

            # ── Process the zip ───────────────────────────────────────────
            logger.info(f"  [2/3] Processing zip file...")
            file_count = process_file(local_path)
            logger.info("")

            # ── Write audit record ────────────────────────────────────────
            logger.info(f"  [3/3] Writing audit record to DynamoDB...")
            size_mb = FILE_SIZE / (1024 * 1024)
            summary = f"Processed {file_name} | {size_mb:.2f} MB | {file_count} files"

            write_audit("COMPLETE", "SUCCESS", summary)

            log_section("ECS FARGATE PROCESSOR — DONE")
            log_kv("Status",  "SUCCESS")
            log_kv("Summary", summary)
            sys.exit(0)

        except ClientError as e:
            logger.error(f"  AWS error: {e}")
            write_audit("FAILED", "FAILED", f"AWS error: {e}")
            sys.exit(1)

        except zipfile.BadZipFile as e:
            logger.error(f"  Invalid zip file: {e}")
            write_audit("FAILED", "FAILED", f"Invalid zip: {e}")
            sys.exit(1)

        except Exception as e:
            logger.error(f"  Unexpected error: {e}", exc_info=True)
            write_audit("FAILED", "FAILED", str(e))
            sys.exit(1)


if __name__ == "__main__":
    main()
