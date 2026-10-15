# Current dashboard feature carry-forward

The preserved `legacy/` application is reference material only. Its routes,
templates, dependencies and database access are not imported or enabled.

The current Flask dashboard now carries forward these useful capabilities:

| Preserved dashboard capability | Current implementation |
| --- | --- |
| Today's revenue and bill count | Selected trading date, completed sales only |
| Weekly and monthly revenue | Explicit rolling 7-day and 30-day totals |
| Product and customer counts | Active company catalogue and registered customers |
| GST summary | CGST, SGST, IGST, cess, total tax and discounts |
| Revenue chart | Seven gap-filled business dates with exact currency values |
| Top products | Five ranked products with quantity and revenue, localized names |
| Low-stock alerts | Current branch stock ledger balances and reorder thresholds |
| Recent transactions | Eight invoices with customer, quantity, date, tender, status and receipt links |
| Day close | Existing permission-checked blind shift-close flow |

The current version also adds payment-method totals, average bill value, a date
filter, manual refresh, clear empty/error states, retry without losing the last
successful result, and responsive blue styling inspired by the branded login.
Both English/Tamil and light/dark themes remain supported.

`GET /api/v1/reports/dashboard?on_date=YYYY-MM-DD` requires `report.view`.
Company and branch scope come from verified authentication claims, never query
parameters. Money and quantities are exact Decimal strings. Historical sales
use the selected date; stock and catalogue/customer counts remain current and
are labelled accordingly. Daily totals query completed sales directly rather
than waiting for a materialized-view refresh.

Demo login requires PostgreSQL and Redis to be connected to the deployed app.
The login's unavailable message accurately reports a failed service connection;
the UI must not substitute fabricated dashboard totals on failure. Follow
[the Railway connection guide](deployment-security.md#railway-service-connections).
