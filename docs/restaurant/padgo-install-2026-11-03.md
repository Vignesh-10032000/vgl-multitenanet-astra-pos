# OnePlus Pad Go update — 3 November 2026

Owner requested installing the latest prepared APK. Installed **1.0.17 (18)** in place over Wi-Fi on OnePlus OPD2305 / Android 14. Signature verified; artifact and installed base APK SHA-256 both equal `5daf23a156be854b4271e917064ab78b6b4d8c23492ffef2006acb0e4c7f9fd4`.

Before installation, force-stopped the app and saved a complete closed-app private safety archive locally. Database integrity passed. All **43 protected files** matched exactly after `adb install -r` and before startup. No uninstall, data clear or live restore.

After native first startup, captured another closed-app archive and confirmed **schema v3**, SQLite integrity and zero foreign-key errors. Every original column in products, customers, sequences, sales, sale lines, payments, adjustments, adjustment payments, print attempts and drafts compared equal. Preserved **36 products, seven bills, 16 sale lines, eight payments, three adjustments, four adjustment payments and six draft rows**. Original images and account preferences match. Expected runtime changes are Android profile-installer bookkeeping, WebView cached flags/parameters and Capacitor's last installed version name/code.

The updated app opens successfully to the owner's existing **Welcome back / Sign in** screen, visually checked on the actual tablet. Left open there for private owner sign-in. No checkout, test sale, printing, shared-folder write/deletion or credential change was performed. First-start migration on this OnePlus is verified; signed-in billing, TVS performance, physical printing and actual reinstall recovery remain separate acceptance checks.

Private archives, database copies, screenshot and detailed JSON are in `test-results/padgo-update-2026-11-03-012631/`. Keep these local; never upload/commit account or ledger snapshots. Local safety archives supplement the app's append-only shared recovery backups and do not replace them. Previous build-verification JSON records the original build-time installation status.
