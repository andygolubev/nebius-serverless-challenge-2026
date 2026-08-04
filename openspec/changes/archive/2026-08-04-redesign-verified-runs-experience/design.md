## Context

The SaaS frontend is a React 18/Vite single-page application with route state in `App.tsx`, one global `styles.css`, and shared result components used by both public `ShowcaseDetail` and authenticated `JobDetail`. The public showcase consumes the existing anonymous `/showcase` and `/showcase/{example_id}` contracts; the backend preserves the declared `GALLERY_EXAMPLES` insertion order. The Claude Design package supplies high-fidelity HTML mockups plus React/CSS references for two phases: Part 1 covers the shared top bar and gallery landing page, and Part 2 covers run detail, About, Terms, and the shared footer.

The implementation must preserve the showcase's strict read-only boundary, current API fields, artifact authorization paths, result derivation, session behavior, and all unrelated worktree changes. It must also account for the fact that replacing global tokens and restyling `ResultPanels` affects login, Dashboard, My Robots, and owner Job detail even when their markup is unchanged.

## Goals / Non-Goals

**Goals:**

- Recreate the chosen light blue/green designs at high fidelity using the existing React and plain-CSS conventions.
- Deliver Part 1 and Part 2 as explicit, independently verifiable task groups within one compatible change.
- Preserve all current data fetching, result interpretation, media, artifact, authentication, and no-gallery-training behavior.
- Keep the public and authenticated application accessible and responsive from 375px mobile through 1440px desktop.
- Make G1 Rough Terrain and Go1 Walker the first two server-ordered gallery entries.

**Non-Goals:**

- New API fields, endpoints, persistence, migrations, or state management.
- Any job submission, re-run, fork, queue, training, image-build, infrastructure, or cloud workflow change.
- Replacing the existing avatar files or copying the prototype HTML into production.
- Redesigning Dashboard, My Robots, Login, or owner Job detail beyond necessary token, shell, and shared-result compatibility work.
- Adding a full URL router or server-side rendering; the new public views use the app's existing route-state pattern.

## Decisions

### Treat the handoff as a visual contract, not production source

Rebuild the reference structure with semantic JSX and named classes in the existing source files. Merge and reconcile the reference CSS into `styles.css` rather than replacing the application wholesale, and compare the result against the chosen v2-light HTML at desktop and responsive widths. The earlier red/Modernist prototype remains excluded.

Alternative considered: copy the generated HTML/CSS verbatim. Rejected because it would bypass existing state, API, accessibility, shared components, and route conventions.

### Introduce the light token set globally and retire automatic dark overrides

Replace the root palette, typography, radius, shadow, and gradient tokens with the handoff's light scheme; remove the `prefers-color-scheme: dark` override and update its regression test. Load Archivo 400–800 from the specified Google Fonts stylesheet in `index.html`, retaining the declared system fallback stack so the app remains usable when the font request is unavailable. Audit every inherited authenticated view for contrast, controls, alerts, overflow, and focus after the token change.

Alternative considered: retain the old dark token override. Rejected because those substitutions break the chosen gradients and the handoff explicitly selects a light-only presentation. Self-hosting Archivo can be substituted later if deployment policy forbids third-party font delivery, but no font binaries are supplied in this change.

### Keep one shell and one route-state model

Extend the `Route` union and `PUBLIC_VIEWS` with `about` and `terms`, render static `About` and `Terms` components, and move the footer into `App.tsx` so it is not duplicated by the gallery. Preserve existing route callbacks, authentication fallback, login completion, logout, and train-your-own behavior. The top bar stays sticky and shared; About and Terms remain accessible without a session. Footer link buttons use route callbacks rather than placeholder fragments, while external profile links remain normal anchors.

Alternative considered: introduce React Router or static backend routes. Rejected because the application already uses local route state and the two pages need neither deep-linking infrastructure nor data fetching.

### Preserve the list's state machine while replacing its composition

Keep `entries`, `failed`, the `useEffect` alive guard, and server-order rendering. Compose the new hero, three-step pipeline, gallery header, square rule-based cards, last poster CTA, evidence band, and creator credit. Cards remain a single accessible button with an explicit label; avatars are decorative within that named control. Loading retains three skeleton cells, errors keep the existing alert copy, and an empty response renders both its explanatory state and the final CTA poster.

Cards intentionally stop displaying duration, cost, timesteps, expected result, and full configuration. Those values remain in the payload and on detail, so exported format helpers and their consumers stay intact.

### Restyle public detail through existing result primitives

Reorder the `ShowcaseDetail` header into the gradient identity block and four-cell meta rail, then style its existing summary, media, bundle, accordions, files, configuration, diagnostics, and closing CTA. Continue to derive all values with `buildResultView`; preserve final-video selection, retry handling, native video controls, public artifact URLs, simulator disclosure, and the confirmation guard.

Because `ResultPanels.tsx` is shared, prefer additive semantic classes or compatible selector changes and verify `JobDetail` after every shared-panel adjustment. No metric count or data-shaping logic changes are planned; if the current seven-KPI invariant changes during implementation, the grid must still have no orphan cell.

### Make the backend order authoritative

Move `g1-rough-terrain` to the first position and `go1-walker` to the second in the tuple that constructs `GALLERY_EXAMPLES`; retain the relative order of Ant, HalfCheetah, Hopper, Walker2D, and Reacher. Update explicit order fixtures/assertions. Do not sort in React, mutate pin identities, or weaken evidence gating.

Alternative considered: reorder the fetched entries in `Showcase.tsx`. Rejected because the existing contract defines server order as canonical for all clients.

### Verify in increasing scope and ship both parts together

Part 1 verification covers catalog order, showcase component states, exact card information hierarchy, keyboard names/focus, responsive gallery, text-based deployed selectors, and inherited-view token regressions. Part 2 adds route/static-copy tests, shared footer navigation, public detail and owner Job result tests, media/bundle safeguards, responsive accordions/tables, and production build. Then run the complete relevant backend/frontend suites, strict OpenSpec validation, and deployed anonymous smoke through the existing `debug-portal` delivery path.

## Risks / Trade-offs

- [Global token replacement makes authenticated pages unreadable or ambiguous] → Inventory legacy token consumers, retain semantic success/danger/warning variables as compatible light values, and test Login, Dashboard, My Robots, and Job detail at mobile and desktop widths.
- [Reference CSS collides with existing broad selectors] → Reconcile duplicate rules deliberately, scope public-only styling beneath semantic page classes where needed, and use shared selectors only for intentional shell/result behavior.
- [Shared `ResultPanels` styling regresses owner Jobs] → Keep component logic unchanged and run `resultView`, Job detail, custom result, and My Robots regression coverage alongside public detail tests.
- [Remote Archivo is blocked or slow] → Keep the system fallback stack and confirm layout remains usable with the font request unavailable.
- [In-memory routes do not support direct URL deep links] → Accept the existing application routing constraint; this change guarantees navigation inside the shell, not new browser-history semantics.
- [Light-only design removes an existing preference feature] → Make the spec/test change explicit and verify contrast in the selected palette rather than silently retaining a broken dark override.
- [The public count can be below seven while curation is incomplete] → Continue deriving count and revision from returned entries, keep empty/loading/error states truthful, and always place the poster last.

## Migration Plan

1. Implement and verify Part 1: tokens/font, shared top bar, landing-page composition, gallery cards/states, server order, and compatibility checks for inherited views.
2. Implement and verify Part 2: detail/result presentation, About and Terms routes/views, shared footer, and owner Job result compatibility.
3. Run focused tests after each phase, then the full relevant backend/frontend suites, production build, strict OpenSpec validation, whitespace checks, and browser checks at representative desktop/mobile widths.
4. Commit and push only on `debug-portal`; inspect the exact GitHub Actions run and GitOps deployment before anonymous production smoke of gallery, detail media/download, About, Terms, navigation, focus, and responsive behavior.
5. Roll back by reverting the frontend/catalog change on `debug-portal`; there is no data or API migration to reverse.

## Open Questions

None. The handoff selects the v2-light direction, supplies the owner-approved About/Terms copy, and explicitly resolves gallery ordering and CTA behavior.
