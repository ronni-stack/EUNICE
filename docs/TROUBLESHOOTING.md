# EUNICE Enterprise — Troubleshooting Runbook

## Server will not start

1. Check port 8000 is free:
   ```bash
   lsof -i :8000
   ```
2. Verify the virtual environment and dependencies:
   ```bash
   source venv/bin/activate
   python -m pytest tests/test_hardening.py::test_ready_endpoint
   ```
3. Check `data/eunice.log` for startup errors.

## `/ready` reports Ollama unreachable

- Confirm Ollama is running: `curl http://localhost:11434/api/tags`
- Set `EUNICE_OLLAMA_URL` correctly.
- If running in Docker, use `host.docker.internal` or the Ollama container name.

## Users cannot log in

- Check `EUNICE_API_KEY` matches the client.
- Ensure the device header `X-EUNICE-Device-ID` is present for API-key auth.
- For OIDC, verify provider config and that the redirect URI is registered.

## Permission denied / 403

- Verify the user's role has the required permission (`admin:*`, `tool:notes`, etc.).
- Use `/admin/users` and `/admin/users/{id}` to inspect assignments.
- Remember resources are scoped to `org_id`; cross-org access is denied by design.

## Tool calls return "not approved"

- Check `/admin/tools/approvals?org_id=<org>`.
- Use `POST /admin/tools/approvals` to re-enable the tool.

## Audit log is empty

- Confirm `data/audit.log` exists and is writable.
- Audit events are filtered server-side; check query parameters.

## Encryption warnings

- Encryption is enabled only when `EUNICE_MASTER_KEY` is set.
- Changing the master key without a rotation plan will make existing encrypted data unreadable.
- Back up `data/` and the master key together.

## Docker / deployment issues

- Ensure `.env` is present and not committed to version control.
- For air-gapped installs, pre-populate `vendor/` with wheels or the install falls back to online.
- VM bundles require `rsync` and `tar` on the build host.
