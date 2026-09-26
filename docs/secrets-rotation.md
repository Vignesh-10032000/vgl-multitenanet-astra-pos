# Secrets and rotation

Production secrets live in the deployment secret manager and enter pods as environment variables or read-only files. They are never committed, baked into images, printed, included in Sentry, or stored beside backups. Required classes include Flask/JWT/offline signing keys, database/Redis credentials, metrics token, IRP/provider credentials, alert webhooks, Grafana admin password, object-store credentials and the age identity.

Rotate provider and metrics credentials every 90 days, database credentials at least every 90 days, and signing keys annually or immediately after suspected exposure. Prefer overlap: add the new credential, deploy readers capable of both where the protocol supports it, switch writers, verify, revoke old, and record evidence. JWT rotation invalidates sessions unless a multi-key verifier is introduced; schedule and communicate it. Offline-signing rotation must account for queued terminal operations. The backup age identity needs a documented re-encryption/retention plan before retirement.

Emergency rotation: contain access, disable the affected feature, issue replacement, deploy through the normal readiness gate, verify audit/provider logs, revoke the exposed value, and open an incident review. Never paste a secret into a ticket or command history.
