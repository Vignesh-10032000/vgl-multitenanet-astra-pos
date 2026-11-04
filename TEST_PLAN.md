# Restaurant POS reliability audit — 31 October 2026

Scope: existing offline HTML/JavaScript + Capacitor application in this checkout. No server, inventory, KOT or payment integration is added. Preserve the owner's installed data, draft, credentials, photographs and append-only shared backups. All generated workloads use isolated synthetic ledgers.

## Inventory and baseline

- Branch `codex/restaurant-offline`, HEAD `c6e3913`; substantial pre-existing uncommitted/untracked implementation is preserved.
- `restaurant/domain.js`: integer paise/BigInt, inclusive line GST, cumulative discount allocation, payments and Kolkata dates.
- `restaurant/repository.js`, `schema.js`: serialized service calls, atomic checkout/corrections, operation and invoice uniqueness, snapshots, holds/drafts, v1→v2 migration.
- `drivers.js`: Node tests use SQLite via `node:sqlite`; browser preview uses sql.js plus IndexedDB; Android uses Capacitor community SQLite. These are separate verification targets.
- `backup.js`, `backup-service.js`, `assets.js`, `backup-folder.js`: logical transaction snapshots, image bytes/digests, isolated validation, staged restore and append-only shared documents.
- `access.js`: salted PBKDF2 offline owner credentials, persisted failed-attempt lockout and session access lock; not encryption.
- `exports.js`, `documents.js`, `upi-qr.js`: CSV/XLSX/PDF, saved-snapshot receipts and explicitly non-payable demo QR.
- Native `RestaurantBackupPlugin`: SAF tree permission, bounded read/write, no backup deletion. `RestaurantDocumentsPlugin`: staged file picker and PrintManager. JUnit covers stream failures/staging; instrumentation template alone does not establish POS behavior.
- Node suites: financial fixtures, 510-bill ledger, rollback, retries, snapshots, corrections, migrations, photos, exports, owner access and folder mocks. Browser: 26 scenarios across billing, photos, split/reporting, setup and QR.
- Existing commands: `npm test`, `npm run test:restaurant:browser`, `npm run lint:js`, `npm run scan:restaurant`, `npm run profile:restaurant`; Android build script with `-Lint -UnitTests`.
- Baseline: 61 Node checks passed; restaurant web build passed (existing lazy ExcelJS chunk warning). Browser baseline is logged separately.

## Execution order and evidence

1. Financial properties: seeded fast-check inputs and independent BigInt expectations for discounts, GST, rounding, split allocation, change, invalid inputs and high valid amounts. Keep the Node runner. Evaluate mutation testing only on the financial core.
2. SQLite: inject failures at each write and before commit, reject duplicate IDs/numbers, interleave reads/writes, reopen file-backed ledgers, check foreign keys/integrity and draft/hold recovery. Add named regressions for reproduced defects before changing production code.
3. Recovery: complete image/owner/hold/snapshot round trip; image-write and restore-write failures; corrupted and malicious input; shared-folder permission/read-back failures. Keep legacy restore cases.
4. Configurable bounded stress: 100/500/1,000 bills, retries, mixed payments, interrupted writes, searches, drafts/holds/reopen, reports, real XLSX parse, CSV, image backup/restore. Record timings, memory samples, file growth and reconciliation. Desktop numbers are diagnostic, not TVS budgets.
5. Browser: fresh contexts only; existing flows plus sql.js persistence failure contracts. Inspect receipts/PDF and logs.
6. Android: build, JUnit, Lint, signature and asset hashes. Check connected-device identity. Native synthetic tests must use a distinct database; do not reset/uninstall or stress the owner's ledger. Physical paper, USB reconnect and TVS endurance remain hardware-dependent.
7. Static analysis: ESLint, scoped Semgrep, dependency audit and diff review. Report findings without unreviewed broad upgrades.

## Acceptance and limits

Any incorrect total, lost committed bill, partial financial record or duplicate invoice fails the relevant check. Counts/latencies must come from executed tools. Test failures remain visible in evidence, with remediation and reruns recorded. No invented universal performance thresholds. Actual TVS acceptance requires its Android 11 WebView/storage/thermal environment and representative data; a phone or desktop cannot establish that result. Reinstall/SAF and actual printer faults require a disposable installation/hardware session. No real payment is sent.

Commands and actual category outcomes are recorded in `TEST_REPORT.md`; raw outputs go under `test-results/reliability-audit/`.
