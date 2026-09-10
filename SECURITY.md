# Security Policy

## Reporting a vulnerability

Please open a GitHub issue only for non-sensitive bugs.

For a security-sensitive report, avoid publishing credentials, JWTs, cookies,
session IDs, authenticated API responses or personal data.

If a public issue is appropriate, provide only redacted logs and a minimal
description of the behavior.

## Credentials

This integration needs the user's m2A/Eaupla! credentials in order to log in to
the customer portal. Credentials are stored in the Home Assistant Config Entry.
JWT access tokens are generated at runtime and kept in memory.
