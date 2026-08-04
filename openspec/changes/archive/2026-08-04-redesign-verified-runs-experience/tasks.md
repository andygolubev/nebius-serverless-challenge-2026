## 1. Baseline and guardrails

- [x] 1.1 Re-read this change's proposal, design, specs, `ARCHITECTURE.md`, the handoff README/reference files, active overlapping changes, and current `IMPLEMENTATION_LOG.MD`; record the exact baseline, commands, observed results, blockers, and safe next step without overwriting unrelated work.
- [x] 1.2 Inventory global token/class consumers and current showcase, detail, route, catalog-order, unit, Playwright, and deployed-smoke assertions; identify broad CSS selectors and shared `ResultPanels` behavior that require compatibility coverage.
- [x] 1.3 Add or update focused tests first for the new server order, compact card fields/accessibility, public routes/footer, light-only token contract, approved static copy, and preserved read-only CTA behavior; confirm each test fails for the intended pre-change reason.

## 2. Part 1 — visual foundation and shared top bar

- [x] 2.1 Replace the root visual tokens with the chosen v2-light ground, ink, border, accent, gradient, Archivo, square-radius, and no-shadow values while retaining compatible light success, danger, warning, disabled, and form states needed by inherited views.
- [x] 2.2 Remove the automatic dark token override, add the specified Archivo 400–800 stylesheet with system fallbacks, and update global focus, button, hover, pressed, skeleton, and typography behavior without introducing a component library or copying prototype HTML.
- [x] 2.3 Restyle the sticky shared top bar at desktop and mobile widths while preserving brand/home, active navigation, authenticated-only Jobs/My Robots links, email display, sign-in, and best-effort sign-out behavior.
- [x] 2.4 Audit Login, Dashboard, My Robots, and owner Job detail under the new tokens for WCAG AA contrast, focus visibility, status semantics, field affordances, clipping, and 375px overflow; repair only compatibility regressions caused by the shared foundation.

## 3. Part 1 — Verified Runs landing page

- [x] 3.1 Rebuild the showcase hero with the approved challenge/free-of-charge copy, explicit two-line heading, both session-aware actions, and the three-step simulate/train/keep pipeline while preserving the existing fetch state and alive guard.
- [x] 3.2 Implement the gallery header and square rule-based responsive grid; derive the run count and first-entry revision from the returned server array and keep the grid usable across 1440px, approximately 1100px, approximately 760px, and 375px widths.
- [x] 3.3 Rebuild each card as one keyboard-operable accessible control showing only index, decorative local avatar, evaluation tag, task, label, description, backend, hardware, criterion, and rollout/detail line; retain the exported formatting helpers for detail/tests.
- [x] 3.4 Add the last-cell session-aware poster CTA, evidence-retention band, and creator-credit statement with the approved copy and flat hover/focus behavior; ensure the poster stays last for seven, partial, and empty result sets.
- [x] 3.5 Preserve and restyle the pending skeletons, existing error alert copy, and left-aligned empty state so each state remains semantically announced and never exposes a gallery submission action.
- [x] 3.6 Reorder the backend `GALLERY_EXAMPLES` construction to G1 Rough Terrain, Go1 Walker, then the existing five-entry relative order; update explicit order fixtures without changing pins, payload fields, evidence gating, or route behavior.

## 4. Part 1 — verification gate

- [x] 4.1 Run focused backend gallery tests and frontend showcase/format tests; verify exact order, all evaluation badge states, loading/error/empty/partial lists, count/revision text, card accessible names, and absence of run/re-run/fork/queue controls.
- [x] 4.2 Run relevant My Robots, Dashboard, Login, Job detail, and stylesheet tests plus the frontend production build; confirm global token changes do not regress authenticated workflows and the system fallback remains usable when Archivo is blocked.
- [x] 4.3 Exercise the Part 1 page with keyboard-only input and capture/compare desktop, intermediate, and 375px browser renders against `Verified Runs v2 light.dc.html`; correct visible spacing, typography, color, grid, focus, and overflow discrepancies before checking off the phase.
- [x] 4.4 Verify existing Playwright text selectors still target unique elements and update selectors only where the approved information hierarchy makes that necessary.

## 5. Part 2 — public run detail and shared result panels

- [x] 5.1 Recompose `ShowcaseDetail` into the gradient back-link/identity/evaluation header and four-cell Backend, Hardware, Timesteps, and Revision rail while retaining API-derived values, loading/error behavior, and empty-media handling.
- [x] 5.2 Apply the two-column result layout, emphasized seven-KPI grid, compact recorded facts, simulator disclosure, gradient bundle callout, rollout player/actions, and media selector without changing `buildResultView`, preferred-video selection, retry, native controls, public URLs, or bundle confirmation.
- [x] 5.3 Restyle Evaluation, Episodes, Result files, Configuration, and Raw diagnostics as accessible ruled accordions/tables with correct open state, labels, narrow-screen reflow, long-value wrapping, and keyboard behavior.
- [x] 5.4 Add the approved closing train-your-own-robot CTA and verify anonymous users enter Login while authenticated users enter My Robots, with no example submission path.
- [x] 5.5 Verify every shared `ResultPanels` change against owner Job detail, including historical gallery Jobs and custom-robot Jobs, so tenant-authorized URLs, identity, evaluation versus completion, media, files, and simulator disclosure remain intact.

## 6. Part 2 — About, Terms, and shared shell footer

- [x] 6.1 Add public `about` and `terms` route variants and rendering branches, include both in `PUBLIC_VIEWS`, and preserve unauthenticated fallback, session expiry, login completion, logout, and active-navigation behavior.
- [x] 6.2 Implement static `About.tsx` from the approved reference copy with hero, project rationale, Find me band, creator credit, and safe external personal-site, LinkedIn, and repository links.
- [x] 6.3 Implement static `Terms.tsx` with all eight owner-approved points verbatim, the emphasized Download your results early item, repository link, closing message, and `Last updated 2 August 2026 · Andy Golubev` attribution.
- [x] 6.4 Move the footer into the application shell, wire About and Terms through route callbacks rather than fragment placeholders, apply the Terms footer background variant, and ensure no view retains a duplicate page-local footer.
- [x] 6.5 Reconcile the shell so the restyled top bar/footer and their session-aware controls remain consistent on showcase, detail, About, Terms, login, and authenticated views without changing page state or adding a new router.

## 7. Part 2 — verification gate

- [x] 7.1 Run focused route/static-view component tests for anonymous access, exact Terms copy, safe external links, footer navigation, session-aware top bar, login cancellation/completion, and authenticated-view protection.
- [x] 7.2 Run `resultView`, showcase detail, media, bundle-confirmation, Job detail, custom-result, and My Robots regression tests; cover success, below-threshold, recorded, no-media, media-error/retry, long metadata, and artifact actions.
- [x] 7.3 Exercise detail, About, Terms, login, and representative authenticated pages with keyboard-only input and compare 1440px, 900px, 760px, and 375px browser renders to the supplied v2-light references; correct focus order, accordion/table reflow, footer layout, clipping, and page-level overflow.
- [x] 7.4 Run the complete frontend unit suite and production build plus the relevant Playwright suite, and record exact pass/fail counts and any intentionally updated selectors in `IMPLEMENTATION_LOG.MD`.

## 8. Integration, delivery, and acceptance

- [x] 8.1 Run the complete relevant backend suite, frontend suite/build, `git diff --check`, tracked secret/large-file checks, and `openspec validate redesign-verified-runs-experience --strict`; leave every task unchecked until its evidence passes.
- [x] 8.2 Review the final diff for accidental API/state/route behavior changes, prototype or generated-file copying, modified avatar assets, third-party images, exposed secrets, and overlap with concurrent active changes.
- [x] 8.3 Commit and push only to `main`, inspect the exact `saas-image.yml` GitHub Actions result and GitOps image bump, and do not infer deployment from a successful local build.
- [x] 8.4 After deployment, run the approved anonymous no-mutation smoke for gallery order/states, card-to-detail navigation, MP4 playback/seeking/retry, bundle confirmation/download, About, Terms, footer/topbar, keyboard focus, and mobile layout; verify signed-in navigation without starting preparation or training.
- [x] 8.5 Record deployment identity, sanitized results, blockers, rollback path, and a final cloud audit in `IMPLEMENTATION_LOG.MD`; confirm no builder, GPU/CPU job, temporary VM, disk, IP, or security rule was created or left running for this UI-only change.
