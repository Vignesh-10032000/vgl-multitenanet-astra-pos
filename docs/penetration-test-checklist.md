# Penetration test checklist

Use synthetic data in an isolated staging tenant. Preserve request IDs and evidence; do not attack GST/IRP or notification providers without their written authorization.

- OWASP A01: cross-company/branch IDOR on every resource; role escalation; missing endpoint decorators; manager-override replay.
- A02: TLS/HSTS; secret storage/rotation; JWT and offline-signing strength; encrypted backups/WAL; no keys beside archives.
- A03: SQL/command/template injection; CSV formula injection; XML injection; upload parsing; barcode/search input.
- A04: server-authoritative totals/tax/stock; idempotency races; offline replay; invoice-number concurrency; return-overage and negative-stock attempts.
- A05: production config fail-closed; CSP; CORS; debug/docs/metrics exposure; container non-root; Kubernetes security settings.
- A06: pip/npm/container/action audit and unsupported dependencies.
- A07: username enumeration, MFA/PIN bypass, refresh replay, screen-lock bypass, brute-force and rate-limit behavior under distributed load.
- A08: artifact/image/import integrity, Celery message trust, deployment image digest, migration provenance and audit tampering.
- A09: every log correlation field; no GSTIN/phone/customer name in Sentry; alert delivery and runbook links; audit denial evidence.
- A10: SSRF through receipt/compliance webhooks, IRP URLs and uploaded content; egress allowlist.
- POS threats: malicious USB/barcode input, shared terminal sessions, drawer no-sale abuse, discount/void/reprint fraud, offline queue deletion, clock rollback, duplicate tender and compromised branch network.

Retest every critical/high finding. A release cannot accept an unresolved critical issue; high issues need a named owner and dated remediation approved by security and product owners.
