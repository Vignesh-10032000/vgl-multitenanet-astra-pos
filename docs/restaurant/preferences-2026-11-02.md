# Top-bar language and appearance controls — 2 November 2026

Owner requested the Tamil/English language control and theme button shown in their screenshot, on the existing app.

- Added adjacent language and moon/sun controls in the current top bar, with accessible names and 44 px minimum touch targets. Compact layouts retain both buttons.
- Tamil and English billing dictionaries are bundled locally; no Flask locale URL or external translation service is needed. Navigation, billing/payment/customer labels, menu forms, settings fields and reporting terminology follow the selection. Owner-entered menu names, categories, portions and historical receipt snapshots retain their saved text. Supporting diagnostic/help text and bilingual report metrics retain some existing English.
- Light/dark palette is applied across billing, management cards, forms and charts. Receipt paper/QR backgrounds remain readable.
- Language and appearance are device display preferences in localStorage (`vglpos.locale`, `vglpos.theme`), restored on reload without changing the SQLite ledger. Auditor export headings retain their existing stable labels.
- No ledger/schema, price, tax, menu-photo or printing changes. No owner database, credentials, shared backups or installed device state were touched. All browser work used disposable Playwright contexts.

## Verification

- New preference checks: 5 pass. They cover a ₹340 draft across both switches/reload, payment options, customer/product dialogs, all navigation targets, and both languages at 1024×768, 1070×716, 732×336 and 390×844. This is browser layout evidence, not TVS acceptance.
- `npm test`: 87 pass (including existing exact-money/tax, ledger, backup, export and image checks).
- `npm run lint:js`: pass after final dictionary-module correction.
- `npm run build:restaurant`: pass, with existing chunk warnings.
- Android assemble/lint: pass, zero errors / 19 existing warnings. Native source unchanged; Java unit tests not rerun for this display change.
- Signed debug candidate: `artifacts/restaurant-pos-1.0.15-debug.apk`, version 1.0.15 (16), 16,026,359 bytes, SHA256 `5e971c74d968bb2e2516bf5fe468a691bc1016fd638ed90fdeb13e9ee765e439`. Signature verified and all 58 bundled web files byte-match `dist/restaurant`.
- `npm run test:restaurant:browser`: all 36 scenarios pass (31 existing + 5 new).
- `npm run scan:restaurant`: 50 files / four rules / zero findings.
- `git diff --check`: pass.

Screenshots: `test-results/preferences/billing-dark-tamil.png` and `billing-light-english.png`.

## Device status

This candidate has not been installed or tested on an Android device in this chat. Last documented installed build remains 1.0.14 (15). Actual TVS performance, physical printing/reconnect and uninstall/reinstall recovery remain pending as before. Preserve all owner data, photo-install markers, original photos and append-only shared backups.
