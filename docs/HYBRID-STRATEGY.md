# Hybrid Backbone Strategy

### Decoupling Storage & Compute for On-Premises Deployments

---

## The Problem

A Member Organisation may require that their sensitive data **never leaves their premises**:

- the `.zip` file must stay on their own S3-compatible storage (e.g. MinIO, Ceph)
- the container workload must run on their own servers

The goal: support this **without rewriting the backbone logic**.

---

## Architecture Overview

```
                ┌────────────────────────────────────────────────────────┐
                │              CLOUD BACKBONE (unchanged)                │
                │                                                        │
Release ──────► │  GitHub Actions → Terraform → Lambda Validator         │
                │                                      │                 │
                │                          Config: endpoints, creds      │
                └──────────────────────────────────────┼─────────────────┘
                                                       │
             ┌─────────────────────────────────────────┼──────────────────┐
             │  ON-PREM TENANT ZONE                    │                  │
             │                                         ▼                  │
             │                          S3-compatible store  +  Container │
             │                          (MinIO / Ceph)          host      │
             └──────────────────────────────────────────────────────────-─┘
```

---

## Strategy — Three Configuration Seams

### Seam 1 — Storage (S3 → S3-compatible)

Both `handler.py` (Lambda) and `process.py` (Fargate) use the standard `boto3` S3 client,
driven by `S3_BUCKET` and `S3_KEY` environment variables.

To redirect to an on-prem S3-compatible store, set one extra environment variable:

| Variable              | Cloud       | On-prem                          |
| --------------------- | ----------- | -------------------------------- |
| `AWS_ENDPOINT_URL_S3` | _(not set)_ | `https://minio.corp.example.com` |

`boto3` respects `AWS_ENDPOINT_URL_*` natively. **Zero code changes.**

### Seam 2 — Compute (ECS Fargate → on-prem container host)

`trigger_ecs()` in `handler.py` wraps a single `ecs_client.run_task()` call.
Replace it with a **Relay Agent** pattern:

1. Lambda writes a **task manifest** (JSON) to an SQS queue or REST endpoint
2. On-prem **Relay Agent** (≈ 80 lines of Python) polls the queue and runs the container
   locally via Docker / Kubernetes API
3. Container reads from on-prem S3-compatible storage, writes audit to on-prem DynamoDB

One new component; no changes to `handler.py`, `process.py`, or any Terraform modules.

### Seam 3 — Audit (DynamoDB → DynamoDB-compatible)

`process.py` writes audit records via `boto3.resource("dynamodb")`.

Set one environment variable to redirect writes:

| Variable                    | Cloud       | On-prem                                 |
| --------------------------- | ----------- | --------------------------------------- |
| `AWS_ENDPOINT_URL_DYNAMODB` | _(not set)_ | `https://dynamo-local.corp.example.com` |

Compatible targets: DynamoDB Local, ScyllaDB Alternator, or any DynamoDB-compatible store.
**Zero code changes.**

---

## Terraform Support

Each environment directory (`infra/environments/<env>/`) controls the seam variables
through `terraform.tfvars`. A new `on_prem = true` flag could conditionally:

- Skip creating AWS ECS / S3 / DynamoDB resources
- Set the three endpoint override variables as Lambda / ECS env vars instead

---

## Summary

| Layer                | Cloud (current) | On-prem                         |
| -------------------- | --------------- | ------------------------------- |
| Storage              | AWS S3          | MinIO / any S3-compatible       |
| Compute              | ECS Fargate     | Relay Agent → Docker / k8s      |
| Audit DB             | AWS DynamoDB    | DynamoDB Local / ScyllaDB       |
| Code changes needed  | —               | **None**                        |
| Infra changes needed | —               | Endpoint env vars + Relay Agent |

The validation rules, audit schema, and container interface are **identical** in both
topologies. Only the transport endpoints differ, and all differences are expressed as
**configuration, not code**.
