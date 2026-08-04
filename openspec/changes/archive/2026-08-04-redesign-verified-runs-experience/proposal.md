## Why

The public showcase is the first experience for challenge visitors, but its current presentation does not clearly communicate the project story, the free bring-your-own-robot path, or the quality of the verified evidence. The supplied Claude Design handoff provides a coherent light blue/green direction for the gallery, run detail, and supporting public pages that should be implemented as one accessible, responsive experience.

## What Changes

- Restyle the shared application chrome and design tokens around the chosen light-only Archivo, blue, green, and teal visual system while preserving readability across authenticated views that inherit those tokens.
- Restructure the Verified Runs landing page with the new hero, run pipeline, compact evidence cards, final poster CTA, evidence band, creator credit, and shared footer while retaining existing loading, error, empty, keyboard, and sign-in behavior.
- Simplify gallery cards to the task story, evaluation state, backend, hardware, and criterion; keep duration, cost, timesteps, expected result, configuration, and artifacts available on run detail.
- Restyle the read-only run detail and shared result panels without changing result derivation, artifact URLs, media behavior, simulator disclosure, bundle confirmation, or owner Job result logic.
- Add public About me and Terms of use views, route them through the existing client-side shell, and expose them from a footer shared by public and authenticated pages.
- Change the server-owned gallery order so `g1-rough-terrain` is first and `go1-walker` is second, with the remaining five examples retaining their relative order.
- Add focused component, contract, responsive, accessibility, and deployed-smoke coverage for both parts of the handoff.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `saas-web-ui`: Replace the dark-aware visual contract with the chosen light presentation; redefine the showcase card and run-detail information hierarchy; and add public About, Terms, shared footer, and responsive navigation behavior.
- `trainable-examples-gallery`: Make G1 Rough Terrain and Go1 Walker the first two entries in the documented server order while preserving the seven stable identities and evidence-only behavior.

## Impact

- Frontend: `saas/frontend/src/styles.css`, `index.html`, `App.tsx`, `views/Showcase.tsx`, `views/ResultPanels.tsx`, two new static views, and their tests/Playwright coverage.
- Backend: `saas/backend/app/catalog.py` and gallery order assertions only; response fields, endpoints, evidence gates, pinning, and orchestration remain unchanged.
- Dependencies/assets: Archivo is added as a webfont with system fallbacks; existing same-origin avatar SVGs remain unchanged and are recolored in CSS.
- Operations: delivery continues through `debug-portal`; implementation requires normal frontend/backend gates and anonymous deployed checks but no training jobs, GPU work, infrastructure change, or data migration.
