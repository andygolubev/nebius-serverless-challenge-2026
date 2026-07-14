## ADDED Requirements

### Requirement: Preparation and training actions follow the setup lifecycle
The My Robots setup UI SHALL show training eligibility and one of `Not prepared`, `Preparing`, `Ready for training`, `Preparation failed`, or `Ineligible` with a concise explanation. An eligible saved setup SHALL provide **Prepare for training**; only its latest current accepted fingerprint SHALL enable **Start training**. Preparation failure SHALL show a sanitized phase/reason and Retry action. The UI SHALL NOT show the former misleading “Training coming after GPU validation” state, because V1 custom training is SB3 on CPU.

#### Scenario: User saves an eligible setup
- **WHEN** a user saves a biped Stand Balance setup on Flat Arena with no optional objects
- **THEN** the setup shows Not prepared and an enabled Prepare for training action while Start training is disabled

#### Scenario: Preparation is running
- **WHEN** the latest attempt is non-terminal
- **THEN** the setup shows its current preparation phase, prevents duplicate actions, and refreshes status without requiring a page reload

#### Scenario: Preparation succeeds
- **WHEN** the latest exact fingerprint becomes accepted
- **THEN** the setup shows Ready for training and enables Start training with fixed `custom-ppo-quick` and `cpu-d3` context

#### Scenario: Preparation fails
- **WHEN** the latest attempt fails
- **THEN** the UI keeps Start training disabled and shows safe diagnostic and Retry controls

#### Scenario: Setup is outside V1
- **WHEN** a saved setup uses an unsupported task, scene, or optional object
- **THEN** the UI explains the exact V1 restriction and does not offer Prepare

### Requirement: Custom start creates and opens a normal Job
Starting an accepted setup SHALL submit only the setup identity plus idempotency metadata, show quota or stale-preparation errors inline, and on success create a normal dashboard Job and provide a direct route to its detail. The UI SHALL NOT expose a backend, algorithm, hardware, image, command, PPO, task, scene, or object override at start time.

#### Scenario: User starts training
- **WHEN** the owner selects Start training for a current Ready setup
- **THEN** the UI creates one custom Job, shows its starting lifecycle, and provides navigation to the normal Job detail

#### Scenario: Fingerprint became stale
- **WHEN** Start training returns that the preparation no longer matches current server versions
- **THEN** the UI returns the setup to Not prepared and asks the user to prepare again without showing a false Job

#### Scenario: User double-clicks Start
- **WHEN** the start action is activated repeatedly before the first response completes
- **THEN** the UI disables the action and the server idempotency contract prevents duplicate Jobs

### Requirement: Custom results are compact, complete, and honest
The normal result view for a custom Job SHALL identify the uploaded robot, task, scene, SB3 backend, fixed profile, preparation fingerprint/version, and evaluation success separately from infrastructure completion. It SHALL prioritize rollout video, key evaluation metrics, configuration summary, checkpoint, and policy-bundle download while keeping detailed nested data expandable. The bundle action SHALL display the simulator-only disclosure before download.

#### Scenario: Completed policy missed its task threshold
- **WHEN** a custom Job completed artifact production with `success=false`
- **THEN** the result is shown as Completed with a clear “task threshold not reached” evaluation state rather than as a failed infrastructure job

#### Scenario: User reviews a successful result
- **WHEN** the owner opens a completed custom Job
- **THEN** the compact view shows the final rollout, success metrics, robot/task/scene/profile summary, and safe artifact actions without raw JSON columns

#### Scenario: User downloads the bundle
- **WHEN** the owner selects the policy bundle action
- **THEN** the UI first states that it is simulator-only and then uses the normal tenant-authorized download URL

### Requirement: Browser-driven production acceptance preserves evidence
Production acceptance SHALL be performed through the deployed UI for both canonical repository robots and every supported task/scene combination. The operator SHALL click Prepare, observe Ready, click Start training, open the resulting Jobs, play rollout media, and download/verify bundles. SaaS Job rows and S3 result artifacts created for this acceptance SHALL be retained for user review; temporary compute/build resources SHALL still be cleaned up according to operations policy.

#### Scenario: Canonical acceptance matrix is completed
- **WHEN** release validation claims V1 custom training support
- **THEN** retained production evidence exists for two robots × two tasks × two scenes, including preparation, Job lifecycle, results, video, and bundle checks

#### Scenario: User later opens an acceptance Job
- **WHEN** the user clicks one of the retained Jobs in the deployed UI
- **THEN** its result and authorized artifacts remain available rather than having been deleted by validation cleanup

