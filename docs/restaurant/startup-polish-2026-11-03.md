# Startup, login and billing polish — 3 November 2026

Scope: front-desk offline Android counter. No authentication algorithm, schema, `synchronous=FULL`, tax/receipt arithmetic, saved sale or backup format changes. Existing unrelated workspace work is retained. Local baseline snapshot precedes the phase commits; nothing is pushed.

## Discovery / phase A checkpoint

Source confirmed the hidden form and sequential DB → logo → branding → photos → workspace → backups → access path. The existing Settings `round_rupee` option defaults off. Fractional weight quantities are **not supported** by the existing integer-portion ledger; kg-labelled products are independent fixed portions. This task preserves that contract.

Changes: immediately rendered login shell with optional pre-paint branding/theme cache; separate entry and deferred app; disabled readiness state and safely queued early form submission; retry on DB failure; post-interactive images, workspace and backup initialization; existing asset markers and full image backups retained; current-version DB initialization avoids the DDL/seed write transaction; native splash/window blue and paint-triggered hide. Native backup validation now uses a uniquely named disposable native SQLite database, leaving WASM on the browser-preview branch. The validator, source snapshot, restore, authentication and image bytes are unchanged. Scratch deletion targets only that generated database, never `restaurant` or shared backup documents. Native execution of this new adapter remains unverified.

Detailed profiling is opt-in with `?startupProfile=1` or localStorage `restaurant.startupProfile=1`. Marks cover all seven stages plus form paint and interactivity. Existing `restaurant:ready` denotes completion of deferred startup, not time to login. First paint is a two-animation-frame observation of the visible shell, not an Android launch-to-screen measurement.

Desktop production-web Chromium 149, sql.js preview, five fresh browser contexts and five locked-owner relaunches; no connected shared backup folder. Median milliseconds from navigation:

| Scenario | Before form paint | After A form paint | Before interactive | After A interactive |
| --- | ---: | ---: | ---: | ---: |
| Empty browser storage | 740.0 | 129.5 | 720.5 | 222.0 |
| Locked-owner relaunch | 196.4 | 57.0 | 169.0 | 85.4 |

Raw stage timelines: `test-results/startup-polish/before.json`, `after-a-verified.json`; repeat with `node --import ./scripts/project-environment.mjs scripts/profile-restaurant-startup.mjs LABEL` after building. These are **not** Android debug/release or TVS results, and do not establish the requested TVS targets.

Phase A checks: 89 restaurant Node tests passed (85 baseline + two initialization + two native-adapter contract checks); seven focused Playwright scenarios passed, including delayed DB/early submit, DB failure/retry, nonblocking photo work, cached-name/removal priority, owner login, old-schema migration and full-image backup/restore. Lint and production web build passed. Native build result and final all-phase checks are recorded below when available. Actual TVS, fresh APK install, release timings, native scratch-validation lifecycle, shared-folder provider/reinstall and physical printing remain unverified. Connected OnePlus Pad Go live data was not touched. ABI narrowing (A10) intentionally omitted; it is optional and ABI support on TVS has not been measured.

Vite reports the intentional copied classic scripts (needed before module execution), existing duplicate icon import and lazy Excel chunk size warning. No external fonts or runtime network dependency was added.

Phase A wider browser run initially had 40 passes / four failures: deferred base CSS changed tile/cart geometry, and icons rendered before registration. Eagerly loading the shared base stylesheet before restaurant overrides and registering both icon sets before preferences corrected these. All eight affected/startup scenarios passed on the corrected build. Android debug assemble/lint succeeded (0 errors, 19 existing warnings); 11 unchanged Java tests passed using Gradle cached results. This does not verify the native JavaScript adapter or splash on hardware.
