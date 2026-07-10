# saas-web-ui Specification

## Purpose
Provide the styled tenant-facing web application: passwordless login flow, a catalog-driven job
composer, a live jobs dashboard, and results views — built on a consistent, accessible,
light/dark-aware design system that works from mobile to desktop.

## Requirements

### Requirement: Login flow UI
The web app SHALL present an unauthenticated user with a polished login screen: an email entry step, then a code entry step with a resend option and clear error states (wrong code, expired code, rate limited). On success the session token SHALL be stored client-side and the user routed to the dashboard; on 401 anywhere in the app the user SHALL be returned to login.

#### Scenario: Email then code
- **WHEN** a user enters their email and submits
- **THEN** the UI advances to a code-entry step telling the user a code was sent, with a resend action

#### Scenario: Wrong code feedback
- **WHEN** the user submits an incorrect code
- **THEN** the UI shows an inline error and lets the user retry or resend without restarting the flow

#### Scenario: Session expiry
- **WHEN** any API call returns 401 while using the app
- **THEN** the UI clears the stored session and shows the login screen

### Requirement: Job composer
The web app SHALL provide a job composer rendered from the `/training-options` catalog: environment selection (with a short description per environment), policy/algorithm selection, and a parameters panel showing defaults with validated inputs (client-side bounds matching the catalog). A preset picker SHALL prefill the form. Submission errors from the server SHALL be shown next to the offending field.

#### Scenario: Compose and submit a custom job
- **WHEN** the user picks an environment, a policy, adjusts a parameter within bounds, and submits
- **THEN** the job is created and appears in the dashboard without a page reload

#### Scenario: Client-side validation
- **WHEN** the user types a value outside a parameter's allowed range
- **THEN** the input shows the violation and the submit action is disabled until fixed

### Requirement: Jobs dashboard
The web app SHALL show the user's jobs as a live-updating list with status rendered as a lifecycle timeline/badge (queued → starting → training → evaluating → rendering → completed/failed), the environment and policy summary, and relative timestamps. Completed jobs SHALL link to a results view showing metrics and media from the artifact manifest. An empty state SHALL guide the first-time user to the composer.

#### Scenario: Live status updates
- **WHEN** a submitted job progresses through its lifecycle
- **THEN** the dashboard reflects the new status within a few seconds without user action

#### Scenario: Results view
- **WHEN** the user opens a completed job
- **THEN** the UI shows the resolved configuration, metrics, and any media links from the artifact manifest

#### Scenario: Empty state
- **WHEN** an authenticated user with no jobs opens the dashboard
- **THEN** the UI shows a friendly empty state with a call to action to create a job

### Requirement: Visual design system
The web app SHALL use a consistent design system: defined color tokens with light and dark theme support (respecting `prefers-color-scheme`), a consistent type scale and spacing scale, accessible contrast (WCAG AA), keyboard-operable forms, and a responsive layout usable from 375px-wide mobile up to desktop. Loading and error states SHALL be designed (skeletons/spinners and human-readable messages), not raw text dumps.

#### Scenario: Dark mode
- **WHEN** the user's OS is set to dark mode
- **THEN** the app renders with the dark token set with no unreadable elements

#### Scenario: Mobile layout
- **WHEN** the app is viewed at 375px width
- **THEN** login, composer, and dashboard remain fully usable without horizontal scrolling
