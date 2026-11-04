# Restaurant POS: start here

Updated on 29 October 2026, Asia/Kolkata.

The active restaurant build now uses the adapted original `src/vglpos/web/templates/pos.html` and `src/vglpos/web/static/src/js/pos.js` for billing, connected to the existing SQLite/image/receipt services. The first original billing slice is implemented and desktop-tested; the original management screens still need incremental conversion. Read `docs/restaurant/original-billing-conversion.md` and `docs/restaurant/quality-gate-2026-10-29.md` before continuing. The earlier handoff describes the state before this conversion. Android installation, native lifecycle/provider tests, actual TVS profiling and physical-printer acceptance remain pending. Project Android/browser tools and caches have been relocated to D: at the owner's request; see `docs/restaurant/storage-migration.json`.

## Read in this order

1. `AGENTS.md` - project boundaries and confirmed user requirements.
2. `HANDOFF.md` - conversation context, source verification and current state.
3. `docs/restaurant/requirements.md` - screens, removals, reporting and setup details.
4. `docs/restaurant/architecture-and-tools.md` - SQLite, Android packaging, printing, tools and sources.
5. `docs/restaurant/acceptance-tests.md` - meaningful correctness and device checks.

## Resources

- `resources/references/` - 12 copied original references: GST return, field report, menu, receipt photo, current screens and device photographs.
- `resources/manifest.json` - original paths and SHA-256 checksums for the copied files.
- `resources/menu-transcription.json` - 36 menu entries/portions transcribed for review; these are seeded by the current separate app, and must retain their independent prices during conversion.
- `docs/restaurant/source-verification.json` - local/GitHub commit comparison.
- `docs/restaurant/tooling-inventory.json` - installed skills and observed build prerequisites.
- `docs/restaurant/mcp-health.json` - documentation MCP connection checks.
- `NEW_CHAT_PROMPT.md` - paste this into the new project chat.

## Start the new chat in this folder

Start a new chat under this SAME existing project, with `D:\vgl-restaurant-pos` as its primary folder. Paste the text from `NEW_CHAT_PROMPT.md`. Reuse the existing checkout and local work; no new clone or project is needed.

The project's primary folder controls working directory and discovery of AGENTS.md, skills and configuration. This task prepared files only; it did not create or dispatch another chat.

Official instructions: https://learn.chatgpt.com/docs/projects

## Source and branch

Repository: https://github.com/Vignesh-10032000/vgl-multitenanet-astra-pos

Baseline: `c6e39137ed0c84b431596a6d0d237d7b2ecdb66b`

Restaurant development branch: `codex/restaurant-offline`

The old README and server-oriented documentation remain as source context. The restaurant requirements in AGENTS.md and docs/restaurant govern this conversion.
