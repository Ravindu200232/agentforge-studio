---
name: security-architecture
description: OWASP Top 10 mitigation, auth/session security, RBAC/ABAC authorization at data boundaries, input sanitization, rate limiting, and encrypted storage.
---

# Security Architecture & Threat Mitigation Skill

## Authentication & Session Security
1. **Session & Cookie Hardening**:
   - Session tokens must travel in `HttpOnly`, `SameSite=Lax` (or `Strict`), and `Secure` (in HTTPS) cookies.
   - Session tokens must never be accessible to client-side JavaScript to prevent cross-site scripting (XSS) token theft.
   - Sign-out must invalidate the session both in the database/cache and on the client cookie.
   - Passwords must be hashed using salted bcrypt/argon2; never plaintext or plain SHA hashes.

2. **Access Control & Authorization**:
   - Authorization must be enforced at the server route and database query level, never relying solely on UI button hiding.
   - Every object lookup (`/api/orders/:id`) must be strictly scoped to the authenticated user's ID or confirmed admin permissions.
   - Unauthorized requests must return `401 Unauthorized`; forbidden access must return `403 Forbidden` (or `404 Not Found` for tenancy isolation).

## Injection & Input Validation
1. **Query Sanitization**:
   - User inputs must never be directly interpolated into database query operators (preventing NoSQL injection such as `{"$ne": null}`).
   - Cast IDs to expected types before querying; reject malformed IDs with `400 Bad Request`.
2. **Strict Schema Validation**:
   - Enforce request body validation at the earliest API boundary.
   - Strip unknown fields and reject payloads exceeding size limits.

## Data Protection & Information Leakage
1. **Response Scrubbing**:
   - API endpoints must return only intentional, projected fields. Never serialize internal database models directly (preventing exposure of password hashes, reset tokens, or tenant metadata).
2. **Error Masking**:
   - Production error responses must return clean, user-friendly messages without leaking stack traces, database schema details, or server directory paths.
3. **Rate Limiting & Abuse Prevention**:
   - Rate limit authentication routes (login, register, password reset) to prevent brute-force attacks.
