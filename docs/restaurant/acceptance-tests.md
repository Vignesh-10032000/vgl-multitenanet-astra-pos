# Acceptance and verification plan

These are planned checks, not claims that they have already passed.

## Existing behavior and simplified screens

- Compare the current billing interface with the preserved baseline at 1920 x 1080. Keep layout and interaction; verify the approved image-card changes.
- Create/edit/deactivate a product and select a local photo. Restart offline; photo and independent portion prices persist.
- Assign a product to Regular or Parcel; verify it appears in the chosen filter on Products and Billing, is excluded from the other filter, and appears in All. Category and search filters must still combine correctly. Edit/restart/full backup restore must retain the assignment.
- Set a fixed kilogram portion (for example 0.5 kg) and its independent selling price. Billing quantity counts whole portions at that saved price; editing only another field must not change the price or an existing `1/2 kg` label. Reject zero/negative/overprecision kg input; retain historical sale snapshots after price/portion edits.
- Customer form contains name, phone and city only. Walk-in billing remains available.
- No inventory navigation/columns/alerts appear; billing is not blocked by zero/missing stock. There is no hidden stock decrement dependency.
- English/Tamil labels and rupee text render; large touch targets remain usable on TVS and OnePlus screen sizes.

## Calculations and ledger

- Preserve existing exact-money, payment and tax fixture checks where applicable; compare converted calculations against independent fixtures.
- Parcel mutton biryani: 1 kg = 450.00; 1/2 kg = 230.00. They must not be proportional aliases.
- Current exclusive menu pricing: ₹170.00 base + ₹4.25 CGST + ₹4.25 SGST = ₹178.50. ₹200.00 tendered yields ₹21.50 change. Discounts reduce the base before GST; optional rupee rounding occurs after GST.
- Retain historical inclusive-GST regression: a saved ₹170.00 bill paid with ₹200.00 retains ₹30.00 change. Version-1/2 backups and v2 SQLite upgrade must preserve those snapshots alongside new exclusive bills.
- Repeated taps, retried saves and delayed print callbacks produce one saved sale/payment/number.
- Simulate failure partway through a sale transaction; no partial sale or orphan payment survives.
- Edit product prices/names after a completed sale; historical receipts and exports keep their original snapshots.
- Void/refund audit records remain linked, and original final numbers are not reused.

## Offline independence and recovery

- Install the APK, complete initial local setup, turn internet off and restart the app/device. Menu, checkout, customers, sales, reports and export function.
- Create more than 500 bills in an automated isolated database without requiring server synchronization. Avoid 500 physical paper receipts; hardware stress printing is a separate agreed-volume test.
- Reopen after forced process termination; committed sales survive and unsaved state is handled explicitly.
- Start a new business day/month/financial-year series offline. Check unique numbers and date-filter boundaries in Asia/Kolkata.
- Test storage/permission errors without silently discarding a sale or claiming an export succeeded.

## Sales and auditor output

- Test All, Cash and GPay filters individually and with date ranges. Displayed totals equal SQL/ledger-derived totals.
- Export CSV, XLSX and PDF while offline. Include a month boundary, discounts/rounding, a void/refund and Tamil/customer text.
- Reopen generated CSV/XLSX in a real parser; reconcile line/register/payment/monthly totals.
- Test commas, quotes, newlines and formula-leading text in fields. Preserve text without spreadsheet formula execution.
- Render PDF pages and inspect pagination, clipping, repeated headings and Tamil text. Do not accept file existence alone.
- Demonstrate backup/restore including all images, settings and numbering, with integrity checks in a disposable test instance.

## Android and physical printing

- Build and install the APK on a supported Android phone/emulator; log OS/device/build identifiers.
- Install and test on TVS S6802 Android 11. Confirm landscape layout, correct WebView behavior and restart.
- Print a sample 80 mm receipt using the tested Android print service through native PrintManager, or a deliberately implemented direct USB bridge. The physical USB cable is already proven.
- Verify actual printable width, Tamil/rupee glyphs, product wrapping, large total, own-store logo/QR and paper usage against the sample.
- Print after USB unplug/replug, printer off/on, paper-out, app restart and device reboot. Show actionable errors and safe reprint.
- A USB transfer success callback is not proof that a physical receipt printed. Verify actual paper output.
- Verify cutter only if enabled for this project; otherwise record manual tearing as the chosen behavior. Cash drawer and KOT remain excluded.
- Scan the configured merchant QR independently and confirm its actual payee before live use. A style-reference QR is never used.

## Reporting

Report code changes, exact commands/checks, pass/fail counts, produced artifacts and unverified device cases. Desktop test success does not establish native USB or production reliability. Keep `verification.md` current as work proceeds.
