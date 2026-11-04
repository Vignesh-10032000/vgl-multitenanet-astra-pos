# Architecture and development tools

Research checked 28 October 2026. This is a scoped recommendation for implementation in the new chat, not an implemented conversion.

## Database decision

Use SQLite on the TVS terminal. It is designed for local application/device storage, supports transactions, and fits this single-terminal restaurant ledger. SQLite is embedded with the app; a separate MySQL service does not need to be installed or kept alive.

MySQL's official server support matrix does not list Android. Unofficial Android/Termux workarounds are not a deployment strategy for this counter. This does not mean MySQL could never be made to run experimentally; it means it is unnecessary and unsupported for the intended installed app. If a cloud service is introduced later, it may use its own server database without replacing the device's local SQLite source of truth.

Sources:

- SQLite appropriate uses: https://www.sqlite.org/whentouse.html
- MySQL supported platforms: https://www.mysql.com/support/supportedplatforms/database.html
- Android offline data architecture: https://developer.android.com/topic/architecture/data-layer/offline-first
- Android Room (native SQLite abstraction option): https://developer.android.com/training/data-storage/room

Choose one local database access layer and keep all ledger writes behind its repository/service boundary. Recommended first candidate for preserving the JS frontend is `@capacitor-community/sqlite`; package metadata checked during preparation reported 8.1.1 with `@capacitor/core >=8.0.0`. Verify platform/build/backup behavior before adopting it. Native Room behind a custom Capacitor plugin is a supported alternative if schema/transaction/backup needs justify it. Do not install two competing authoritative databases.

Amounts use integer paise or exact decimal arithmetic. Model products/variants, customers, sales, sale lines, payments, bill sequences, settings, print attempts and void/refund audit records. Save immutable line snapshots. Exclude stock, stock movements, valuation and purchase entities from the restaurant workflow. Image files live in app storage, with local paths and backup coverage.

Candidate plugin source: https://github.com/capacitor-community/sqlite

## Packaging and source reuse

Recommended route: bundled local HTML/CSS/JS in a Capacitor Android app, with native SQLite, printing and export/save bridges. Preserve the current billing arrangement, vanilla JS modules and useful tested arithmetic; avoid a UI framework rewrite without evidence of need.

Capacitor 8.5.3 was the npm stable version during preparation. Official v8 documentation supports Android API 24+ and an appropriate Android System WebView; Android 11 is inside that OS range. Actual TVS WebView version is not recorded. Resolve an Android 11-compatible dependency set at implementation time and pin package versions/lockfiles.

The existing application cannot simply be zipped into an APK:

- Its Jinja templates are rendered by Flask and reference server paths.
- Vite builds JS assets, not a complete standalone HTML shell; its current base is `/static/dist/`.
- Existing login, products/settings changes, sales/report queries and final invoice assignment depend on APIs.
- IndexedDB and service-worker caches currently support interruption recovery around a server; the 500-entry queue is not the permanent ledger.

Adapt the app shell/routing and replace core server calls with local repository operations. Retain Python code as a reference/test oracle where logic needs porting; do not try to install Flask, PostgreSQL, Redis and Celery onto the TVS as a prerequisite for billing. Cloud backup/sync may be added separately if requested; core checkout must remain independent.

Sources:

- Capacitor Android support/runtime: https://capacitorjs.com/docs/android
- Capacitor local plugin bridge: https://capacitorjs.com/docs/plugins/creating-plugins
- Capacitor storage guidance: https://capacitorjs.com/docs/guides/storage

## Printing options and already-established evidence

The user's USB connection and print-service proof are established. Preserve the demonstrated TVS S6802 -> USB -> RP 3230 hardware baseline.

1. First integration candidate: call Android PrintManager from the installed app and route a correctly sized document through the installed Looped Labs print service. This reuses the observed working driver path. Native APK -> print-service behavior still needs on-device testing.
2. If operational requirements justify direct printing, implement a focused native USB host plugin: enumerate devices, obtain USB permission, claim the correct interface/endpoint, serialize jobs, handle detach/reconnect and send the verified printer protocol. Identify by stable vendor/product/interface properties, not the old session bus path.
3. Rasterize Tamil/branding where printer text-codepage support is insufficient. Confirm printable dots, feed, wrapping, QR readability and any cutter commands on physical paper.

Use explicit print-job states. A saved sale is the source for retries and reprints. A successful USB write is not independent physical-print confirmation. No KOT, drawer integration, rooting or new hardware discovery is required for the initial slice.

Sources:

- Android USB host API: https://developer.android.com/develop/connectivity/usb/host
- Android PrintManager: https://developer.android.com/reference/android/print/PrintManager
- Verified field print service: https://play.google.com/store/apps/details?id=com.loopedlabs.usbprintservice
- Local evidence: `resources/references/technical-discovery-2026-10-25.pdf`

## Auditor exports and storage APIs

- CSV: a small local writer with UTF-8, quoting, formula-text protection and exact amount formatting.
- XLSX: ExcelJS is a candidate; npm reported 4.4.0, MIT. Check dependencies/browser bundle and use actual workbook tests before adopting. Avoid assuming the npm package named `xlsx` is current without checking its publisher's security/distribution guidance.
- PDF: Android PdfDocument/print rendering are candidates for locally generated readable reports. Tamil text needs real rendering checks; do not assume any JS PDF library handles Indic shaping correctly just because it accepts Unicode.
- Save/share: Android Storage Access Framework or an appropriate Capacitor native bridge; file selection via system picker. Keep report generation and saving offline. Verify saved files with real parsers/rendering.
- Backup: use a consistent SQLite backup/export strategy plus image/config files; validate and restore into a disposable instance. Do not confuse accounting exports with restorable backups.

Sources:

- ExcelJS source/documentation: https://github.com/exceljs/exceljs
- Android PDF API: https://developer.android.com/reference/android/graphics/pdf/PdfDocument
- Android document save/open APIs: https://developer.android.com/training/data-storage/shared/documents-files
- Capacitor filesystem: https://capacitorjs.com/docs/apis/filesystem

## Skills installed for this project

These are instructions for development, not runtime app dependencies. They are installed under `.agents/skills` and should become discoverable in a new chat opened in this folder.

| Skill | Source | Why selected |
| --- | --- | --- |
| capacitor-app-development | capawesome-team/skills | Existing web interface/native packaging, storage and Android troubleshooting. |
| capacitor-plugin-development | capawesome-team/skills | Focused native USB/printing/export bridge guidance. |
| capacitor-mcp | capawesome-team/skills | Setup and correct version selection for the documentation MCP. |
| android-cli | android/skills (Google) | SDK/device/ADB/documentation tooling and APK testing guidance. |
| testing-setup | android/skills (Google) | Native database, lifecycle and instrumentation test guidance. |

Quality review: Google Android skills repository reported about 9,921 stars. The specialized Capawesome repository reported 51 stars; its Capacitor app-development skill had about 1.3K installs in the skill directory. The low repo star count was considered, and its direct Capacitor specialization, maintainer identity, source instructions and absence of required paid/account services were reviewed. Popularity is not proof of correctness. Exact file hashes and source repositories are in tooling-inventory.json.

The user does not need Hilt/Compose/iOS/cloud services merely because a generic skill suggests them. Apply only relevant sections and retain the requested source/UI approach. No claim is made that these are the globally best tools; they are a small, reviewed set suited to this conversion.

Sources: https://github.com/android/skills and https://github.com/capawesome-team/skills

## MCP configuration and checks

Global configuration already contained Context7, Serena, Playwright and Chrome DevTools entries. This preparation does not reinstall those or change their global settings.

Project `.codex/config.toml` defines:

- `restaurant_context7`: verified remote documentation endpoint under a distinct project name, avoiding transport-field collisions with the inherited global `context7` entry.
- `capacitor`: hosted, UNOFFICIAL documentation MCP maintained by Capawesome. It serves official Capacitor docs; it is not an Ionic-endorsed server. No account or API token was needed during the check.

Both endpoints answered MCP initialize and tools/list requests. Capacitor search_docs also returned Android v8 documentation results. See mcp-health.json. The first Capacitor request without the later explicit client User-Agent returned 403; the subsequent proper-client requests returned 200. Do not hide that distinction when debugging network issues.

These direct endpoint checks do not inject tools into an already-running chat. The new trusted project chat must load the configuration. Serena/Playwright/Chrome DevTools remain inherited where the client makes them available; inherited configuration is not proof that every tool is healthy or that a device is connected.

MCP servers are development-time documentation/navigation/test tools. The installed POS does not call them and does not require internet for billing. No paid/external app APIs are needed for local menu/billing/export. Automatic UPI verification, GST portal filing or cloud sync would be separate requirements.

Sources:

- Codex MCP configuration: https://learn.chatgpt.com/docs/extend/mcp?surface=cli
- Context7: https://github.com/upstash/context7
- Capacitor MCP source/guide: https://github.com/capawesome-team/skills/tree/main/skills/capacitor-mcp

## Build environment observed

- Node 24.12.0, npm 11.6.2.
- Android SDK at `C:\Users\L E N O V O\AppData\Local\Android\Sdk`.
- SDK platform android-36 and build tools 35.0.0 / 36.1.0 present.
- ADB 1.0.41, platform-tools 36.0.0 works by absolute path. It was not on PATH.
- Java was not found on PATH and Android Studio was absent at the standard Program Files location. This is not proof that no JDK exists anywhere. Locate a suitable JDK or install the required one in the implementation chat before claiming an APK build.
- No connected-device or native-build check was performed during preparation. No new SDK/JDK/emulator has been installed by this preparation.

## GST boundary

The local FY 2025-26 GSTR-4 records composition filing. Confirm current status before live receipt configuration. If composition continues, customer documentation must follow the applicable Bill of Supply rules rather than separately collecting GST. Keep tax mode configurable and distinguish sale exports from statutory return preparation/filing.

Sources:

- Historical file: `resources/references/gst-return-fy2025-26.pdf`.
- CBIC composition conditions: https://cbic-gst.gov.in/hindi/composition-rules.html
- CBIC invoice/Bill of Supply FAQ: https://cbic-gst.gov.in/hindi/sectoral-faq.html
