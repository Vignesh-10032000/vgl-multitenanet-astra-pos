# Billing, receipts and store administration

Payment opens with the exact bill total selected for editing. The summary distinguishes
money still to collect from change to return. Split tender fills the remaining amount;
Exact cash deducts other tenders. Completion waits for the latest validated preview.
UPI and card fields identify their required transaction reference. The server remains
the authority for totals, reference validation and completing the sale.

Receipts separate Date and Time, use tabular numeric columns, and show tender received,
change and remaining payment. Store time comes from `STORE_TIMEZONE` (default
`Asia/Kolkata`). Naive SQLite UTC timestamps keep their UTC meaning before display.
58 mm, 80 mm and A5 layouts share these rules, including provisional offline receipts.

Reports use Total sales, Bills completed and Stock value at cost. The selected dates
are shown; stock value represents current stock rather than the sales date range.
Chart labels have reserved space above the bars. Compliance summaries use plain labels
for waiting submissions, issues requiring attention and invoice mismatches.

## Login feature copy

The login overview groups implemented capabilities into stock visibility, customer
records and balances, sales insights, GST records, shift closing, branded receipts,
and account access. Checkout chips show scan/quick keys, hold/recall, split tender,
the offline bill queue, keyboard shortcuts and weighed goods. The same overview
is available below sign-in on mobile, in English and Tamil.

Claims were checked against the dashboard read model, customer list, reports/GSTR-1
export, POS shift dialogs, receipt settings and security settings. Purchase and
inventory-depth APIs are not advertised as completed browser screens. Industry
customization is offered as a conversation, without implying restaurant-specific
workflows are already included. Sample revenue remains explicitly illustrative.

## Store logo upload

Authorized users can upload or remove a logo in **Settings → Store profile**.
PNG, JPEG and WebP are accepted up to 512,000 bytes and 2048 pixels on either edge.
The server decodes the image, strips metadata and converts it to a PNG of at most
512 × 256 pixels. SVG and malformed files are rejected. Logos are stored with the
company and appear on receipts, including cached offline receipts after reference sync.

## Team and security

The login page offers **Staff / Cashier**, **Admin**, and **Super Admin** options.
Staff opens billing; administrator options open the dashboard, unless a safe local
destination was requested. Administrators can also use the staff entry for checkout.
The server verifies administrator selections against current company and branch roles
before issuing tokens. Selecting a role never adds permissions. Existing Owners can
use both administrator options. Existing API clients may omit the selection.

Use **Settings → Team & access** from an authorized account to manage these roles.

| Role | Account administration |
| --- | --- |
| Super Admin | Manages administrator and operational staff access within its company |
| Admin | Manages operational staff; cannot grant or change administrator accounts |
| Existing Owner | Retains company administration and may create Super Admins |
| Cashier | Uses assigned checkout permissions; cannot manage staff or store branding |

These roles never bypass the company boundary. Managers cannot change their own
account through team administration. Account changes require the acting user's
password and, when enabled, a current authenticator code. Existing branch-specific
assignments cannot be replaced by the company-wide team form.

Disabling an account, resetting credentials or changing its access invalidates its
previous access and refresh tokens through persisted session versions. Disabled
companies are also rejected. Account changes append audit events without credentials.

**Settings → Security** exposes authenticator enrollment, counter lock and sign out
on every device. Enrollment and global sign-out require fresh credential proof.
An enabled authenticator cannot be overwritten by setup; PIN login cannot bypass it.
Credential confirmation and authenticator actions are limited by company account.
Invalid setup codes report an error while preserving the existing valid session.
Concurrent API requests share one refresh rotation.

## Rollout and verification

Apply Alembic migration `0018` before starting updated workers, then build web assets.
The migration adds company logo storage and user session versions and has a downgrade.
Use the configured PostgreSQL and Redis services for server deployments.

Automated coverage includes payment races and split tender, uploaded image rejection
and isolation, Admin/Super Admin boundaries, MFA, token revocation, receipt layouts,
responsive reports, keyboard/scanner checkout, accessibility and the POS asset budget.
The complete migration chain was upgraded, downgraded and upgraded again on a scratch
SQLite database. Browser test databases now use separate connections for concurrent
requests rather than sharing one SQLite cursor.

Keploy external replay passed nine credential-free health, anonymous access and
malformed-login checks. Authenticated billing and role checks ran locally through
pytest and Playwright. The authenticated Keploy import was rejected by automatic
approval review because bearer tokens could be sent externally, so it was not run.
Keploy artifacts are in the ignored `test-results/keploy-api` directory. Only
per-request IDs and HTTP transport metadata were excluded from replay comparisons.

Semgrep did not complete: its Windows engine failed with `Invalid argument socketpair`.
Its result must not be described as a successful security scan.

Design references: [Square permissions](https://squareup.com/help/us/en/article/5822-employee-permissions),
[OWASP file uploads](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html),
and [OWASP session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
