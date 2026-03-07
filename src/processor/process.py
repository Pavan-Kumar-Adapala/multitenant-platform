"""
Processor — src/processor/process.py
Runs inside ECS Fargate container.
Prototype: logs file name, size, and zip contents.
Replace process_file() with real logic in production.
"""

import os
import sys
import boto3
import zipfile
import logging
import tempfile
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger()

S3_BUCKET  = os.environ["S3_BUCKET"]
S3_KEY     = os.environ["S3_KEY"]
ORG_ID     = os.environ["ORG_ID"]
FILE_SIZE  = int(os.environ.get("FILE_SIZE", 0))
USER_NAME  = os.environ.get("USER_NAME", "")
USER_EMAIL = os.environ.get("USER_EMAIL", "")
TABLE_NAME = os.environ["TABLE_NAME"]

s3 = boto3.client("s3")
db = boto3.resource("dynamodb")


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


def process_file(tmp_path):
    file_name = os.path.basename(S3_KEY)
    size_mb   = FILE_SIZE / (1024 * 1024)

    logger.info("=" * 55)
    logger.info("  PROCESSING REPORT")
    logger.info("=" * 55)
    logger.info(f"  File     : {file_name}")
    logger.info(f"  Size     : {size_mb:.3f} MB ({FILE_SIZE} bytes)")
    logger.info(f"  Org ID   : {ORG_ID}")
    logger.info(f"  Uploaded : {USER_NAME} <{USER_EMAIL}>")
    logger.info("-" * 55)

    with zipfile.ZipFile(tmp_path, "r") as zf:
        entries = zf.infolist()
        logger.info(f"  Files in archive: {len(entries)}")
        logger.info("-" * 55)
        for zi in entries:
            kb = zi.file_size / 1024
            logger.info(f"  {zi.filename:<45} {kb:>8.1f} KB")

    logger.info("=" * 55)
    return len(entries)


def main():
    logger.info(f"Container started | org={ORG_ID} | file={S3_KEY}")

    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = os.path.join(tmpdir, "package.zip")

        try:
            logger.info(f"Downloading s3://{S3_BUCKET}/{S3_KEY}")
            s3.download_file(S3_BUCKET, S3_KEY, local_path)

            file_count = process_file(local_path)

            size_mb = FILE_SIZE / (1024 * 1024)
            summary = (f"Processed {os.path.basename(S3_KEY)} | "
                       f"{size_mb:.2f} MB | {file_count} files")

            write_audit("COMPLETE", "SUCCESS", summary)
            logger.info(f"Done ✅ — {summary}")
            sys.exit(0)

        except Exception as e:
            logger.error(f"Processing failed: {e}", exc_info=True)
            write_audit("FAILED", "FAILED", str(e))
            sys.exit(1)


if __name__ == "__main__":
    main()
