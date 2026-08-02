## MODIFIED Requirements

### Requirement: Visual design system
The web app SHALL use one consistent light visual system across public and authenticated surfaces: the chosen white, blue, green, and teal token palette; Archivo with system fallbacks; a consistent type and spacing scale; square structural rules; accessible contrast (WCAG AA); visible teal `:focus-visible` treatment; keyboard-operable controls; and responsive layouts usable from 375px mobile through desktop. The app SHALL NOT substitute a dark token set in response to `prefers-color-scheme`. Loading, error, empty, hover, pressed, and selected states SHALL be designed and SHALL remain distinguishable without motion, shadow, or color alone.

#### Scenario: Operating system requests dark mode
- **WHEN** the user's OS is set to dark mode
- **THEN** public and authenticated views retain the selected light palette and every text, control, alert, and focus state remains readable

#### Scenario: Mobile layout
- **WHEN** the app is viewed at 375px width
- **THEN** showcase, detail, About, Terms, login, My Robots, Jobs, and dashboard remain usable without page-level horizontal scrolling

#### Scenario: Webfont is unavailable
- **WHEN** Archivo cannot be loaded from its stylesheet provider
- **THEN** the declared system fallback renders every view without hidden controls, clipped essential text, or layout failure

### Requirement: Public showcase is the unauthenticated landing experience
The web app SHALL render the showcase to a visitor with no session as the default application-root view, without redirecting to login or flashing a login screen. It SHALL identify Sim2Policy as a free Nebius Serverless Challenge 2026 project, explain the simulate/train/keep pipeline, credit that it was built in weeks by one person with an LLM, and present the server-ordered published entries in a responsive evidence gallery. Each card SHALL show its index, decorative local avatar within an accessible card control, task, label, description, evaluation state, backend, hardware, criterion, and rollout/detail link line. Duration, cost, timesteps, expected result, and full configuration SHALL remain available on detail rather than on the compact card. The gallery SHALL end with the sign-in/My Robots poster CTA and SHALL include the evidence-retention and creator-credit bands.

#### Scenario: Visitor arrives without an account
- **WHEN** a person with no stored session opens the application root
- **THEN** the polished hero, free-of-charge challenge context, pipeline, published gallery, and sign-in path render without a blocking login prompt

#### Scenario: Visitor inspects an example card
- **WHEN** a visitor focuses or selects a published card
- **THEN** its accessible name contains the example label and task, the compact evidence fields are readable, and selection opens the existing read-only result view

#### Scenario: Showcase is loading or fails
- **WHEN** the showcase request is pending or fails
- **THEN** the gallery presents square skeleton cells or the existing human-readable error alert respectively, without exposing raw diagnostics

#### Scenario: Showcase is empty
- **WHEN** no curated run has been published yet
- **THEN** the showcase shows the designed left-aligned preparation message and still renders the final sign-in/My Robots poster CTA

#### Scenario: Showcase is responsive and keyboard-operable
- **WHEN** the showcase is used at 375px width or with keyboard-only input
- **THEN** navigation, hero actions, card browsing, the final poster CTA, and footer links remain operable without horizontal scrolling

## ADDED Requirements

### Requirement: Public run detail prioritizes recorded evidence
The public showcase detail SHALL retain the existing anonymous data and artifact behavior while presenting a gradient identity header, evaluation state, backend, hardware, timesteps, revision, simulator-only disclosure, KPI summary, recorded facts, policy-bundle action, primary rollout player, selectable media, expandable evidence sections, and closing train-your-own-robot CTA. Values SHALL continue to come from the API and `buildResultView`; placeholder values from the design files SHALL NOT enter production logic.

#### Scenario: Visitor opens a completed run
- **WHEN** an anonymous visitor opens a published showcase example
- **THEN** the identity and evaluation evidence appear before diagnostics, the final rollout is primary when present, and configuration, episodes, files, and raw diagnostics remain inspectable in labeled sections

#### Scenario: Visitor downloads the policy bundle
- **WHEN** a published run has a validated policy bundle and the visitor selects its download action
- **THEN** the existing simulator-only confirmation is shown and the existing public download URL is used only after confirmation

#### Scenario: Public detail is used on a narrow screen
- **WHEN** the detail is viewed at 375px width
- **THEN** its header, meta rail, KPI cells, player, media selector, accordion content, episode rows, artifact actions, and closing CTA remain readable and keyboard-operable without page-level horizontal scrolling

#### Scenario: Shared result panels render an owner Job
- **WHEN** the same result-panel components render an authenticated historical, gallery-associated, or custom-robot Job
- **THEN** its existing identity, authorization, metrics, media, artifacts, disclosures, and actions remain present and functional under the new visual treatment

### Requirement: Shared public chrome and informational views
The application shell SHALL provide the restyled sticky top bar and shared footer navigation with consistent session-aware controls. It SHALL expose About me and Terms of use as public client-side views without fetching data or requiring authentication. About SHALL use the owner-approved biography and external profile/source links; Terms SHALL render all eight owner-approved points verbatim, highlight the download-early warning, and show the specified last-updated attribution. Footer navigation SHALL open these views from the shared shell, and external links SHALL open safely with `rel="noreferrer"`.

#### Scenario: Anonymous visitor opens About
- **WHEN** an unauthenticated visitor activates About me in the footer
- **THEN** the About view opens within the shared chrome and presents the project rationale, creator credit, and working external profile/source links without requesting a session

#### Scenario: Anonymous visitor opens Terms
- **WHEN** an unauthenticated visitor activates Terms of use in the footer
- **THEN** the Terms view opens within the shared chrome with all eight approved points, the emphasized download warning, and the 2 August 2026 attribution

#### Scenario: Session-aware top bar
- **WHEN** the shared shell renders for an anonymous or authenticated visitor
- **THEN** it preserves the existing brand/home behavior, exposes only authenticated Jobs and My Robots navigation when signed in, and presents the correct sign-in or email/sign-out cluster

#### Scenario: Footer is shared across views
- **WHEN** a visitor moves among showcase, run detail, About, Terms, login, or authenticated views
- **THEN** the footer retains working About and Terms navigation and does not duplicate inside page content
