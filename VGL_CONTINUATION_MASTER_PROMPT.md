# VGL Website — Continuation Master Prompt (Phases 3–6)

You are continuing the approved Vignesh Growth Lab (VGL) implementation inside the
AstroWind repository `Vignesh-10032000/astrowind-main`, on branch
`claude/vgl-website-implementation-nvlqdl`. Phases 1–2 are COMPLETE, verified and
committed (signed commits: `b26d117` "Phase 1: VGL foundation", `085b89d`
"Phase 2: full homepage"). The plan was already approved — do NOT re-plan, do NOT
redesign, continue implementation directly with Phase 3.

## STEP 0 — verify branch state before anything else

Run `git log --oneline -3` on `claude/vgl-website-implementation-nvlqdl`.
- If the tip is "Phase 2: full homepage in approved section order" → continue with Phase 3.
- If those commits are MISSING (the previous session's push was blocked by a 403
  write-permission denial): STOP and ask me to upload `vgl-website-branch.bundle`
  (I have it downloaded). Then restore with:
  `git fetch <path-to-bundle> claude/vgl-website-implementation-nvlqdl:restored && git checkout -B claude/vgl-website-implementation-nvlqdl restored`
  Never rebuild Phases 1–2 from scratch and never start over from main.

## Sources of truth (already in the repo, priority order)

1. `design-reference/vignesh-growth-lab-website-design/project/uploads/master_prompt_claude_fable.md` — all business facts (never invent or alter facts)
2. The `.dc.html` files in `design-reference/.../project/` — approved visual/responsive/2.5D direction. Read the relevant one before building each page: `Services.dc.html`, `Service Template.dc.html`, `Projects.dc.html`, `Case Study Template.dc.html`, `About.dc.html`, `Contact.dc.html`
3. `design-reference/.../project/claude-code-notes.md` — implementation rules (re-read it first)
4. Content matrices are ALREADY PORTED to typed data — use `src/data/vgl/services.ts`, `src/data/vgl/projects.ts`, `src/data/vgl/site.ts`; do not re-read the original .js matrices except to double-check

## What already exists (do not rebuild)

- Dark-only Nocturne theme. Tokens in `src/assets/styles/tailwind.css` under the
  `vgl-*` namespace (`--color-vgl-bg/surface/text/accent`, neutral+accent ramps
  100–900, `--color-vgl-section(-glow/-ghost)`, `--color-vgl-cyan` (tech only),
  `--color-vgl-wa`/`-wa-text` (WhatsApp only), `--radius-vgl-sm/md/lg`,
  `--shadow-vgl-sm/md/lg`) plus primitives: `vgl-btn`, `vgl-btn-primary`,
  `vgl-btn-ghost`, `vgl-btn-wa`, `vgl-card`, `vgl-tag(-accent/-neutral/-tech)`,
  `vgl-container`, `vgl-kicker`, `vgl-input`, `vgl-rule`; motion utilities
  `[data-reveal]`/`.vgl-in`, `.vgl-float`, `.vgl-lift`, `.vgl-cta .vgl-arrow`,
  `vgl-pulse` — all with `prefers-reduced-motion` overrides.
- Components in `src/components/vgl/`: `Header` (sticky frosted nav, exact link
  order, mobile menu with Escape/focus/scroll-lock, 900px breakpoint), `Footer`
  (3 columns + MSME bar + disabled Instagram), `FloatingWhatsApp`, `WhatsAppCta`,
  `SectionHeading` (kicker/h1|h2/sub, `cyan` prop), `CtaBand`, `TrustStrip`,
  `StatsGrid` (`[data-stats]` + `.vgl-num` counters), `ComparisonTable` (table +
  ≤760px stacked cards), `ProcessSteps`, `FaqAccordion`, `TechnologyGroup`,
  `ServiceVisual` (4 compact 2.5D mini-scenes), `ServiceCard`, `ProjectCard`
  (takes `cardCopy` override; AI-automation variant renders poster+play link, no
  embed), `DeviceMockup` (angled browser chrome), `ImageFrame` (missing-screenshot
  placeholder — real screenshots don't exist yet), `ResultBadge`, `TestimonialCard`
  (video variant with the approved "Video will be added before launch" fallback),
  `ContactForm` (complete Formspree wiring), `HeroHome` (approved 2.5D hero 1a),
  `RevealMotion` (IO reveals + counter animation; include once per page that needs motion).
- Data/utils: `src/data/vgl/{site,services,projects}.ts`,
  `src/utils/whatsapp.ts` (`waLink(message)`), `src/utils/structured-data.ts`
  (`jsonLd()`, `localBusiness`, `faqPage`, `aboutPage`, `contactPage`,
  `collectionPage`, `breadcrumbList`, `serviceSchema`, `creativeWork`, `siteUrl()`).
- Pages: homepage is FULLY implemented (approved section order, 2.5D hero,
  Formspree form, motion). `/about`, `/contact`, `/services`, `/services/[slug]`,
  `/projects`, `/projects/[slug]`, `404` exist as styled stubs with correct
  per-route metadata + JSON-LD already wired — flesh them out, keep their
  metadata/JSON-LD approach.
- Assets in `public/`: `brand/vgl-logo(-mark).svg`, `images/vignesh.webp`,
  `images/nextgen-testimonial.webp`, `videos/n8n-workflow.mp4`,
  `documents/vgl-resume.pdf`, `documents/udyam-certificate.pdf`,
  `images/workflow/` (empty, reserved). Interim OG brand card at
  `src/assets/images/og-cover.png` (replace-before-launch, wired in config.yaml).
- `src/config.yaml`: siteUrl placeholder `https://vignesh-growth-lab.example`
  (single source for all absolute URLs — flagged for launch), dark:only theme,
  blog disabled, title template `%s`.

## Remaining phases

### Phase 3 — Services (`/services` + `/services/[slug]` ×4)
Follow `Services.dc.html` and `Service Template.dc.html` exactly.
- `/services`: hero (kicker "Services", h1 "Four ways we grow<br>Tamil Nadu
  businesses.", sub); four `<article>` rows separated by `border-top` (4th also
  border-bottom): number 01–04 (accent, tnum) + h2 with service icon (cyan;
  WhatsApp service icon green) + description + neutral tag chips | right column
  "Who it's for" + audience copy + proof line (ph:trend-up, accent-200) + CTAs
  "Explore service" (primary → detail page) and "See the proof" (ghost → related
  case study); "Same process, every service" compact 4-step grid
  (PROCESS_STEPS_COMPACT); glow CTA panel ("Not sure what your business needs?" /
  "Book a free call" → wa message "Hi Vignesh, I'd like a free strategy call.").
  CollectionPage/ItemList JSON-LD is already in the stub.
- `/services/[slug]`: breadcrumb (Home › Services › name, aria-current, ph:caret-right);
  2-col hero: kicker "Service", h1 serviceName, heroStatement, outcome line
  (ph:target cyan, "**Outcome:** …"), CTAs "Get a free quote" (WhatsApp,
  service.waMessage) + "What's included" ghost → `#included` anchor + price tag
  ONLY when `startingPrice` non-empty (website-development only) | right: 16:11
  hero media — `ImageFrame` since all heroImage fields are empty; proof strip
  (quickProof + "MSME Registered" + "Direct founder support"); "Who it's for";
  `#included` section (scroll-margin-top 84px): 6 feature cards from
  service.features (cyan icons) + Technologies chip row (vgl-tag-tech);
  related-project card (ImageFrame left; tags, h3, copy, result line, CTAs "Read
  the case study" + "Live site" ONLY when related.liveUrl non-empty — hidden for
  whatsapp-ai-automation); compact process; glow CTA with service.ctaHeading +
  "Talk to Vignesh on WhatsApp". Service + BreadcrumbList JSON-LD already in stub.
- Build a small `SectionGlowPanel.astro` for the glow CTA card
  (radial `--color-vgl-section-glow` over `--color-vgl-section`, radius-lg,
  flex-wrap justify-between) — it recurs on services/service/projects/case-study pages.

### Phase 4 — Projects (`/projects` + `/projects/[slug]` ×4)
Follow `Projects.dc.html` and `Case Study Template.dc.html` exactly.
- `/projects`: hero (kicker "Projects", h1 "Projects built around<br>measurable
  business outcomes.", sub "15+ projects delivered across Tamil Nadu — stores,
  boutiques, POS systems and AI automations. Here are the ones with stories worth
  telling."); 4 ProjectCards (full matrix summaries, result badge line style per
  design — reuse ProjectCard); "More delivered work" (MORE_PROJECTS: Masala Mill
  Store, Albatross Gym — quiet bordered cards, no CTAs); glow CTA ("Have a
  similar project in mind?" / "Talk to Vignesh" → wa "Hi Vignesh, I have a
  project in mind.").
- `/projects/[slug]` — one template, conditional blocks in FIXED order; empty
  fields collapse the block entirely:
  1. Breadcrumb (Home › Projects › client) + tags (type/location/tech) + h1
     client + summary + CTA row: live-URL button ONLY if `liveUrl` (label from
     `liveLabel`) + WhatsApp "I want something like this" (project.waMessage);
     hero media 21:9 rounded-14 — ImageFrame (all heroImage empty today).
  2. Facts bar: 4 quiet cards — Client / Location / Project type / Built with.
  3. Brief & build 2-col: left kicker = `challengeKicker` ("Project goal" — this
     exact label, it must never imply a client statement), challengeTitle,
     challenge; right kicker "What we built" in CYAN (bar+text), solutionTitle,
     solution, delivered[] list with cyan ph:check.
  4. Results band (full-bleed `--color-vgl-section` + glow, like StatsGrid):
     h2 "Results", 3 stat pairs from results[], tnum, counters welcome.
  5. Testimonial — ONLY when quote non-empty (NextGen only): blockquote
     (Inter 500, clamp(21,2.4vw,28), hanging quotes) + figcaption "— quoteAuthor"
     + testimonial image (nextgen-testimonial.webp, max-width 320, radius 12).
  6. Video — ONLY when videoSrc non-empty (AI automation only): kicker "In
     action" + h2 videoHeading ("Workflow demonstration"); figure.card with
     native <video controls playsinline preload="metadata"
     src="/videos/n8n-workflow.mp4" aria-label={videoLabel}
     style aspect-ratio 16/9, object-fit contain, top corners rounded>;
     <track kind="captions"> ONLY if videoCaptionsFile; visible figcaption =
     videoLabel; transcript <details> ONLY if videoTranscript. No poster file
     exists yet — omit poster attr until supplied.
  7. Gallery — ONLY when galleryImages non-empty: currently EMPTY for all →
     the gallery section is HIDDEN entirely (the 4 n8n screenshots don't exist
     yet; captions are pre-staged in data for when they arrive at
     /images/workflow/n8n-workflow-1..4.webp).
  8. CTA: border-top divider, "Want results like this?" + "Free 30-minute
     strategy call. Custom proposal in 24 hours." + buttons: WhatsApp "Talk to
     Vignesh" + ghost "About this service" → relatedServiceRoute + ghost "All
     projects" → /projects.
  CreativeWork + BreadcrumbList JSON-LD already in the stub.

### Phase 5 — About + Contact + 404 polish
Follow `About.dc.html` / `Contact.dc.html` exactly.
- `/about`: hero 2-col — kicker "About", h1 "One founder.<br>Every project.",
  two body paragraphs (FOUNDER.bio facts + "15+ projects… founder on WhatsApp"),
  CTAs View Resume (primary) / LinkedIn / GitHub (ghost) | right: vignesh.webp
  in `.lighten` (mix-blend-mode: lighten) wrapper, radius-lg, 1122×1402;
  "Principles we don't bend" — 4 bordered cards (Direct founder access
  [green wa icon], You own everything [ph:key], Honest fixed pricing
  [ph:receipt], Local and registered [ph:map-pin]); "Verified, not claimed" —
  4 credential cards from CREDENTIALS (+hover border-accent) + MSME strip
  (seal-check · UDYAM-TN-03-0328658 · "Government of India · Udyam
  Registration"); CTA border-top "Talk to Vignesh directly" + WhatsApp +
  ghost "Contact page". AboutPage/Person JSON-LD already in stub.
- `/contact`: kicker "Contact", h1 "Let's Discuss Your Project", sub "Fill this
  in 60 seconds…"; 820px-breakpoint grid (DISTINCT from nav's 900px):
  desktop `1fr 1fr` where left column stacks (A) WhatsApp card (green-tinted
  border, "Fastest: WhatsApp", "Most clients start here…", "Chat on WhatsApp"
  CTA) → (C) info list (phone/email/location/"Vignesh personally replies within
  24 hours" with ph:clock) → (D) "What happens next" numbered ol (01–04) +
  footnote "Questions first? See client proof (/#clients) or read the FAQ
  (/#faq)."; right column = ContactForm (heading "Send an enquiry", intro
  "Vignesh personally replies within 24 hours.", no whatsappAlt) spanning
  3 rows; mobile single column in source order A→form→C→D. ContactPage JSON-LD
  already in stub. The ContactForm component handles all Formspree behavior —
  do not duplicate its scripts, just include it once.
- 404 already VGL-styled — leave unless something is off.

### Phase 6 — Validation & polish
- `npm run build`, `npm run check`, `npm run preview`; Playwright sweep at
  1440/1024/768/390/360/320: `document.documentElement.scrollWidth` must equal
  viewport width on every route; screenshot each page.
- `grep -riE "dc\.html|design-reference|\{\{siteUrl\}\}" dist/` must return nothing.
- Per-route metadata audit: every route ships its own title/description/canonical
  /JSON-LD (no template defaults anywhere).
- Keyboard pass: skip link, mobile menu, FAQ accordion, form focus states;
  reduced-motion pass (emulate via Playwright `reducedMotion: 'reduce'`).
- Final report: changed files per phase + "Assets Required Before Launch":
  1) client-testimonial.mp4 2) client-testimonial-poster.webp 3) n8n video
  poster 4) real project screenshots ×4 5) n8n workflow screenshots ×4 →
  /images/workflow/ 6) real og-cover.png (interim brand card ships today)
  7) real Instagram URL 8) production domain in src/config.yaml.

## Hard rules (from the approved brief — do not violate)

- No `.dc.html` or `design-reference/` links in production output; `{{siteUrl}}`
  never ships literally (derive absolute URLs via `siteUrl()` from config).
- Conditional blocks collapse when data is empty: gallery, video, transcript,
  captions track, quote, price, live URL. Transcript/captions UI never renders
  without content. Never fake screenshots, footage or testimonial content.
- The n8n video embeds ONLY on /projects/ai-whatsapp-automation.
- Formspree: endpoint `meeyzjgw`, AJAX + native POST fallback, plain
  `data-fs-field`, field errors `data-fs-error="name|business_type|whatsapp|service|budget"`,
  global `#vgl-form-error`, `data-fs-success`, disabled "Sending…" state,
  MutationObserver settle — NO fixed reset timers.
- WhatsApp green (#25D366/#3ddc74) for WhatsApp elements only; cyan #7fd4e0 for
  technology only; violet is the primary accent.
- Anchored sections `scroll-margin-top: 84px`; 44px tap targets; WCAG AA;
  `rel="noopener noreferrer"` on all target=_blank; grids
  `repeat(auto-fit, minmax(min(100%, Npx), 1fr))` (320px-safe).
- All facts verbatim from the data modules — no invented claims, prices, or results.

## Environment pitfalls learned in the previous session

- Never write `*/` inside a CSS comment (e.g. glob paths) — it terminates the
  comment and corrupts the stylesheet.
- eslint/prettier/tsconfig already exclude `design-reference/`; ContactForm.astro
  has an eslint override for the Formspree shim — keep both.
- Playwright: `import { chromium } from '<repo>/node_modules/playwright-core/index.mjs'`
  with `executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'`.
  Raw `chrome --headless --screenshot --window-size` reports misleading layout
  widths — use Playwright viewports for overflow checks.
- Git: `git config user.email noreply@anthropic.com && git config user.name Claude`
  before committing. Commits auto-sign via the environment (`commit.gpgsign=true`);
  local `%G?` shows N/B only because ssh-keygen is absent — ignore that.
- If `git push` returns 403: it is a repository write-permission policy denial
  at the session git proxy (reads work, writes refused). Do NOT retry endlessly.
  Tell me to check the Claude GitHub app's write access to
  `Vignesh-10032000/astrowind-main`, and deliver the work meanwhile as
  (a) `git bundle create` of the branch and (b) a source zip (exclude
  node_modules/dist/.git/.astro), sent via file attachment.

## Workflow per phase

Implement → `npx prettier -w` on new files → `npm run build` + `npm run check`
green → Playwright overflow/screenshot spot-check → commit with a descriptive
"Phase N: …" message → push (or bundle fallback) → summarize changed files to me.
Do not start Phase 4 before Phase 3 is committed, etc. Ask me only when a
decision genuinely isn't covered by the design sources or this prompt.
