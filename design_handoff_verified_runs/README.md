# Handoff: Verified Runs page (public showcase) — light blue/green redesign

## Overview
A restyle and restructure of the public, unauthenticated showcase page of **Sim2Policy**
(`saas/frontend/src/views/Showcase.tsx`, rendered by `App.tsx` at route `{ view: "showcase" }`).
It is the first page a visitor sees. Goals, from the designer's brief:

1. Look far more polished and less template-y.
2. Keep the same data — no new API fields, no new endpoints.
3. Say plainly that the project is an entry for the Nebius Serverless Challenge 2026 and is
   free of charge (no credit card, email only).
4. Credit that it was built with passion in weeks by one person working with an LLM.
5. Order the gallery with **G1 Rough Terrain first, Go1 Walker second**.

The page still contains **no control that starts, re-runs, forks or queues a training job** —
that invariant from the current source is preserved. The only call to action is sign-in.

## About the design files
The files in this bundle are **design references authored in HTML** — prototypes that show the
intended look, structure and states. They are **not production code to copy verbatim**. The task
is to recreate them inside the existing app: React 18 + TypeScript + Vite, plain CSS in
`src/styles.css` with CSS custom properties, no CSS framework, no component library.
Use that established pattern (semantic class names in `styles.css`, tokens in `:root`).

`Showcase.reference.tsx` and `showcase.reference.css` in this folder are provided as a
close-to-final starting point in exactly that style — read them, then adapt.

## Fidelity
**High-fidelity.** Final colors, typography, spacing and states. Recreate pixel-accurately.
Two schemes were explored and both are included:

- `Verified Runs v2 light.dc.html` — **the chosen direction**: white ground, soft blue→green
  gradients, teal accent. All values in this README describe this version.
- `Verified Runs.dc.html` — earlier "Modernist" exploration: #f3f2f2 ground, red accent,
  black 2px rules. Kept for reference only; do not implement.

## Scope of change in the codebase

| File | Change |
| --- | --- |
| `saas/frontend/src/styles.css` | Replace the `:root` token block (see **Design tokens**); add the new `.showcase-*` / `.gallery-*` rules from `showcase.reference.css`; delete or retune the `prefers-color-scheme: dark` block — the gradients assume a light ground |
| `saas/frontend/src/views/Showcase.tsx` | New markup for `Showcase` and `ShowcaseCard` (see `Showcase.reference.tsx`). `ShowcaseDetail` is out of scope for this pass but inherits the tokens |
| `saas/frontend/src/App.tsx` | Header/topbar restyle only — same routes, same handlers. Class names `topbar`, `brand`, `brand-dot`, `nav-btn` are reused with new CSS |
| `saas/frontend/index.html` | Add the Archivo webfont link |
| `saas/backend/app/catalog.py` | Reorder `GALLERY_EXAMPLES` so `g1-rough-terrain` is first and `go1-walker` second — the frontend renders `result.examples` in server order |
| `saas/frontend/public/avatars/*.svg` | Unchanged files; they are rendered through a CSS `filter` (see **Assets**) |

No backend contract changes. `formatDuration`, `formatCost`, `formatMetric` and
`formatTimesteps` stay exported from `Showcase.tsx` — the detail view and tests
(`showcaseFormat.test.ts`) still use them, even though the cards no longer show duration/cost.

## Screens / Views

### 1. Top bar (in `App.tsx`, present on every view)
- **Purpose**: brand, primary nav, session state.
- **Layout**: `display:flex; align-items:center; gap:32px; padding:18px 40px;`
  `position:sticky; top:0; z-index:10; background:#ffffff;`
  `border-bottom:2px solid rgba(16,74,82,0.16);` A `flex:1` spacer sits before the right cluster.
- **Brand**: 12×12px square, no radius, `background:linear-gradient(135deg,#1f8ff5 0%,#35c95f 100%)`,
  then the wordmark "Sim2Policy" — Archivo 800, 19px, `letter-spacing:-0.02em`, color #14232b.
- **Nav items**: Archivo 13px, uppercase, `letter-spacing:0.02em`, padding `8px 12px`,
  `border-bottom:3px solid transparent`. Active item: weight 700, color #14232b,
  `border-bottom-color:#17b9a8`. Inactive: weight 600, color #557179; hover color #14232b.
  "Jobs" and "My robots" render only when authenticated (existing `authed` flag).
- **Right cluster**: when authed, the user email at 13px / #557179, then a "Sign out" quiet
  button; when anonymous, one gradient "Sign in" button at 13px.

### 2. Hero
- **Purpose**: state what the page is, how a run happens, and that it is free.
- **Layout**: `max-width:1440px; margin:0 auto; padding:72px 40px 56px;`
  `display:grid; grid-template-columns:minmax(0,1.35fr) minmax(0,1fr); gap:64px; align-items:start;`
  Background wash: `linear-gradient(103deg,#e9f4ff 0%,#eefaf5 46%,#f4fdf7 68%,#ffffff 100%)`.
  Below ~900px collapse to one column and drop the h1 to ~48px.
- **Left column, in order**:
  1. Eyebrow — 12px, weight 700, `letter-spacing:0.16em`, uppercase, color #0d8f83.
     Copy: `Verified training runs · Nebius Serverless Challenge 2026`
  2. `h1` — Archivo 800, 76px, `line-height:0.94`, `letter-spacing:-0.035em`, `text-wrap:balance`,
     color #14232b. Copy: `Watch robots` / `learn to move` (explicit `<br>`).
  3. Lede — 19px, `line-height:1.45`, `max-width:34ch`, color #46626b, `text-wrap:pretty`.
     Copy: `Seven policies trained on real hardware and recorded end to end — policy weights,
     metrics and rollout video. Browse them freely, then bring your own robot.`
  4. Button row — `display:flex; gap:12px; margin-top:32px`. Primary gradient button
     `Browse the seven runs` (anchor to the gallery); quiet button
     `Sign in to train your own` (calls the existing `onSignIn`).
  5. Free-of-charge note — `margin-top:28px; padding-top:16px;`
     `border-top:2px solid rgba(16,74,82,0.16); max-width:46ch;` 15px, `line-height:1.5`,
     color #46626b. Copy: `This is my project for the **Nebius Serverless Challenge 2026** — so it
     is free of charge for you. No credit card. Just your email, and you get a personal space
     where you can train your own robots.` ("Nebius Serverless Challenge 2026" is `<strong>`,
     weight 700, color #14232b.)
- **Right column — "How a run happens"** (`border-top:2px solid rgba(16,74,82,0.16); padding-top:20px`):
  label at 11px / 700 / `0.16em` / uppercase / #557179, then three rows.
  Each row: `display:grid; grid-template-columns:44px 1fr; gap:16px; padding:18px 0;`
  with `border-bottom:1px solid rgba(16,74,82,0.12)` on the first two.
  Numeral: Archivo 800, 15px, color #17b9a8. Title: Archivo 700, 17px. Body: 14px, #557179.
  1. **01 Simulate** — MuJoCo physics — no physical robot, no lab time.
  2. **02 Train** — PPO as a serverless AI job — SB3 on CPU, MJX/JAX on GPU.
  3. **03 Keep** — Policy, metrics and rollout video land in durable storage — the machine can go away.

### 3. Gallery header strip
`max-width:1440px; padding:0 40px`, a `border-top:2px solid rgba(16,74,82,0.16)`, then a
`display:flex; align-items:baseline; justify-content:space-between; padding:20px 0 28px` row:
- `h2#gallery` "The gallery" — Archivo 800, 26px, `letter-spacing:-0.02em`.
- Right meta — 13px, 600, `letter-spacing:0.08em`, uppercase, #557179.
  Copy: `7 runs · revision gallery-v1-2026-07-14` (count from `entries.length`,
  revision from `acceptance_revision` of the first entry).

### 4. Gallery grid (the core of the redesign)
- **Container**: `display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr));`
  **`gap:0`**, `border-top:2px solid rgba(16,74,82,0.16); border-left:2px solid rgba(16,74,82,0.16);`
  `max-width:1440px; margin:0 auto 88px; padding:0 40px;` (the padding sits on a wrapper so the
  rules meet the content edge). Four cells across at 1440px.
- **Cell (each card)**: `display:flex; flex-direction:column; gap:14px; padding:24px;`
  `border-right` + `border-bottom: 2px solid rgba(16,74,82,0.16)`. **No radius, no shadow,
  no lift on hover.** The whole cell is the click target (keep the current single-`<button>`
  or an `<a>`; keep `aria-label={\`${entry.label} — ${entry.task}\`}`).
  Hover: `background:linear-gradient(180deg,#f4fbff 0%,#f3fdf7 100%)`.
  Focus-visible: `outline:2px solid #17b9a8; outline-offset:2px`.
- **Card contents, top to bottom**:
  1. Row: index label (`01`…`07`, Archivo 800, 13px, `letter-spacing:0.1em`, color #a8bec2,
     from the array index) and, right-aligned, the evaluation tag.
  2. Avatar `<img>` 64×64, `filter:grayscale(1) contrast(1.05) sepia(0.35) hue-rotate(120deg)
     saturate(2.2) brightness(1.02)` — recolors the indigo SVGs into the green/teal palette.
     `alt=""` (decorative; the label is in the card's accessible name).
  3. Task eyebrow — 11px, 700, `letter-spacing:0.14em`, uppercase, #0d8f83 (`entry.task`).
  4. Title `h3` — Archivo 800, 23px, `line-height:1.1`, `letter-spacing:-0.02em` (`entry.label`).
  5. Description — 14px, `line-height:1.45`, #46626b, `text-wrap:pretty` (`entry.description`).
  6. `dl` pushed to the bottom (`margin-top:auto`), `padding-top:14px`,
     `border-top:1px solid rgba(16,74,82,0.12)`, rows `display:flex; justify-content:space-between; gap:12px`
     with `gap:8px` between rows. `dt`: 11px, 600, `0.1em`, uppercase, #6b868d.
     `dd`: 13px, 700, right-aligned. Three rows only:
     **Backend** `entry.backend_label` · **Hardware** `entry.hardware_label` ·
     **Criterion** `entry.evaluation.criterion`.
     (Duration, cost, timesteps and `expected_result` were deliberately dropped from the card —
     they remain on the detail page.)
  7. Link line — 12px, 800, `letter-spacing:0.08em`, uppercase, #0d8f83.
     `Watch the rollout →` when `entry.has_media`, else `Inspect the run →`.
- **Evaluation tag** (`.v2-tag`): `padding:4px 10px`, 11px, 700, `letter-spacing:0.06em`,
  uppercase, color #0a6f66, `background:linear-gradient(100deg,#e6f4ff 0%,#e4fbef 100%)`,
  `border:1px solid rgba(16,74,82,0.14)`, no radius.
  `evaluation.success === true` → "Met task threshold"; `false` → "Below task threshold"
  (same tag, color #8a3b1c on `linear-gradient(100deg,#fff3e6,#ffeede)`);
  `null` → "Recorded run" (neutral: #557179 on #f4f7f8). Keep `title={criterion}`.
- **Eighth cell — the CTA poster** (a grid cell, not a separate section, so the grid stays full):
  `background:linear-gradient(140deg,#1f8ff5 0%,#17b9a8 52%,#35c95f 100%); color:#ffffff;`
  `display:flex; flex-direction:column; justify-content:space-between; gap:24px; padding:24px;`
  same 2px right/bottom rules. Contents:
  kicker `Your turn` (11px, 700, `0.16em`, uppercase); statement `Bring your own robot.`
  (Archivo 800, 30px, `line-height:1.02`, `letter-spacing:-0.03em`); body 14px
  `Free of charge — no credit card. Give an email, get a personal space, upload a model, build a
  bounded environment and train it.`; then a white button `Sign in to train →`
  (color #0a6f66, `align-self:flex-start`) wired to `onSignIn`.
  With 7 entries this fills a 4-across grid exactly. If the entry count changes, the poster
  should stay the **last** cell.

### 5. "What every run leaves behind" band
`border-top:2px solid rgba(16,74,82,0.16); background:linear-gradient(170deg,#f3fbff 0%,#f1fbf4 100%);`
inner `max-width:1440px; padding:56px 40px 64px`. A label (11px/700/0.16em/uppercase/#557179,
`margin-bottom:32px`) then `display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:40px`.
Each column: `border-top:2px solid rgba(16,74,82,0.16); padding-top:16px`,
`h3` Archivo 800 22px `letter-spacing:-0.02em`, body 15px #46626b `text-wrap:pretty`.
1. **A policy you can replay** — Checkpoint weights and the exact executed configuration — environment, algorithm, timesteps, seed.
2. **Measured, not claimed** — Observed runtime and cost recorded from the job itself, next to the success criterion it was judged against.
3. **A rollout video** — Rendered from the trained policy, so the result is watchable and not only a number on a chart.

### 6. "Built with passion and love" statement
`border-top:2px solid rgba(16,74,82,0.16);`
`background:linear-gradient(100deg,#ffffff 0%,#f1fbf5 60%,#e9f4ff 100%);`
inner `max-width:1440px; padding:56px 40px 64px; display:grid;`
`grid-template-columns:minmax(0,1fr) minmax(0,1.3fr); gap:64px; align-items:start`.
Left: label `Built with passion and love` (11px, 700, `0.16em`, uppercase, #0d8f83).
Right: Archivo 800, 34px, `line-height:1.12`, `letter-spacing:-0.025em`, `text-wrap:pretty` —
`Simulation, training, storage, deployment and this page — built in weeks by one person with an
LLM. That is the time we live in, and I loved every hour of it.`

### 7. Footer
`border-top:2px solid rgba(16,74,82,0.16); background:#ffffff;` inner
`max-width:1440px; padding:24px 40px 40px; display:flex; flex-wrap:wrap; gap:24px;`
`justify-content:space-between; align-items:baseline`. Three items:
1. Wordmark `Sim2Policy` — Archivo 800, 15px.
2. `<nav aria-label="Footer">` with `display:flex; gap:24px`: **About me** and **Terms of use** —
   12px, 700, `letter-spacing:0.08em`, uppercase, #0d8f83, underline on hover.
   Routes do not exist yet — add `{ view: "about" }` and `{ view: "terms" }` to the `Route`
   union and to `PUBLIC_VIEWS`, or point them at static pages. Placeholders in the mock are
   `#about` / `#terms`.
3. Meta line `Nebius Serverless Challenge 2026` — 12px, `letter-spacing:0.08em`, uppercase, #557179.

## Interactions & behavior
- **Card click** → existing `onOpenExample(entry.id)` → `{ view: "showcase-example", id }`. Unchanged.
- **Any CTA** → existing `onSignIn` (`trainYourOwn` in `App.tsx`): authenticated users go to
  My Robots, anonymous users to Login. Unchanged.
- **Hover**: cards take the light gradient tint; buttons `filter:saturate(1.15) brightness(1.04)`;
  pressed `filter:brightness(0.94)`. Transitions: `background 0.15s ease, filter 0.15s ease`.
  No transform, no shadow — the design is flat.
- **Focus**: `:focus-visible { outline:2px solid #17b9a8; outline-offset:2px }` globally;
  never leave the browser default.
- **Loading** (`entries === null`): keep the existing three `.skeleton` blocks at `height:20rem`
  inside the grid, but square (radius 0) and shimmering between #f2fbf9 and rgba(16,74,82,0.10).
- **Error** (`failed`): keep the existing `.alert-error` role="alert" copy verbatim.
- **Empty** (`entries.length === 0`): keep the existing `.empty-state` copy; left-align it and
  still render the poster CTA cell.
- **Responsive**: the grid is `auto-fit`/`minmax(300px,1fr)` — 4 across ≥1440px, 3 ≈1100px,
  2 ≈760px, 1 below. Under 900px the hero becomes one column (pipeline block below the copy),
  the h1 drops to ~48px, and section padding goes to `40px 20px`. Under 640px the three-column
  band stacks.

## State management
No new state. `Showcase` keeps exactly what it has today:
`entries: ShowcaseEntry[] | null` and `failed: boolean`, filled by `api.showcase()` in a
`useEffect` with the existing `alive` guard. `authed` arrives as a prop. Card order comes from
the server array — do the reordering in `catalog.py`, not in the component.

## Design tokens (v2 light)
```css
:root {
  /* ground + ink */
  --bg:            #ffffff;
  --surface:       #ffffff;
  --surface-2:     #f2fbf9;   /* hover / tinted fill */
  --border:        rgba(16,74,82,0.16);  /* 2px structural rules */
  --border-soft:   rgba(16,74,82,0.12);  /* 1px rules inside cards */
  --text:          #14232b;
  --text-muted:    #557179;
  --text-body:     #46626b;   /* paragraph ink on white */
  --text-faint:    #6b868d;   /* dt labels */
  --text-ghost:    #a8bec2;   /* card index numerals */

  /* accent */
  --accent:        #0d8f83;   /* links, eyebrows, text-size accent (AA on white) */
  --accent-strong: #0a6f66;   /* pressed / text on tinted fill */
  --accent-mid:    #17b9a8;   /* focus ring, active nav rule, numerals */
  --blue:          #1f8ff5;
  --green:         #35c95f;

  /* gradients */
  --grad-action:   linear-gradient(100deg, #1f8ff5 0%, #17b9a8 55%, #35c95f 100%);
  --grad-poster:   linear-gradient(140deg, #1f8ff5 0%, #17b9a8 52%, #35c95f 100%);
  --grad-hero:     linear-gradient(103deg, #e9f4ff 0%, #eefaf5 46%, #f4fdf7 68%, #ffffff 100%);
  --grad-band:     linear-gradient(170deg, #f3fbff 0%, #f1fbf4 100%);
  --grad-credit:   linear-gradient(100deg, #ffffff 0%, #f1fbf5 60%, #e9f4ff 100%);
  --grad-tag:      linear-gradient(100deg, #e6f4ff 0%, #e4fbef 100%);
  --grad-hover:    linear-gradient(180deg, #f4fbff 0%, #f3fdf7 100%);

  /* type */
  --font: "Archivo", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono: ui-monospace, "SF Mono", "Cascadia Code", monospace;

  /* radius + elevation: none, on purpose */
  --radius-sm: 0; --radius: 0; --radius-lg: 0;
  --shadow: none; --shadow-lg: none;
}
```
Type scale actually used: 76 / 34 / 30 / 26 / 23 / 22 / 19 / 17 / 15 / 14 / 13 / 12 / 11 px.
Weights: 800 (Archivo, all display and titles), 700 (labels, dd, buttons), 600, 400.
Spacing scale: 4, 8, 12, 14, 16, 20, 24, 32, 40, 56, 64, 72, 88 px.
Uppercase micro-labels always carry letter-spacing 0.08–0.16em.

Contrast: #0d8f83 on #ffffff ≈ 4.0:1 — fine for the 11–13px bold uppercase labels and links used
here. Do **not** use #17b9a8 or #35c95f for text; they are structural/decorative only.

## Assets
- `avatars/*.svg` — the seven existing files from `saas/frontend/public/avatars/`, unmodified.
  They are indigo (#4f46e5 / #312e81 / #e0e7ff) and are recolored **in CSS** by the filter listed
  above so they sit in the blue/green palette. If you prefer, re-author the SVG fills to
  #1f8ff5 / #0a6f66 / #e6f4ff and drop the filter — visually equivalent, cheaper to render.
- **Archivo** from Google Fonts, weights 400/500/600/700/800:
  `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&display=swap">`
  Self-host it if the deployment must avoid third-party requests.
- Icons: none are used. If any are added later, use Lucide.
- No photography.

## Files in this bundle (part 1)
- `Verified Runs v2 light.dc.html` — **the design to implement**. Open in a browser.
- `Verified Runs.dc.html` — the earlier red/Modernist exploration, reference only.
- `Showcase.reference.tsx` — close-to-final React for `views/Showcase.tsx` (the list view and card).
- `showcase.reference.css` — the CSS to merge into `src/styles.css`.
- `avatars/` — the seven avatar SVGs, as shipped today.

## Suggested order of work (part 1)
1. Tokens + Archivo in `styles.css` / `index.html`; remove the dark-scheme block. Check every
   view still reads (Dashboard, MyRobots, JobDetail inherit the tokens).
2. Topbar restyle in `App.tsx` + CSS.
3. Gallery grid and card (`showcase.reference.css` + `Showcase.reference.tsx`).
4. Hero, poster cell, the two closing bands, footer links.
5. Reorder `GALLERY_EXAMPLES` in `catalog.py`; confirm `saas/backend/tests/test_gallery.py`
   and `frontend/src/views/showcaseFormat.test.ts` still pass, and that the Playwright
   `e2e/deployed-smoke.spec.ts` selectors still match (they key off text, not classes — verify).
6. Add `about` / `terms` routes, or point the footer links at real destinations.

---

# Part 2 — Run detail, About me, Terms of use

Added after the gallery page. Same tokens, same chrome (topbar + footer), same CSS conventions.
Design files: `Run Detail v2 light.dc.html`, `About Me v2 light.dc.html`, `Terms v2 light.dc.html`.
Reference code: `Detail.reference.css`, `About.reference.tsx`, `Terms.reference.tsx`.

## Routing changes (`App.tsx`)
Add two public views; everything else stays as it is.

```ts
type Route =
  | { view: "showcase" }
  | { view: "showcase-example"; id: string }
  | { view: "about" }      // new
  | { view: "terms" }      // new
  | { view: "login" }
  | { view: "dashboard" }
  | { view: "robots" }
  | { view: "job"; id: string };

const PUBLIC_VIEWS = new Set<Route["view"]>(["showcase", "showcase-example", "about", "terms", "login"]);
```
The footer lives in the shell (it is identical on every page), so lift it out of `Showcase` into
`App.tsx` if you prefer — its two links call `setRoute({ view: "about" })` / `{ view: "terms" }`.
Both pages are static: no props, no fetch, no state.

## 8. Run detail page (`ShowcaseDetail` in `views/Showcase.tsx` + `ResultPanels.tsx`)
Same data and same component decomposition as today — `buildResultView(detail.metrics, …)`,
`MediaPanel`, `MetricDetails`, `EpisodeDetails`, `ArtifactFiles`, `BundleCallout`,
`SimulatorDisclosure`, `KeyValue`. **No logic changes**; this is a restyle plus a re-ordered header.
All values shown in the mock are placeholder numbers — keep reading them from the API.

- **Back link**: 12px, 700, `0.08em`, uppercase, #0d8f83. Copy: `← Back to verified runs`.
- **Run header** sits on the hero wash (`--grad-hero`), inner `max-width:1440px; padding:28px 40px 48px`:
  - identity row `display:flex; justify-content:space-between; gap:32px; margin-top:28px`;
    avatar 80×80 with the same recolor filter; eyebrow `Verified example · Recorded run`;
    `h1` Archivo 800 **52px** `line-height:1.0` `letter-spacing:-0.03em` = `detail.label`;
    below it 19px #46626b — `{task} — {description}`. The evaluation tag is right-aligned
    (`white-space:nowrap`).
  - **meta rail**: `dl` `display:flex; flex-wrap:wrap; border-top:2px solid var(--border); margin-top:36px`,
    each cell `flex:1 1 200px; padding:16px 24px 0 0`; `dt` 11px/600/0.1em/uppercase/#6b868d,
    `dd` Archivo 800 17px. Four cells: Backend, Hardware, Timesteps
    (`formatTimesteps(executed_config.total_timesteps)`), Revision (`acceptance_revision`).
- **Simulator-only note** (`SimulatorDisclosure`): `padding:16px 20px`, `--grad-tag` background,
  `1px solid rgba(16,74,82,0.14)`, no radius. Bold lead `Simulator-only policy.` then the existing
  sentence in #46626b. Copy unchanged from source.
- **Two columns**: `display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.15fr); gap:48px`
  (summary left, media right). Stack under 1000px.
- **KPI grid** — `display:grid; grid-template-columns:repeat(2,minmax(0,1fr));`
  `border-left:1px solid var(--border-soft)`, each cell `padding:18px 20px` with
  `border-right`/`border-bottom: 1px solid var(--border-soft)`. The **first** KPI
  (`emphasis: true` → Mean reward) takes `grid-column: span 2` and a
  `linear-gradient(160deg,#f3fbff,#f1fbf4)` fill, value at Archivo 800 **40px** in #0a6f66;
  the other six are single cells with 22px values (16px for the long checkpoint string).
  `resultView` returns exactly 7 KPIs → 2 + 6 units = 4 full rows, no empty cell. **If you add or
  remove a KPI, keep the unit count even.** Labels 11px/600/0.1em/uppercase/#6b868d.
- **Compact facts** below it (`.v2-kv`, one column): Success criterion, Primary metric,
  Observed duration, Observed cost — `dt` 12px uppercase #6b868d, `dd` 13px/700 right-aligned,
  each row `border-bottom:1px solid var(--border-soft)`.
- **Bundle callout** (`BundleCallout`): full-width `--grad-poster` block, `padding:22px 24px`,
  white type; left `Policy bundle ready` (Archivo 800 20px) + the existing sentence plus the file
  size at 14px; right a white button `Download policy bundle` (`.btn-invert`). Keep the existing
  `window.confirm(SIMULATOR_ONLY_NOTICE)` guard on the anchor.
- **Media panel** (`MediaPanel`): heading row (eyebrow `Policy rollout`, `h2` = selected artifact
  name at Archivo 800 26px, right-aligned `formatBytes(size)` at 12px uppercase #6b868d) over a
  `border-bottom:2px solid var(--border)`. Then the `<video controls preload="metadata">` at
  `aspect-ratio:16/9`, `width:100%`, no radius, on a
  `linear-gradient(150deg,#14232b,#0d3b45 55%,#0a5a52)` backdrop (the mock draws a play glyph
  where the native player renders). Below: the three quiet buttons Play / Open media / Download,
  then the `role="radiogroup"` selector — one bordered strip, each button
  `flex:1 1 200px; padding:10px 16px`, dividers `1px solid var(--border)`; the selected button gets
  `--grad-tag` + #0a6f66 + weight 700, others white/#557179 with a #f2fbf9 hover.
  Keep the error alert and `Retry playback` button, and the `no-media` fallback sentence.
- **Accordions** (`MetricDetails`, `EpisodeDetails`, `ArtifactFiles`, Configuration, Raw diagnostics):
  each `<details>` has `border-top:2px solid var(--border)` (the last one also `border-bottom`);
  `summary` is `display:flex; justify-content:space-between; padding:18px 0; cursor:pointer`,
  marker hidden, `strong` Archivo 800 18px, `span` 12px/600/0.08em/uppercase/#6b868d, and a
  `::after` `+` in #0d8f83 that becomes `–` when `[open]`. Bodies use `.v2-kv`
  (`repeat(auto-fill,minmax(280px,1fr))`, `gap:0 40px`, rows ruled at 1px). Evaluation is
  `defaultOpen`. Episodes render as a 5-column grid table: header row on
  `linear-gradient(100deg,#f3fbff,#f1fbf4)` with 11px uppercase labels, body rows 13px/700 with
  1px rules, outcome "Completed" tinted #0a6f66. Result files: a plain `ul`, one ruled row each —
  name 14px/700 over size 12px #6b868d on the left, `Open` / `Download` links (12px, 700, 0.08em,
  uppercase) on the right. Raw diagnostics: `<pre>` on #f6fbfa with a 1px border, 12px mono,
  `line-height:1.6`, `overflow-x:auto`.
- **Closing CTA** (`aside`): `--grad-poster`, `padding:32px`, white; left
  `Want a policy for your own robot?` (Archivo 800 26px) + `Free of charge — no credit card. Just
  your email, and you get a personal space to train in.` (15px); right a white button
  `Sign in to train your own →` wired to the existing `onSignIn`.

## 9. About me page (new — `views/About.tsx`)
Static page, no props. Sections top to bottom:
1. **Hero** on `--grad-hero`, `padding:72px 40px 56px`, one flush-left column:
   eyebrow `About me`; `h1` **Andy Golubev** (Archivo 800, 76px, `line-height:0.94`,
   `letter-spacing:-0.035em`); lede 19px #46626b `max-width:40ch` —
   `I built Sim2Policy on my own for the Nebius Serverless Challenge 2026 — simulation, training,
   storage, the API, the deployment and this website.`; then a button row (`gap:10px`):
   gradient `andygolubev.com →` → https://andygolubev.com/ ; quiet `LinkedIn` →
   https://www.linkedin.com/in/andy-golubev/ ; quiet `GitHub repository` →
   https://github.com/andygolubev/nebius-serverless-challenge-2026
   (external links get `target="_blank" rel="noreferrer"`).
2. **Why this project exists** — a 2px rule, then
   `display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.6fr); gap:64px`:
   left an 11px uppercase label, right three paragraphs (21px lead in #14232b, then two at 17px
   in #46626b). Copy is in `About.reference.tsx`.
3. **Find me** band on `--grad-band`: label `Find me`, then three ruled columns
   (`repeat(3,minmax(0,1fr)); gap:40px`, each `border-top:2px` + `padding-top:16px`), each an
   `<a>` with an Archivo 800 22px title (Personal site / LinkedIn / Source code) and the bare URL
   at 15px in #0d8f83 with `overflow-wrap:anywhere`.
4. **Built with passion and love** — the same statement block as the gallery page (reuse
   `.credit`), so the two pages end identically.
5. Footer.

## 10. Terms of use page (new — `views/Terms.tsx`)
Static page. Hero on `--grad-hero`: eyebrow `Terms of use · Nebius Serverless Challenge 2026`,
`h1` **The short version** (76px), lede `Eight points, plain language, no lawyers involved. If
something here matters to you, read it before you sign in.`

Then a list on a `border-top:2px` container; **each item** is
`display:grid; grid-template-columns:88px minmax(0,1fr) minmax(0,1.4fr); gap:32px; padding:32px 0`
with `border-bottom:1px solid var(--border-soft)` (the last item 2px): numeral (Archivo 800, 15px,
`0.1em`, #17b9a8), `h2` (Archivo 800, 24px, `line-height:1.15`, `letter-spacing:-0.02em`), body
(17px, `line-height:1.55`, #46626b). Item **06** is highlighted: `--grad-tag` background, body ink
#14232b, and 20px inner padding on the numeral and the paragraph. Under 900px collapse to one
column per item (numeral above the heading).

Exact copy (verbatim, from the site owner):
1. **Who made this** — I am the creator: **Andy Golubev**. Sim2Policy is my personal project for the Nebius Serverless Challenge 2026 — not a company, not a product.
2. **The results are yours** — Anything trained on this site — policies, checkpoints, metrics, videos — can be used by anyone, for anything. No licence to ask for, no attribution required.
3. **No guarantees at all** — I do not promise that training works, that it keeps working, or that any result is correct. Everything here is provided as is. You use it at your own risk.
4. **I am not responsible for what you do with it** — That includes harmful use. What you train and where you deploy it is your decision and your responsibility. These are simulator-only policies and are not directly deployable to physical hardware.
5. **Your email, and only your email** — I use it for one thing: creating your personal space so your training results have somewhere to live. No marketing, no sharing, no selling. It is erased when this project ends — by the end of 2026, possibly sooner.
6. **Download your results early** — I do not guarantee storage of anything you train. Files can disappear when the project ends or before that. Please download what you care about as soon as it is ready.
7. **Open source** — The whole thing is on GitHub — read it, run it, fork it: github.com/andygolubev/nebius-serverless-challenge-2026
8. **These terms can change** — Without notice — I have probably forgotten something important and will add it later. Sorry about that.

Closing, after the list: `Be happy and enjoy your day.` at Archivo 800 **40px**,
`letter-spacing:-0.03em`, color #0a6f66, `margin-top:56px`; under it
`Last updated 2 August 2026 · Andy Golubev` at 13px/600/0.08em/uppercase/#557179.
This page's footer sits on `--grad-credit` instead of white.

## Order of work for part 2
1. `Detail.reference.css` into `styles.css`; restyle `ShowcaseDetail` + `ResultPanels` (no logic edits).
2. Add the `about` / `terms` routes and the two static views from the reference files.
3. Move the footer into the shell so all four pages share it.
4. Check `resultView.test.ts`, `my-robots.test.tsx` and the Playwright specs still pass —
   `JobDetail.tsx` shares `ResultPanels`, so verify the owner's job page too.

## All files in this bundle
- `Verified Runs v2 light.dc.html` — gallery page (implement)
- `Run Detail v2 light.dc.html` — run detail page (implement)
- `About Me v2 light.dc.html` — About me page (implement)
- `Terms v2 light.dc.html` — Terms of use page (implement)
- `Verified Runs.dc.html` — early red/Modernist exploration (reference only, do not build)
- `Showcase.reference.tsx`, `showcase.reference.css` — gallery reference code
- `Detail.reference.css`, `About.reference.tsx`, `Terms.reference.tsx` — part-2 reference code
- `avatars/` — the seven avatar SVGs as shipped today
