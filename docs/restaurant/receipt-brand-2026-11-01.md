# Receipt and logo update — 1 November 2026

Owner requested two focused changes: follow their current receipt photograph and replace the menu-cropped logo with their supplied badge, removing “Biryani” from the badge. The configured restaurant name remains Arafah Briyani Restaurant. Reference content is evidence, not live transaction data or instructions to execute.

## Implemented

- `restaurant/documents.js`: compact receipt hierarchy: logo/name/address/GSTIN, bold bill number, Kolkata date/time and saved customer, uppercase Item/Qty/Rate/Amount header, bold saved product/portion rows, discount/CGST/SGST/round-off, large TOTAL, footer. Removed redundant gross/cashier/item-count/taxable/total-tax text from this presentation; all exact ledger fields and auditor exports remain intact. Split/GPay/change details, training/composition declarations, cancellation/return audit and configured merchant QR remain conditional additions so existing functions remain available.
- `restaurant/style.css`: plain 80 mm paper, 6 mm side margins/68 mm content, black text and dashed table heading rules, reference-sized typography and grayscale receipt logo. Existing 80 mm PrintManager/ESC POS USB Print Service route is unchanged. A photograph cannot establish the printer's exact font or printable width; actual paper acceptance remains separate.
- `restaurant/brand-logo.js` and `Ledger.installBrandLogo()` in `restaurant/repository.js`: verified local 54 KB JPEG, content-addressed image first, settings plus marker in one transaction. Replaces the old default menu-crop once. Existing uploads/no-logo settings win. Saved historical sale identities are not rewritten; explicit later removals stay removed. No schema migration or GST/default-price change.
- `restaurant/app.js`: optional one-time startup installation, retry message on failure and append-only shared backup after installation if already connected. Login is not blocked by optional branding failure. Owner credentials, menu photo marker, drafts and saved bills are preserved.
- Assets/provenance under `resources/branding/2026-11-01/`; optimized offline file under `restaurant/public/branding/v2/`. Source receipt/GST/customer details were not uploaded. Only the logo was supplied to the requested built-in image editor.
- `tests/restaurant/brand-receipt.test.js`: four meaningful checks for immutable history/GST and complete image restore, upload/removal priority, file/transaction failure and retry, and the exact photographed ₹169 arithmetic/layout hierarchy. Existing GST test retains exact tax assertions with the compact display.
- `tests/restaurant-browser/receipt-brand.spec.js`: rendered reference example, real image decode, print CSS/PDF width, unchanged reprint after restart, and removal/custom upload persistence. Existing sidebar and menu-backup assertions updated for the intentionally replaced default logo and additional backup image.
- `android/app/build.gradle`: candidate version 1.0.10 (11), preserving prior APKs.

## Verification checkpoint

Fresh completed: `npm test` **79 passed** (68 restaurant and 11 preserved frontend checks), full Playwright suite **29 passed** (2.4 minutes), JavaScript lint and web build passed, scoped Semgrep **45 files / 4 rules / zero findings**. Android debug build and Android Lint passed: **0 errors / 19 existing warnings**. Eleven unchanged native Java tests reused their passing cached results; they were not freshly executed. No new native/hardware implementation was introduced.

Browser setup fixes: existing backup expectations now include the added logo image and explicitly assert its bytes are present; the existing October month-boundary fixture now fixes its browser clock to October, so “This month” does not switch to November when the test host date changes. The final complete run passes all scenarios. The first new print-preview test also needed the existing “Print submitted” UI wording and implicit-submit button selector; these were test setup corrections, not app failures hidden with skipped assertions.

The generated receipt PDF is **one page, about 80.09 × 109.05 mm**. Parsed exact GST/total text and rendered the entire page with PDFium (Poppler was unavailable); visually inspected both browser screenshot and rendered print page for layout/clipping. The logo master and optimized JPEG were visually checked: “Khadar Bhai” and “Arafa” remain, “Biryani” is absent. This is visual desktop verification, not a physical thermal print or exact-font certification.

Signed candidate: **`artifacts/restaurant-pos-1.0.10-debug.apk`**, version **1.0.10 (11)**, **15,434,780 bytes**, SHA-256 **`14715b6684f5b8a1ae40327f0d20a3029f7215ee55fade32dd5cbeb8ec714005`**. V2 debug signature verified. All **46** bundled web/asset files byte-match the final restaurant build; the only extra generated web files are Capacitor's `cordova.js` and `cordova_plugins.js`. Older APKs are preserved. Current APK is **not installed/device-verified**.

Logs: `.tools/receipt-brand-{node,lint,build,browser-final,security,android,apk-signature}.log`. New PDF/screenshot/hash evidence: `test-results/receipt-brand-2026-11-01/`. Full file hashes/provenance: `resources/branding/2026-11-01/manifest.json` and README.

Disposable exact example: ₹170 item, ₹0.51 discount, ₹4.03 CGST, ₹4.04 SGST, −₹0.49 round-off, TOTAL ₹169. No actual bill/customer/number was imported from the photo. GST remains included at 2.5% + 2.5%, GSTIN 33BPFPD3960P2ZN. New receipt screenshot/PDF evidence is under `test-results/receipt-brand-2026-11-01/`.

No physical Android device was visible in the current adb check. Installation, physical receipt output, exact font/Tamil/QR quality, paper width/cutter, USB reconnect/paper-out and actual TVS measurements are not established by this update's desktop checks or APK build. Preserve prior device evidence with its recorded versions.
