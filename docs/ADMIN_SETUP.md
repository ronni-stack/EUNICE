# EUNICE Enterprise — Admin Setup Guide

## 1. Installation

### Local development

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Docker Compose

```bash
cp .env.example .env   # edit with your secrets
EUNICE_OLLAMA_URL=http://host.docker.internal:11434 docker compose up --build
```

### VM / air-gapped

```bash
# Online machine: build the bundle
./scripts/build_vm_image.sh

# Transfer dist/eunice-enterprise-vm-*.tar.gz to the target
# On the target (air-gapped):
./scripts/airgapped_install.sh /path/to/eunice-enterprise
systemctl start eunice-enterprise
```

## 2. Required environment variables

Create a `.env` file or export the variables before starting the server:

```bash
# Security — change all defaults in production
EUNICE_MASTER_KEY="<32+ byte random string>"
EUNICE_API_KEY="<random api key>"
EUNICE_JWT_SECRET="<random jwt signing secret>"

# Inference
EUNICE_OLLAMA_URL="http://localhost:11434"
# EUNICE_MODEL=llama3.2:3b

# CORS (production)
EUNICE_ALLOWED_ORIGINS="https://chat.company.com"
```

Check status with:

```bash
curl -H "Authorization: Bearer $EUNICE_API_KEY" \
     -H "X-EUNICE-Device-ID: admin-device" \
     http://localhost:8000/admin/secrets/audit
```

## 3. Create the first admin

1. Create an identity:

```bash
curl -X POST http://localhost:8000/identity/create \
  -H "Authorization: Bearer $EUNICE_API_KEY" \
  -d '{"display_name":"Admin","passphrase":"...","device_id":"admin-device"}'
```

2. Assign the admin role:

```bash
python - <<'PY'
from memory.sqlite_store import SQLiteStore
s = SQLiteStore()
s.ensure_user("<identity_id>")
s.assign_user_role("<identity_id>", role_id="admin")
PY
```

## 4. Organizations, departments, and users

Use the admin endpoints:

- `POST /admin/orgs` — create organization.
- `POST /admin/orgs/{org_id}/departments` — create department.
- `POST /admin/users` — create user with org/department/role.
- `PATCH /admin/users/{user_id}` — reassign org/department/role.

## 5. Tool approvals

List tools and approval status:

```bash
curl -H "Authorization: Bearer $EUNICE_API_KEY" \
     -H "X-EUNICE-Device-ID: admin-device" \
     "http://localhost:8000/admin/tools/approvals?org_id=default"
```

Disable a tool:

```bash
curl -X POST http://localhost:8000/admin/tools/approvals \
  -H "Authorization: Bearer $EUNICE_API_KEY" \
  -H "X-EUNICE-Device-ID: admin-device" \
  -d '{"org_id":"default","tool_name":"network_scan","approved":false}'
```

## 6. OIDC setup

```bash
curl -X POST http://localhost:8000/auth/oidc/providers \
  -H "Authorization: Bearer $EUNICE_API_KEY" \
  -H "X-EUNICE-Device-ID: admin-device" \
  -d '{
    "provider_id": "azure-ad",
    "org_id": "default",
    "name": "Azure AD",
    "issuer": "https://login.microsoftonline.com/<tenant>/v2.0",
    "client_id": "...",
    "client_secret": "...",
    "redirect_uri": "https://chat.company.com/auth/callback",
    "role_mapping": {"admin": ["EUNICE-Admins"], "user": ["EUNICE-Users"]}
  }'
```

## 7. Backup

Back up the `data/` directory regularly. Encrypted data can only be decrypted with the same `EUNICE_MASTER_KEY`.
