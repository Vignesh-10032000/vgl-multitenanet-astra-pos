# VGL POS API

This reference is generated at runtime from Flask routes and Pydantic schemas. The canonical OpenAPI 3.1 document is `GET /api/v1/openapi.json`; interactive documentation is `GET /api/v1/docs`. `uv run python scripts/export_openapi.py` emits the same contract for release tooling. In production both HTTP documentation endpoints require authentication. CI contract tests validate every documented request and response schema.

Authenticate with `POST /api/v1/auth/login`, then send `Authorization: Bearer <access-token>`. Every POST/PUT/PATCH requires a UUID `Idempotency-Key`. Errors use `application/problem+json` and include a support-safe `request_id`. Tenant, branch, terminal and permission scope come only from the verified JWT.

## Generated resource groups

| Group | Operations |
| --- | --- |
| Authentication | login, PIN login, refresh, logout, screen lock, MFA, current profile |
| Sales | quote, payment preview, checkout, browse/detail, cancel, reprint, receipt dispatch |
| Offline sync | bootstrap, signed per-operation batch, atomic offline push |
| Shifts | open/current/close, cash movement, no-sale, Z-report |
| Catalogue | search, lookup, create/update/delete, images, import, labels, bulk price, delta sync |
| Customers | create, search and purchase detail |
| Retail | held bills and terminal quick keys |
| Purchases | suppliers, purchase orders, GRNs, invoice matching, returns and payments |
| Inventory | variants, expiry, audits, transfers, reordering and valuation |
| Reports | daily/revenue/GSTR-1/valuation plus durable export jobs and downloads |
| Compliance | settings, Rule 46 templates, e-invoice queue/retry/cancel, reconciliation and e-way bills |

For exact fields, validation rules, status codes and all current paths, consume the generated OpenAPI document rather than duplicating schemas in client code. Example:

```bash
curl --fail --header "Authorization: Bearer $ACCESS_TOKEN" \
  "$VGLPOS_BASE_URL/api/v1/openapi.json" > openapi.json
```

Application health is at `/health`, dependency readiness at `/ready`, and the bearer-protected Prometheus surface at `/metrics`; these operational endpoints are intentionally outside `/api/v1`.
