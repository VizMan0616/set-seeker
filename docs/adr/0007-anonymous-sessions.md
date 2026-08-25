# ADR 0007: Anonymous session-based users

- Status: accepted
- Date: 2026-08-24

## Context

Charm inventories and search pagination state must persist somewhere. Options:

1. **Anonymous long-lived session cookie**, inventories server-side keyed by session.
2. **Browser localStorage only**: zero server user data, but no cross-device sync and data
   vanishes on cache clear.
3. **Full accounts** (email/OAuth): real sync, but auth code, password reset, and security
   surface on a self-hosted open-source tool.

## Decision

Anonymous sessions. First visit issues a long-lived, unguessable cookie (`sessions.id`);
inventories and search states are stored server-side in SQLite keyed by it. No registration,
no login, no personal data.

## Consequences

- Zero friction — critical for a tool people open mid-hunt, often on a phone.
- Self-hosters never manage accounts; the threat model shrinks to "don't leak session ids".
- Losing the cookie loses the inventory; acceptable for v1. A future "export/import inventory"
  (JSON download/upload) mitigates without auth — candidate for a later ADR.
- Session cleanup job needed (delete sessions/search states idle beyond N days).
