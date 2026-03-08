# Hybrid Backbone Strategy

**Decoupling Storage & Compute for On-Premises Deployments**

---

## The Problem

A Member Organisation may require that their sensitive data never leaves their premises:

- The `.zip` file must stay on their own S3-compatible storage (e.g. MinIO, Ceph)
- The container workload must run on their own servers

The goal is to support this constraint **without rewriting the backbone logic** — the Lambda validator, the processor container, and the audit schema must remain identical in both topologies.

---

## Architecture Overview

```
                ┌──────────────────────────────────────────────────────┐
                │           CLOUD BACKBONE (unchanged)                 │
                │                                                      │
Release ──────► │  GitHub Actions → Terraform → Lambda Validator       │
                │                                    │                 │
                │                        Config: endpoints, creds      │
                └────────────────────────────────────┼─────────────────┘
                                                     │
             ┌───────────────────────────────────────┼──────────────────┐
             │  ON-PREM TENANT ZONE                  │                  │
             │                                       ▼                  │
             │                        S3-compatible store  + Container  │
             │                        (MinIO / Ceph)         host       │
             └──────────────────────────────────────────────────────────┘
```

The cloud backbone — GitHub Actions, Terraform, and the Lambda Validator — remains fully in the cloud and is unchanged. Only the endpoints that Lambda and the processor container talk to are redirected by environment variables.

---

## Strategy — Three Configuration Seams

### Seam 1 — Storage (AWS S3 → S3-compatible)

Both `handler.py` (Lambda) and `process.py` (Fargate) use the standard `boto3` S3 client, driven by `S3_BUCKET` and `S3_KEY` environment variables.

To redirect to an on-premises S3-compatible store, set one additional environment variable:

| Variable              | Cloud (default) | On-premises                      |
| --------------------- | --------------- | -------------------------------- |
| `AWS_ENDPOINT_URL_S3` | _(not set)_     | `https://minio.corp.example.com` |

`boto3` respects `AWS_ENDPOINT_URL_*` natively. **Zero code changes required.**

---

### Seam 2 — Compute (ECS Fargate → on-premises container host)

`trigger_ecs()` in `handler.py` wraps a single `ecs_client.run_task()` call. For on-premises deployments, replace this with a **Relay Agent** pattern:

1. Lambda writes a **task manifest** (JSON payload containing `S3_BUCKET`, `S3_KEY`, `ORG_ID`, etc.) to an SQS queue or a REST endpoint exposed by the on-prem network
2. An on-premises **Relay Agent** (~80 lines of Python) polls the queue and runs the processor container locally via Docker or Kubernetes
3. The container reads from the on-premises S3-compatible store and writes audit records to the on-premises DynamoDB-compatible store

**What changes:** one new Relay Agent component is added on-premises.  
**What does not change:** `handler.py`, `process.py`, and all Terraform modules.

---

### Seam 3 — Audit Database (AWS DynamoDB → DynamoDB-compatible)

`process.py` writes audit records via `boto3.resource("dynamodb")`.

To redirect writes to an on-premises store, set one additional environment variable:

| Variable                    | Cloud (default) | On-premises                             |
| --------------------------- | --------------- | --------------------------------------- |
| `AWS_ENDPOINT_URL_DYNAMODB` | _(not set)_     | `https://dynamo-local.corp.example.com` |

Compatible targets include DynamoDB Local, ScyllaDB Alternator, or any DynamoDB-compatible API. **Zero code changes required.**

---

## Side-by-Side Comparison

| Layer               | Cloud (default) | On-premises                       |
| ------------------- | --------------- | --------------------------------- |
| Storage             | AWS S3          | MinIO / any S3-compatible         |
| Compute             | ECS Fargate     | Relay Agent → Docker / Kubernetes |
| Audit DB            | AWS DynamoDB    | DynamoDB Local / ScyllaDB         |
| Code changes needed | —               | **None**                          |
| Infra changes       | —               | Endpoint env vars + Relay Agent   |

---

## Terraform Support

Each environment directory (`infra/environments/<env>/`) controls the seam variables through `terraform.tfvars`. A new `on_prem = true` flag could conditionally:

- Skip creating AWS ECS, S3, and DynamoDB resources
- Inject the three `AWS_ENDPOINT_URL_*` variables as Lambda and ECS environment variable overrides

This means the same Terraform codebase can target either topology by changing a single variable.

---

## Key Principle

The validation rules, audit schema, and container interface are **identical** in both topologies. The only differences are the transport endpoints, and all of those differences are expressed as **configuration, not code**.

This design satisfies the data-residency requirement of Member Organisations without forking the codebase or maintaining a separate version of the platform.
