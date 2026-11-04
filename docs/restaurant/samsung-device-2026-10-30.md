# Samsung multi-device verification — 30 October 2026

The Samsung provides additional functional and diagnostic evidence. The governing optimization target remains the TVS S6802; see `tvs-performance-baseline.md`. No CPU-equivalence or measured speed ratio between these devices is established.

## Device and build

Observed via authorized USB ADB: Samsung SM-A235F, Android 14, `ro.soc.model=SM6225`, board `bengal`, supported ABIs arm64-v8a/armeabi-v7a/armeabi. System WebView: 156.0.8078.47. Physical display: 1080 × 2408; density 450 dpi, override 480 dpi; app landscape viewport 732 × 336 CSS pixels with the keyboard dismissed.

Physical `MemTotal` was 5,711,876 KiB (about 5.45 GiB usable physical memory, not including swap); initially 2,590,248 KiB was available. Swap was 4,194,300 KiB and is not counted as physical RAM. `/data` reported 113,973,228 KiB total and 90,021,492 KiB available. These are snapshots, not app budgets or storage-throughput measurements. Dalvik properties reported 512m heap size and 256m growth limit; those are not a combined Java/native/WebView memory allowance. Battery initially 84%, 35°C, USB-powered.

Installation and functional tests used the identical **1.0.6 (7)** APK tested on OnePlus, SHA-256 `46a7b63c83dc588ae0b943ca1e9c2604380dac0c76e3623b3ca6d994343090c6`. The owner created their own account privately on the phone. No app data was cleared or uninstalled.

## Verified functional cases

- Owner setup/sign-in, seven navigation destinations, no horizontal page overflow during navigation.
- Ten add/quote/remove cycles with a ₹170 portion; cart returned to empty.
- Three new explicitly labelled test bills: Cash, GPay and split Cash ₹50 + UPI ₹120. All preserved inclusive GST: ₹161.90 taxable + ₹4.05 CGST + ₹4.05 SGST = ₹170. Cash ₹200 tendered gave ₹30 change. All three were fully voided with Samsung device-test reasons; gross ₹510, corrections ₹510, net ₹0. Historical bills and correction records remain intact.
- The owner selected shared folder **Music** using Android SAF. Automatic backups grew from one document to eight during customer/sale/cancellation tests. Every original backup URI remained present, and discovery validated the saved three-bill candidate.
- Mobile data was originally enabled and Wi-Fi disabled. Mobile data was temporarily disabled; Android reported no active default network. The app was force-stopped and relaunched offline. Private owner sign-in succeeded; all three bills/corrections, an unpaid test draft and the folder grant survived. The temporary draft was removed.
- CSV, XLSX and PDF were saved offline through the system document picker. CSV was parsed with Python and XLSX with ExcelJS: three invoices, four tender rows, three item rows and three corrections; gross/corrections ₹510 each and final sales ₹0. The 1,091,335-byte PDF parsed as 10 pages, was rendered with Poppler and visually inspected. Native staging cache was emptied after save. Mobile data was restored to its original enabled setting; Wi-Fi was left unchanged.

Local evidence is in `test-results/android-samsung/`: `device.json`, `smoke.json`, `restart.json`, `verification-summary.json`, native memory snapshots, receipt texts, exported documents, rendered pages and screenshots. No private references or phone data were uploaded.

## Measured diagnostics and limits

Ten in-WebView click-to-authoritative-total samples ranged **168.7–181.3 ms**, median **173.4 ms**. This includes the original **150 ms quote debounce** in `pos.js`, rendering and native interaction; it is not pure CPU work. No long task was reported by the observer during that short quote probe. There is no identical OnePlus timing series to compare against.

Main-process PSS was 172,001 KiB before navigation/billing and 183,745 KiB afterward. WebView JS used-heap snapshots were 4,282,672 and 7,135,180 bytes; no forced GC was performed. A later, different process after offline restart/exports reported main-process PSS 181,260 KiB. These samples exclude the separately hosted renderer's full native memory, are not peaks and cannot establish a leak or absence of leaks. Raw snapshots are retained.

`am start -W` activity total time was 2,763 ms on first launch and 1,420 ms for the offline cold restart. These are Android activity timings, not complete cashier-ready timings or comparable CPU benchmarks.

This run used the starter menu and three bills, not a representative photograph set or a 1,000-bill load. Final performance acceptance still requires the actual TVS, realistic history/images, sustained operation, combined memory/CPU/I/O profiling and physical printing.

## Compact navigation finding

Visual review found labels overflowing the inherited 76px sidebar at this width. The initial navigation check caught page overflow but did not assert that each link stayed inside its own sidebar. `PHONE-NAV-02` adds that assertion and reproduces the clipped-link failure before the fix.

The correction stacks icons and small, wrapped labels only between 721px and 899px, keeps touch targets at least 44px, sizes the menu logo to fit, and preserves the existing vertical scrolling. Portrait bottom navigation, the wider OnePlus/TVS layouts and billing arrangement are retained. The preview was verified on the actual Samsung. Version **1.0.7 (8)** is installed without clearing data; all **23 browser scenarios**, JavaScript lint, web build and Android build/lint passed (0 errors, 19 warnings). Eleven unchanged Java tests reused their previously passing results. The APK signature is verified and all 23 web assets match the build. SHA-256: `2ace40bc439933154590c899b0899de98c5241d2e7fba95bf010678ec990a8f0`.

**Final installed-build check passed:** after private owner sign-in on 1.0.7, all seven navigation links and their labels fit inside the sidebar with at least 44px touch targets. The three bills and all ₹510 of cancellations were retained, giving zero net sales. All eight existing shared backups and folder access remained present. The cart is empty. No page errors or new AndroidRuntime/Capacitor console errors appeared during the check. Evidence: `test-results/android-samsung/final-update.json` and `reports-107.png`. The payment/offline/export cases above used 1.0.6; the CSS-only follow-up was verified separately on installed 1.0.7.

## Device coverage

| Device | Evidence | Remaining significance |
| --- | --- | --- |
| OnePlus 9R / Android 14 / WebView 155 | Native functional smoke, offline restart, backup and exports; PDF picker crash found and fixed in 1.0.6 | Functional reference; performance does not transfer to TVS |
| Samsung SM-A235F / Android 14 / WebView 156 | Same 1.0.6 functional checks plus short quote probe; installed 1.0.7 navigation/data-retention follow-up passed | Additional device coverage; still more physical RAM than the recorded TVS |
| TVS S6802 / Android 11 / roughly 4 GB RAM | Collected hardware and field USB-service printing evidence | Actual app performance, lifecycle and physical printing acceptance still required |
