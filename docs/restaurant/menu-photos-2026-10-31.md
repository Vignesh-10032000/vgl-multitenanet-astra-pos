# Offline menu photos — 31 October 2026

Added **22 generated illustrative food photographs** for the 36 existing menu entries, including shared images for portion variants. These are sample menu images, not photographs of the restaurant's actual servings. Products explains that the owner can replace them with their own photos.

## Assets and performance constraints

The optimized JPEG set is **947,459 bytes combined**, with a maximum edge of **384px** and maximum individual file size **48,147 bytes**. Runtime files are `restaurant/public/menu-photos/v1/*.jpg`. The full selected originals are preserved separately in `resources/menu-photos/source-v1/` and are not packaged into the APK. All images were generated with the built-in image_gen tool; their prompt set, generator output paths and project paths are recorded in `resources/menu-photos/generation-v1.json`. No CLI/API-key fallback or external photo/CDN dependency was used.

`scripts/prepare-menu-photos.mjs` copies the selected originals without deleting them, downsamples/encodes JPEGs in an isolated browser canvas, checks the thumbnail size limit and writes `restaurant/menu-photos.json` with source paths, checksums and exact ID/name/portion matches. It refuses to overwrite a different existing thumbnail. No compositing or dish editing is performed by the preparation script.

First upgrade reads the small JPEGs sequentially, checks their byte length/checksum, saves them through the existing durable content-addressed ImageStore, then updates the eligible product references and install marker in one SQLite transaction. Subsequent starts check the marker and do not fetch/reinstall the bundled JPEGs. Billing retains its fixed image area and uses lazy loading with asynchronous decoding. Photos are shared between suitable portion entries without changing their independent prices.

This is a resource-conscious asset budget, not TVS performance certification. One-time native installation cost, decoded-image/renderer memory, and the larger complete-backup write/read-back cost still need measurements on the actual TVS. The complete backups now include these image bytes; no shared backups are deleted to offset the additional storage.

## Data preservation and recovery

- Existing uploaded photos win. Products renamed or changed to another portion are skipped unless they still match the original image mapping. The transaction rechecks those conditions after files have been prepared, so an intervening owner edit/upload wins too.
- Only `products.image` changes. Product IDs, names, portions, categories, active flags, prices, tax settings, saved bills, historical item snapshots and payments are preserved.
- The marker is `local:bundled-menu-photos-v1` in the existing local preferences/drafts storage. It is backed up/restored with the ledger. A photo the owner removes is not automatically reinstalled at the next start.
- Files are prepared before references are committed. A file-preparation/database failure leaves no partially updated product references or success marker. Photos can retry on reopening; an optional photo failure does not prevent accessing the saved ledger.
- On an existing connected shared-folder installation, a completed image update requests another consistent complete backup. Uploaded/default images use the existing image-including backup and restore validation. Old snapshots and backups remain untouched.

## File map

- `restaurant/menu-photo-install.js`: bounded sequential asset preparation and one-time update orchestration.
- `restaurant/repository.js`: atomic product-image update and marker; final edit/upload recheck.
- `restaurant/app.js`: initialization, nonfatal photo errors, backup integration and product-list image attributes.
- `restaurant/index.html`: illustrative-image explanation in Products.
- `src/vglpos/web/static/src/js/pos.js`: asynchronous image decoding; billing arrangement unchanged.
- `tests/restaurant/menu-photos.test.js`: five data-preservation/failure/concurrency/backup checks.
- `tests/restaurant-browser/menu-photos.spec.js`: actual thumbnails, no runtime external requests, warm restart, owner upload priority, removal and complete restore.

The existing Tamil/custom-photo browser case now waits for its debounced search to return one result before checking that photo, and expects the 22 bundled images plus its own custom image in a complete backup. The earlier test assumed all other menu entries had no photos; its assertions now verify the enlarged image set and the custom image explicitly.

## Verification and artifacts

Node suite: **58 passed**, including the preserved frontend/tax-parity checks and five new photo tests. Final browser suite: **24 passed** (1.7 minutes), including photo installation/upload/removal/restore and all earlier billing, split-payment, reporting and layout cases. JavaScript lint and web build passed. Scoped Semgrep: four rules, 42 files, zero findings. Android build/lint passed with zero errors and 19 warnings; the unchanged 11 Java tests reused their previously passing results.

APK SHA-256: `76607feefbc662b5b3c2a2976b605c0cf8458453c2cb7498632227e98277644c`; size 15,377,018 bytes. Signature verified with apksigner 36.1.0 and the same Android Debug signer. All **45** packaged web files match the build byte for byte, including all 22 JPEGs; Android package/version, minimum API 24, target API 36 and four ABIs were checked using aapt. Exact hashes are in `build-verification.json`.

Visual QA: every generated thumbnail was inspected in `test-results/menu-photos/contact-sheet.png`, and actual Billing screenshots at 1920 × 1080 and 732 × 336 were reviewed. Billing layout, portions, prices and inclusive GST are retained. Local preview: `http://127.0.0.1:5174/`.

Candidate APK: `artifacts/restaurant-pos-1.0.8-debug.apk`, version 1.0.8 (9). The later physical OnePlus OPD2305 session fresh-installed this exact APK and verified all 36 photo references/22 local images offline, image decoding across categories, Cash/UPI/split checkout, audited cancellations, offline force-stop/restart with the owner's actual draft and shared-folder access intact, and zero bundled-photo asset fetches after the install marker was present. The full image backup was saved natively and restored exactly into a disposable database; CSV/XLSX/PDF saves also passed. See `opd2305-device-2026-10-31.md` and local `test-results/android-opd2305/` evidence. The original three bills and ₹1,735 net, the owner's two-item ₹340 unpaid draft, and all nine shared backup documents remain intact. Earlier OnePlus 9R/Samsung evidence still applies to their reported versions. Upgrade from an older installed photo-less APK, actual uninstall/reinstall recovery, representative TVS image/backup performance and physical printing remain unverified.
