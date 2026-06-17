# EUNICE Identity & Access Design

**Version:** 0.9-preview  
**Status:** Design draft — not yet implemented  
**Goal:** Enable one EUNICE server to serve multiple people, multiple devices per person, and optional future cloud identity providers (e.g., Google OAuth), while keeping data strictly isolated and conflicts transparent.

---

## 1. Core Concepts

EUNICE separates three ideas that are currently conflated in the `users` table:

| Concept | Definition | Example |
|---------|------------|---------|
| **Identity** | A real person or persistent persona. | `Alex` |
| **Device** | A physical client that talks to the server. | `Alex's phone`, `Alex's laptop` |
| **Session** | A single conversation thread. | `Morning planning`, `Trip to Tokyo` |
| **Profile** | A contextual persona under one identity. | `Alex/personal`, `Alex/work`, `Alex/guest` |

A household EUNICE server may have:

- One identity used by three devices (Alex on phone + laptop + browser).
- Three identities on one device (a shared kitchen tablet with a profile switcher).
- A guest identity that auto-expires after 24 hours.
- An office EUNICE with many identities and an admin identity.

---

## 2. Data Model

### 2.1 `identities`

The canonical person record. Provider-agnostic so Google OAuth can be added later.

```sql
CREATE TABLE identities (
    id TEXT PRIMARY KEY,                          -- internal UUID
    provider TEXT DEFAULT 'local',                -- 'local' | 'google' | ...
    provider_user_id TEXT UNIQUE,                 -- email from Google, or NULL for local
    display_name TEXT,
    email TEXT,
    avatar_url TEXT,
    passphrase_hash TEXT,                         -- for local auth; nullable if OAuth
    is_admin BOOLEAN DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### 2.2 `devices`

A device is a client instance. A device can be linked to exactly one identity at a time, but can be re-linked (switch user).

```sql
CREATE TABLE devices (
    id TEXT PRIMARY KEY,                          -- stable device fingerprint / device_id
    identity_id TEXT NOT NULL,
    name TEXT,                                    -- "Alex's Phone"
    device_type TEXT,                             -- 'phone' | 'laptop' | 'browser' | 'tablet'
    trusted BOOLEAN DEFAULT 0,                    -- requires admin approval if false
    last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
    last_ip TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (identity_id) REFERENCES identities(id) ON DELETE CASCADE
);
```

### 2.3 `sessions`

Already exists; update to reference `identity_id` (not just `user_id`). A session belongs to one identity and optionally one device.

```sql
ALTER TABLE sessions ADD COLUMN identity_id TEXT;
ALTER TABLE sessions ADD COLUMN device_id TEXT;
```

### 2.4 `facts` (with provenance)

Facts gain `device_id` and `identity_id` columns. Conflicts are tracked explicitly.

```sql
CREATE TABLE facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_id TEXT NOT NULL,
    device_id TEXT,                               -- provenance
    key TEXT NOT NULL,
    value TEXT,
    category TEXT DEFAULT 'general',
    confidence REAL DEFAULT 1.0,
    source TEXT DEFAULT 'explicit',
    reinforcement_count INTEGER DEFAULT 1,
    conflict_with INTEGER,                        -- reference to another fact.id
    resolved_at TEXT,                             -- NULL until user resolves
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(identity_id, key),
    FOREIGN KEY (identity_id) REFERENCES identities(id) ON DELETE CASCADE
);
```

> **Note:** The `UNIQUE(identity_id, key)` constraint is relaxed during conflicts. A conflicting fact is inserted with `conflict_with` set, and the resolver marks the chosen one as canonical.

---

## 3. Authentication Providers

### 3.1 Primary: Local Passphrase / PIN

Default for a private, local-first assistant.

- First setup creates the admin identity with a passphrase.
- New devices claim an existing identity by providing the passphrase.
- Passphrase is hashed with `bcrypt` or Argon2 and stored in `identities.passphrase_hash`.

### 3.2 Future: Google OAuth

Google Auth is an optional provider. The schema already supports it via `provider` and `provider_user_id`.

- `/auth/google/login` redirects to Google.
- Callback exchanges code for ID token.
- EUNICE extracts email and either creates a new identity or links to an existing one.
- Refresh tokens are stored encrypted in a separate `provider_tokens` table.

### 3.3 Provider Interface

```python
class IdentityProvider:
    async def authenticate(self, credentials: dict) -> IdentityInfo: ...
    async def refresh(self, stored_token: dict) -> IdentityInfo | None: ...
```

This keeps the core identity logic provider-agnostic.

---

## 4. Login / Claim / Switch Flow

### 4.1 New Identity + First Device

```
POST /identity/create
{
  "display_name": "Alex",
  "passphrase": "...",
  "device_id": "phone-abc123",
  "device_name": "Alex's Phone",
  "device_type": "phone"
}

Response:
{
  "identity_id": "uuid-alex",
  "device_id": "phone-abc123",
  "token": "<session_token>"
}
```

### 4.2 Claim Existing Identity on New Device

```
POST /identity/claim
{
  "identity_id": "uuid-alex",
  "passphrase": "...",
  "device_id": "laptop-xyz789",
  "device_name": "Alex's Laptop",
  "device_type": "laptop"
}
```

- If `trusted_devices_only` is enabled, admin must approve the new device.
- On approval, the device is linked to the identity.

### 4.3 Switch Identity on Existing Device

```
POST /identity/switch
{
  "device_id": "kitchen-tablet-001",
  "identity_id": "uuid-bob",
  "passphrase": "..."
}
```

Useful for shared tablets or browsers.

### 4.4 Session Token

After login/claim/switch, the server returns a short-lived session token (JWT or signed token) that the client sends on subsequent requests:

```
Authorization: Bearer <session_token>
X-EUNICE-Device-ID: laptop-xyz789
```

The token contains `identity_id` and `device_id`. The server validates it per request.

---

## 5. Conflict Resolution

### 5.1 Detecting Conflicts

When a device stores a fact that contradicts an existing fact for the same identity:

1. Mark the new fact with `conflict_with = existing_fact.id`.
2. Insert the existing fact's `conflict_with = new_fact.id` (bidirectional link).
3. Queue a clarification alert.

### 5.2 Delivering Clarification

Next time the identity chats, EUNICE asks:

> "Your phone says your favorite color is blue, but your laptop says red. Which is right?"

Or the client can poll:

```
GET /alerts
```

Response:
```json
{
  "alerts": [
    {
      "type": "fact_conflict",
      "facts": [101, 102],
      "question": "Your phone says your favorite color is blue, but your laptop says red. Which is right?"
    }
  ]
}
```

### 5.3 Resolving

```
POST /alerts/resolve
{
  "alert_id": "alert-1",
  "keep_fact_id": 101
}
```

- The chosen fact becomes canonical (`conflict_with = NULL`, `resolved_at = now`).
- The losing fact is soft-deleted or marked `archived`.
- EUNICE replies with confirmation.

---

## 6. Identity Lifecycle

| State | Behavior |
|-------|----------|
| **Create** | First device sets up identity. Can be admin. |
| **Claim** | New device joins existing identity via passphrase or OAuth. |
| **Switch** | Shared device changes active identity. |
| **Guest** | Temporary identity with auto-expiry. No passphrase required. Data wiped on expiry or logout. |
| **Archive** | Identity data retained but device cannot log in. |
| **Delete** | Full wipe of identity data from SQLite, ChromaDB, and files. |

### Guest Mode

```sql
CREATE TABLE guest_sessions (
    identity_id TEXT PRIMARY KEY,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (identity_id) REFERENCES identities(id) ON DELETE CASCADE
);
```

A background job checks for expired guests and deletes them.

---

## 7. Tool Permission Model

Tools declare their risk and required permissions in the manifest:

```json
{
  "name": "transfer_funds",
  "description": "Send money from the user's account",
  "risk_tier": "high",
  "requires_confirmation": true,
  "allowed_by_default": ["admin"],
  "allowed_profiles": ["personal", "work"],
  "denied_profiles": ["guest"]
}
```

### Permission Resolution

1. Is the tool enabled globally in `config.py`?
2. Is the identity allowed to use this tool?
3. Is the current profile allowed?
4. Does the risk tier require confirmation?

If any check fails, EUNICE returns a denial or asks for admin approval.

---

## 8. Notifications & Proactive Nudges

EUNICE uses a scheduler for user-visible reminders, not hidden autonomous actions.

### Rules

- A reminder is a notification: "You have a meeting in 15 minutes."
- A nudge is a suggestion: "Last time you mentioned calling your sister. Want me to add a reminder?"
- **No autonomous tool execution** unless explicitly enabled by the user for that specific tool.
- Reminders are stored in SQLite and delivered via `/alerts` or inline in chat.

### Data Model

```sql
CREATE TABLE reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_id TEXT NOT NULL,
    title TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    delivered BOOLEAN DEFAULT 0,
    recurrence TEXT,                              -- cron-like expression or NULL
    FOREIGN KEY (identity_id) REFERENCES identities(id) ON DELETE CASCADE
);
```

---

## 9. API Endpoints (Draft)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/identity/create` | Create identity + first device |
| POST | `/identity/claim` | Link new device to identity |
| POST | `/identity/switch` | Switch device to another identity |
| POST | `/identity/logout` | Log out device |
| DELETE | `/identity/{id}` | Delete identity and all data |
| GET | `/identity/me` | Current identity info |
| GET | `/devices` | List devices for current identity |
| POST | `/devices/{id}/approve` | Admin approves a pending device |
| DELETE | `/devices/{id}` | Revoke device access |
| GET | `/alerts` | Pending alerts for identity |
| POST | `/alerts/resolve` | Resolve an alert |
| GET | `/auth/google/login` | Initiate Google OAuth |
| GET | `/auth/google/callback` | Google OAuth callback |

---

## 10. Migration Path from v0.8

1. Rename existing `users` table to `identities`.
2. For each existing `user_id`, create one identity and one device.
3. Update `sessions`, `messages`, `facts`, `trails`, etc. to reference `identity_id`.
4. Add `devices`, `reminders`, `alerts`, and provider tables.
5. Keep `user_id` as a read-only alias for `identity_id` during transition.

---

## 11. Open Questions

1. Should the admin identity be required, or can EUNICE run in "flat" mode where every identity is equal?
2. Should device approval be required by default, or only in office mode?
3. How should identity deletion handle vector memory (ChromaDB) cleanup? By metadata filter on `identity_id`.
4. Should OAuth linking to an existing local identity require the local passphrase?
5. What is the session token TTL? Suggest 7 days with sliding refresh.

---

## 12. Recommended Implementation Order

1. Schema migration: `identities`, `devices`, `sessions` updates.
2. Local auth: create, claim, switch, logout.
3. Device trust / admin approval.
4. Conflict detection and `/alerts` endpoint.
5. Guest mode.
6. Tool manifest + permission checks.
7. Reminders/notifications scheduler.
8. Google OAuth provider.
