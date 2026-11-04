# Governing performance target: TVS S6802

Owner directive, 30 October 2026: performance and resource optimization must target the restaurant's TVS terminal. The OnePlus 9R has substantially greater processing headroom and is useful for functional checks; its successful runs do not establish responsiveness, memory safety or sustained operation on the TVS.

## Collected evidence

Source: `resources/references/technical-discovery-2026-10-25.pdf`, hardware table, supported by the supplied device photographs. Earlier transcription: `docs/restaurant/handoffs/2026-10-28-previous-handoff.md`, Confirmed hardware and printing.

| Property | Observed TVS baseline |
| --- | --- |
| Terminal | TVS Electronics S6802 |
| Android | 11 |
| Platform / board | Rockchip / `rk30board`; exact CPU and supported ABIs not established |
| RAM | About 4 GB; settings reported 4.1 GB, approximately 1.3 GB average use and 2.7 GB available at that inspection |
| Storage capacity | 128 GB; 10.27 GB used and about 117.7 GB available at inspection |
| Display | 1920 × 1080 landscape touchscreen |
| Proven field print route | USB TVS RP 3230, ESC POS USB Print Service, 80 mm / 203 DPI |

RAM availability and free space are historical snapshots, not guaranteed application budgets. Storage capacity does not establish read/write throughput or latency. CPU model, ABI, clocks, sustained performance, storage speed and current TVS WebView version remain unmeasured; do not fill them in from the OnePlus or from the board name.

## Implementation priorities

- Current starter photo budget (31 October 2026): 22 JPEGs, 947,459 bytes combined, 384px maximum edge; one-time sequential preparation with a durable skip marker on warm starts. See `menu-photos-2026-10-31.md`. Measure native startup, decoded-image memory and image-including full-backup I/O on TVS; this size budget is not a measured performance acceptance result.
- Keep tap-to-cart and checkout responsive before spending resources on analytics, images, exports or backup work. Preserve exact-money calculations, atomic ledger writes and durable acknowledgements.
- Bound image resolution, decoded-image retention, rendered rows and report work. Use ledger-backed queries and paging as data grows; measure full-result materialization rather than assuming ten visible rows also bound memory.
- Keep optional heavy export code outside startup/billing. Avoid retaining several full-size representations of a PDF, backup or image simultaneously. Stage/stream native files and keep large bytes out of activity state.
- Measure automatic-backup duration and its effect on checkout, disk writes and free space as the ledger and photos grow. Backups remain append-only: optimization must never silently delete retained shared backups or weaken consistency/restore checks.
- Measure password verification on the TVS; do not reduce password security merely because a phone test feels fast or because the terminal is slower. Any adjustment needs measured latency and a reviewed security tradeoff.
- Preserve the billing arrangement, local data, historical snapshots and the owner-confirmed current GST setup (new prices exclude GST from 2 November; old inclusive snapshots remain unchanged). Do not add a framework, cloud runtime or stock functionality to address an unmeasured bottleneck.

## Acceptance evidence

Follow `docs/restaurant/device-acceptance.md`, TVS performance. Record the actual TVS OS/WebView/ABI, usable memory, storage space and measured I/O, screen configuration, build/hash, dataset, thermal/background conditions and profiler overhead.

Use representative menu photos and a disposable 1,000-bill fixture, then larger history where justified. Measure cold/warm ready time, tap-to-cart and final-save latency, frame stalls, native/Java/WebView/JS memory peaks and growth over repeated billing/navigation/reprint cycles. Measure report, backup and CSV/XLSX/PDF peaks separately and while normal billing resumes. Do not clear or replace a live ledger to create test data.

Set numerical acceptance budgets from measured TVS behavior and cashier requirements; no invented CPU-equivalence, throughput numbers or RAM allowance is currently approved. CPU/network throttling and low-memory emulation can expose regressions, but cannot reproduce the TVS's CPU, storage, Android 11 WebView and thermal behavior. Keep such evidence labelled as simulation.

The OnePlus functional report is `docs/restaurant/oneplus-device-2026-10-30.md`. Additional Samsung SM-A235F checks and measured diagnostics are in `docs/restaurant/samsung-device-2026-10-30.md`. The Samsung reports about 5.45 GiB usable physical memory, still above the recorded TVS capacity. Neither phone is a TVS performance certification; actual TVS acceptance remains pending.

## 2 November counter optimization checkpoint

See `receipt-performance-2026-11-02.md`: fewer redundant cart renders/storage reads and a bounded image cache are desktop-verified. The desktop tap sample improved; warm startup did not. No actual TVS timing or memory acceptance result has been obtained.
