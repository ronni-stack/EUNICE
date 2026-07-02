# EUNICE Enterprise

This document describes the enterprise features layered on top of the base EUNICE personal-assistant codebase. Enterprise work lives on the `eunice-enterprise` branch; `main` remains the personal-assistant base.

## Feature overview

| Week | Theme | Key capabilities |
|------|-------|------------------|
| 1–2 | Multi-tenancy & RBAC | Organizations, departments, roles, wildcard permissions, tool/memory/API enforcement |
| 3 | Audit logging | Append-only JSON Lines audit log, event filtering, auditor role |
| 4 | Security testing | RBAC penetration, cross-org isolation, audit integrity tests |
| 5 | OIDC SSO | Corporate identity-provider linking, claim/role mapping |
| 6 | Encryption at rest | AES-256-GCM field encryption for SQLite + ChromaDB, per-org keys |
| 7 | Security hardening | Input sanitization, rate limiting, CORS/CSP, secrets audit, vulnerability scan |
| 8 | Deployment packaging | Docker Compose, VM image builder, air-gapped install, ops endpoints |
| 9 | Admin dashboard | Org/department/user management, tool approvals, model status, audit filters |
| 10 | Documentation | This guide, admin setup, user quick start, troubleshooting runbook |

## Branching strategy

- `main` — personal assistant (single user, no enterprise features).
- `eunice-enterprise` — enterprise superset. Rebase or merge from `main` as needed.

## Security model

- **Identity**: local passphrases + device IDs, plus OIDC-linked identities.
- **Authorization**: roles contain JSON permission lists; wildcard patterns (`admin:*`, `tool:*`) are supported.
- **Isolation**: all memory (SQLite + ChromaDB), facts, documents, reasoning runs, and audit events are scoped to an `org_id`.
- **Encryption**: when `EUNICE_MASTER_KEY` is set, sensitive fields are encrypted with per-org AES-256-GCM keys derived via PBKDF2.
- **Audit**: every tool call, memory access, permission denial, and reasoning step is logged immutably.

## Key endpoints

- `GET /health` — liveness.
- `GET /ready` — readiness probe (SQLite, vector store, Ollama, daemon).
- `GET /metrics` — operational counts (admin only).
- `GET /audit` — audit log viewer (auditor/admin).
- `/admin/*` — org/department/user management, crypto status, secrets audit, tool approvals, model status.

See `ADMIN_SETUP.md` for first-time configuration and `USER_QUICKSTART.md` for end-user guidance.
