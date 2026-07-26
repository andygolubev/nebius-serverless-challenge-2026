import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ApiError,
  CatalogObjectInput,
  EnvironmentCatalog,
  ObjectCatalogEntry,
  Robot,
  RobotSample,
  RobotSetup,
  RobotType,
} from "../api";

type WorkspaceData = {
  samples: RobotSample[];
  robots: Robot[];
  setups: RobotSetup[];
  catalog: EnvironmentCatalog;
};

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function fieldError(error: unknown): { field?: string; message: string } {
  if (error instanceof ApiError) {
    return { field: error.fieldError?.field, message: error.fieldError?.message ?? error.message };
  }
  return { message: "Something went wrong. Please try again." };
}

export function MyRobots({
  onBrowseExamples = () => undefined,
  onJobStarted = () => undefined,
}: {
  onBrowseExamples?: () => void;
  onJobStarted?: (id: string) => void;
}) {
  const [data, setData] = useState<WorkspaceData | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [selectedRobot, setSelectedRobot] = useState<Robot | null>(null);
  const [deleteRobotId, setDeleteRobotId] = useState<string | null>(null);
  const [deleteSetupId, setDeleteSetupId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [robotType, setRobotType] = useState<RobotType>("quadruped");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadErrors, setUploadErrors] = useState<Record<string, string>>({});
  const [setupBusy, setSetupBusy] = useState<string | null>(null);
  const [setupError, setSetupError] = useState<Record<string, string>>({});
  const idempotencyKeys = useRef<Record<string, string>>({});
  const fileInput = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      const [samples, robots, setups, catalog] = await Promise.all([
        api.listRobotSamples(),
        api.listRobots(),
        api.listRobotSetups(),
        api.environmentCatalog(),
      ]);
      setData({ samples, robots, setups, catalog });
      setLoadError(false);
    } catch {
      setLoadError(true);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!data?.setups.some((setup) => setup.training_readiness === "preparing")) return;
    let alive = true;
    const refresh = async () => {
      try {
        const setups = await api.listRobotSetups();
        if (alive) setData((current) => (current ? { ...current, setups } : current));
      } catch {
        if (alive) setLoadError(true);
      }
    };
    const timer = window.setInterval(refresh, 1000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [data?.setups.some((setup) => setup.training_readiness === "preparing")]);

  async function refreshSetup(setupId: string) {
    const setup = await api.getRobotSetup(setupId);
    setData((current) =>
      current
        ? { ...current, setups: current.setups.map((item) => (item.id === setup.id ? setup : item)) }
        : current,
    );
    return setup;
  }

  async function prepareSetup(setup: RobotSetup, retry = false) {
    setSetupBusy(setup.id);
    setSetupError((current) => ({ ...current, [setup.id]: "" }));
    try {
      await api.prepareRobotSetup(setup.id, retry);
      await refreshSetup(setup.id);
    } catch (error) {
      setSetupError((current) => ({ ...current, [setup.id]: fieldError(error).message }));
    } finally {
      setSetupBusy(null);
    }
  }

  async function startTraining(setup: RobotSetup) {
    setSetupBusy(setup.id);
    setSetupError((current) => ({ ...current, [setup.id]: "" }));
    try {
      const key =
        idempotencyKeys.current[setup.id] ??
        `start-${setup.id}-${Date.now().toString(36)}`;
      idempotencyKeys.current[setup.id] = key;
      const job = await api.startRobotTraining(setup.id, key);
      onJobStarted(job.id);
    } catch (error) {
      setSetupError((current) => ({ ...current, [setup.id]: fieldError(error).message }));
    } finally {
      setSetupBusy(null);
    }
  }

  async function upload(event: FormEvent) {
    event.preventDefault();
    const errors: Record<string, string> = {};
    if (!name.trim()) errors.name = "Give this robot a recognizable name.";
    if (!file) errors.file = "Choose one MJCF .xml file.";
    else if (!file.name.toLowerCase().endsWith(".xml")) errors.file = "The file must end in .xml.";
    if (Object.keys(errors).length) {
      setUploadErrors(errors);
      return;
    }
    setUploading(true);
    setUploadErrors({});
    try {
      const robot = await api.uploadRobot(name.trim(), robotType, file!);
      setData((current) =>
        current
          ? { ...current, robots: [robot, ...current.robots.filter((item) => item.id !== robot.id)] }
          : current,
      );
      setName("");
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
    } catch (error) {
      const diagnostic = fieldError(error);
      setUploadErrors({ [diagnostic.field ?? "form"]: diagnostic.message });
    } finally {
      setUploading(false);
    }
  }

  async function downloadSample(sample: RobotSample) {
    try {
      triggerDownload(await api.downloadRobotSample(sample.id), sample.filename);
    } catch {
      setLoadError(true);
    }
  }

  async function downloadRobot(robot: Robot) {
    try {
      triggerDownload(await api.downloadRobot(robot.id), robot.filename);
    } catch {
      setLoadError(true);
    }
  }

  async function removeRobot(robotId: string) {
    try {
      await api.deleteRobot(robotId);
      setData((current) =>
        current ? { ...current, robots: current.robots.filter((robot) => robot.id !== robotId) } : current,
      );
      if (selectedRobot?.id === robotId) setSelectedRobot(null);
      setDeleteRobotId(null);
    } catch {
      setLoadError(true);
    }
  }

  async function removeSetup(setupId: string) {
    try {
      await api.deleteRobotSetup(setupId);
      setData((current) =>
        current ? { ...current, setups: current.setups.filter((setup) => setup.id !== setupId) } : current,
      );
      setDeleteSetupId(null);
    } catch {
      setLoadError(true);
    }
  }

  if (!data && !loadError) {
    return <div className="skeleton workspace-skeleton" aria-label="Loading My Robots" />;
  }
  if (!data) {
    return (
      <div className="empty-state">
        <h1>My Robots</h1>
        <p>We couldn't load your robot workspace.</p>
        <button className="btn" onClick={load}>Retry</button>
      </div>
    );
  }

  return (
    <div className="robot-workspace">
      <div className="workspace-heading">
        <div>
          <p className="eyebrow">Bring Your Robot · Beta</p>
          <h1 className="section-title">My Robots</h1>
          <p className="section-sub">
            Validate a small self-contained MJCF model, then compose a bounded locomotion setup.
          </p>
        </div>
        <span className="beta-chip">CPU training beta</span>
      </div>

      {loadError && <div className="alert alert-error" role="alert">A request failed. Your last loaded data is still shown.</div>}

      <section aria-labelledby="sample-heading">
        <div className="section-heading-row">
          <div>
            <h2 id="sample-heading">Start with an example</h2>
            <p>These primitive-only files use the exact same validator as your upload.</p>
          </div>
        </div>
        <div className="sample-grid">
          {data.samples.map((sample) => (
            <article className="sample-card" key={sample.id}>
              <RobotAvatar type={sample.robot_type} />
              <div className="sample-card-copy">
                <h3>{sample.name}</h3>
                <p>{sample.description}</p>
                <span className="metadata-line">
                  {sample.validation.body_count} bodies · {sample.validation.actuator_count} actuators
                </span>
              </div>
              <button className="btn btn-ghost" onClick={() => downloadSample(sample)}>
                Download XML
              </button>
            </article>
          ))}
        </div>
      </section>

      <section className="card upload-card" aria-labelledby="upload-heading">
        <div>
          <p className="eyebrow">One file · 1 MiB maximum</p>
          <h2 id="upload-heading">Upload MJCF</h2>
          <p className="section-sub">
            UTF-8 XML with primitive geometry only. Meshes, textures, plugins, includes, paths, and archives are rejected.
          </p>
        </div>
        <form className="upload-form" onSubmit={upload} noValidate>
          <div className="field">
            <label htmlFor="robot-name">Robot name</label>
            <input
              id="robot-name"
              className={`input ${uploadErrors.name ? "invalid" : ""}`}
              value={name}
              maxLength={80}
              onChange={(event) => {
                setName(event.target.value);
                setUploadErrors(({ name: _, ...rest }) => rest);
              }}
              aria-invalid={!!uploadErrors.name}
            />
            {uploadErrors.name && <span className="field-error">{uploadErrors.name}</span>}
          </div>
          <fieldset className="field compact-fieldset">
            <legend>Robot type</legend>
            <div className="segmented-control">
              {(["quadruped", "biped"] as RobotType[]).map((type) => (
                <label key={type} className={robotType === type ? "selected" : ""}>
                  <input type="radio" name="robot-type" value={type} checked={robotType === type} onChange={() => setRobotType(type)} />
                  {type === "quadruped" ? "Quadruped" : "Biped"}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="field">
            <label htmlFor="robot-file">MJCF XML</label>
            <input
              ref={fileInput}
              id="robot-file"
              className={`input file-input ${uploadErrors.file ? "invalid" : ""}`}
              type="file"
              accept=".xml,application/xml,text/xml"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                setUploadErrors(({ file: _, ...rest }) => rest);
              }}
              aria-invalid={!!uploadErrors.file}
            />
            {uploadErrors.file && <span className="field-error">{uploadErrors.file}</span>}
          </div>
          {uploadErrors.form && <div className="alert alert-error" role="alert">{uploadErrors.form}</div>}
          <button className="btn" disabled={uploading}>{uploading ? "Validating…" : "Validate model"}</button>
        </form>
      </section>

      <section aria-labelledby="models-heading">
        <div className="section-heading-row">
          <div>
            <h2 id="models-heading">Validated models</h2>
            <p>{data.robots.length} of 20 active robot versions</p>
          </div>
        </div>
        {data.robots.length === 0 ? (
          <div className="inline-empty">Download an example above and upload it here to test the workflow.</div>
        ) : (
          <div className="robot-grid">
            {data.robots.map((robot) => (
              <article className="robot-card" key={robot.id}>
                <div className="robot-card-title">
                  <RobotAvatar type={robot.robot_type} />
                  <div>
                    <h3>{robot.name}</h3>
                    <span className="metadata-line">{robot.robot_type} · {robot.filename}</span>
                  </div>
                  <span className="badge completed">Model validated</span>
                </div>
                <dl className="stat-strip">
                  <div><dt>Bodies</dt><dd>{robot.validation.body_count}</dd></div>
                  <div><dt>Joints</dt><dd>{robot.validation.joint_count}</dd></div>
                  <div><dt>Actuators</dt><dd>{robot.validation.actuator_count}</dd></div>
                  <div><dt>Geoms</dt><dd>{robot.validation.geom_count}</dd></div>
                </dl>
                <div className="digest-row">
                  <span>SHA-256</span>
                  <code title={robot.digest}>{robot.digest}</code>
                </div>
                <p className="readiness-note">
                  Model file and structure validated. Build a setup to review its available training path.
                </p>
                <div className="card-actions">
                  <button className="btn" onClick={() => setSelectedRobot(robot)}>Build environment</button>
                  <button className="btn btn-ghost" onClick={() => downloadRobot(robot)}>Download XML</button>
                  {deleteRobotId === robot.id ? (
                    <span className="confirm-actions">
                      <span>Delete this version?</span>
                      <button className="btn btn-danger" onClick={() => removeRobot(robot.id)}>Delete</button>
                      <button className="btn btn-ghost" onClick={() => setDeleteRobotId(null)}>Cancel</button>
                    </span>
                  ) : (
                    <button className="btn-link danger-link" onClick={() => setDeleteRobotId(robot.id)}>Delete model</button>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {selectedRobot && (
        <EnvironmentBuilder
          key={selectedRobot.id}
          robot={selectedRobot}
          catalog={data.catalog}
          setups={data.setups}
          onClose={() => setSelectedRobot(null)}
          onSaved={(setup) =>
            setData((current) =>
              current
                ? { ...current, setups: [setup, ...current.setups.filter((item) => item.id !== setup.id)] }
                : current,
            )
          }
          onPrepare={prepareSetup}
          onStart={startTraining}
          onBrowseExamples={onBrowseExamples}
          busySetupId={setupBusy}
          setupError={setupError}
        />
      )}

      <section aria-labelledby="setups-heading">
        <div className="section-heading-row">
          <div>
            <h2 id="setups-heading">Validated setups</h2>
            <p>{data.setups.length} of {data.catalog.max_setups} saved drafts</p>
          </div>
        </div>
        {data.setups.length === 0 ? (
          <div className="inline-empty">Choose “Build environment” on a validated model to create a setup.</div>
        ) : (
          <div className="setup-list">
            {data.setups.map((setup) => (
              <article className="setup-card" key={setup.id}>
                <div>
                  <span className="badge completed">Setup validated</span>
                  <h3>{setup.name}</h3>
                  <p>{setup.robot_name} · {humanize(setup.task_template_id)} · {humanize(setup.scene_preset_id)}</p>
                </div>
                <div className="setup-card-meta">
                  <span>{setup.objects.length} scene objects</span>
                  <code title={setup.digest}>{setup.digest.slice(0, 12)}…</code>
                </div>
                <SetupTrainingActions
                  setup={setup}
                  busy={setupBusy === setup.id}
                  error={setupError[setup.id]}
                  onPrepare={prepareSetup}
                  onStart={startTraining}
                  onBrowseExamples={onBrowseExamples}
                />
                {deleteSetupId === setup.id ? (
                  <span className="confirm-actions">
                    <span>Delete this setup?</span>
                    <button className="btn btn-danger" onClick={() => removeSetup(setup.id)}>Delete</button>
                    <button className="btn btn-ghost" onClick={() => setDeleteSetupId(null)}>Cancel</button>
                  </span>
                ) : (
                  <button className="btn-link danger-link" onClick={() => setDeleteSetupId(setup.id)}>Delete setup</button>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function RobotAvatar({ type }: { type: RobotType }) {
  return <span className={`robot-avatar ${type}`} aria-hidden>{type === "quadruped" ? "4×" : "2×"}</span>;
}

function humanize(value: string): string {
  return value.replace(/-/g, " ").replace(/\b\w/g, (character: string) => character.toUpperCase());
}

function readinessCopy(setup: RobotSetup): string {
  if (setup.training_readiness === "preparing") {
    return `Preparing · ${humanize(setup.current_preparation?.phase ?? "starting")}`;
  }
  if (setup.training_readiness === "ready") return "Prepared for fixed CPU training";
  if (setup.training_readiness === "preparation_failed") {
    return `Preparation failed · ${humanize(setup.current_preparation?.failure_reason ?? "retry available")}`;
  }
  if (setup.training_readiness === "ineligible") return humanize(setup.reason);
  return setup.reason === "custom-training-not-enabled"
    ? "Custom training is not enabled on this deployment"
    : "Preparation required before training";
}

function SetupTrainingActions({
  setup,
  busy,
  error,
  onPrepare,
  onStart,
  onBrowseExamples,
}: {
  setup: RobotSetup;
  busy: boolean;
  error?: string;
  onPrepare: (setup: RobotSetup, retry?: boolean) => void;
  onStart: (setup: RobotSetup) => void;
  onBrowseExamples: () => void;
}) {
  const preparing = setup.training_readiness === "preparing";
  const failed = setup.training_readiness === "preparation_failed";
  return (
    <div className="setup-training-actions">
      <span className={`readiness-state ${setup.training_readiness}`} role="status">
        {readinessCopy(setup)}
      </span>
      {setup.can_start_training ? (
        <button className="btn" disabled={busy} onClick={() => onStart(setup)}>
          {busy ? "Starting…" : "Start training"}
        </button>
      ) : setup.can_prepare || preparing || failed ? (
        <button
          className="btn"
          disabled={busy || preparing || !setup.can_prepare}
          onClick={() => onPrepare(setup, failed)}
        >
          {busy ? "Submitting…" : preparing ? "Preparing…" : failed ? "Retry preparation" : "Prepare for training"}
        </button>
      ) : (
        <div className="verified-example-handoff">
          <p>
            {setup.reason === "custom-training-not-enabled"
              ? "This setup is saved and validated, but this deployment has no accepted custom training adapter and production job specification. No training job was created."
              : "This setup is saved and validated, but it is outside the fixed custom training profile. No training job was created."}
          </p>
          {/* Reference evidence, never an alternative training action: showcase
              examples are read-only and cannot be trained. */}
          <button type="button" className="btn btn-ghost" onClick={onBrowseExamples}>
            See a verified example
          </button>
        </div>
      )}
      {error && <span className="field-error" role="alert">{error}</span>}
    </div>
  );
}

function EnvironmentBuilder({
  robot,
  catalog,
  setups,
  onSaved,
  onClose,
  onPrepare,
  onStart,
  onBrowseExamples,
  busySetupId,
  setupError,
}: {
  robot: Robot;
  catalog: EnvironmentCatalog;
  setups: RobotSetup[];
  onSaved: (setup: RobotSetup) => void;
  onClose: () => void;
  onPrepare: (setup: RobotSetup, retry?: boolean) => void;
  onStart: (setup: RobotSetup) => void;
  onBrowseExamples: () => void;
  busySetupId: string | null;
  setupError: Record<string, string>;
}) {
  const compatibleTasks = useMemo(
    () => catalog.task_templates.filter((task) => task.compatible_robot_types.includes(robot.robot_type)),
    [catalog, robot.robot_type],
  );
  const [name, setName] = useState(`${robot.name} setup`);
  const [taskId, setTaskId] = useState(compatibleTasks[0]?.id ?? "");
  const [sceneId, setSceneId] = useState(catalog.scene_presets[0]?.id ?? "");
  const [objectType, setObjectType] = useState(catalog.object_types[0]?.id ?? "box");
  const [objects, setObjects] = useState<CatalogObjectInput[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<RobotSetup | null>(null);
  const currentSaved = saved
    ? setups.find((setup) => setup.id === saved.id) ?? saved
    : null;
  const scene = catalog.scene_presets.find((item) => item.id === sceneId)!;
  const totalObjects = (scene?.objects.length ?? 0) + objects.length;
  const objectSpecs = new Map(catalog.object_types.map((item) => [item.id, item]));
  const invalidObjects = objects.some((object) => !isValidObject(object, objectSpecs.get(object.object_type)!));

  function addObject() {
    const spec = objectSpecs.get(objectType)!;
    const object: CatalogObjectInput = { object_type: spec.id };
    for (const parameter of spec.parameters) object[parameter.name] = parameter.default;
    setObjects((current) => [...current, object]);
    setSaved(null);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const setup = await api.createRobotSetup({
        name: name.trim(),
        robot_id: robot.id,
        task_template_id: taskId,
        scene_preset_id: sceneId,
        objects,
      });
      setSaved(setup);
      onSaved(setup);
    } catch (cause) {
      setError(fieldError(cause).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="builder card" aria-labelledby="builder-heading">
      <div className="builder-header">
        <div>
          <p className="eyebrow">Environment builder</p>
          <h2 id="builder-heading">Set up {robot.name}</h2>
          <p>Choose server-owned tasks and primitives. No code, URL, scene, or object upload is accepted.</p>
        </div>
        <button className="btn btn-ghost" onClick={onClose}>Close builder</button>
      </div>

      <div className="field builder-name">
        <label htmlFor="setup-name">Setup name</label>
        <input id="setup-name" className="input" maxLength={80} value={name} onChange={(event) => setName(event.target.value)} />
      </div>

      <fieldset className="builder-step">
        <legend><span>1</span> Locomotion task</legend>
        <div className="choice-grid" role="radiogroup" aria-label="Locomotion task">
          {compatibleTasks.map((task) => (
            <button
              key={task.id}
              type="button"
              role="radio"
              aria-checked={task.id === taskId}
              className={`choice-card ${task.id === taskId ? "selected" : ""}`}
              onClick={() => { setTaskId(task.id); setSaved(null); }}
            >
              <strong>{task.label}</strong>
              <span>{task.description}</span>
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset className="builder-step">
        <legend><span>2</span> Scene preset</legend>
        <div className="choice-grid scene-choice-grid" role="radiogroup" aria-label="Scene preset">
          {catalog.scene_presets.map((preset) => (
            <button
              key={preset.id}
              type="button"
              role="radio"
              aria-checked={preset.id === sceneId}
              className={`choice-card ${preset.id === sceneId ? "selected" : ""}`}
              onClick={() => { setSceneId(preset.id); setSaved(null); }}
            >
              <strong>{preset.label}</strong>
              <span>{preset.description}</span>
              <small>{preset.objects.length ? `${preset.objects.length} preset objects` : "Open terrain"}</small>
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset className="builder-step">
        <legend><span>3</span> Optional catalog objects</legend>
        <p className="builder-hint">Add up to {catalog.max_objects} total objects, including the {scene?.objects.length ?? 0} in this preset.</p>
        <p className="builder-hint">
          Custom training V1 supports Stand Balance or Walk Forward on Flat Arena or Ramp Course with no optional objects.
        </p>
        <div className="add-object-row">
          <label htmlFor="object-type">Object type</label>
          <select id="object-type" className="input" value={objectType} onChange={(event) => setObjectType(event.target.value as CatalogObjectInput["object_type"])}>
            {catalog.object_types.map((type) => <option key={type.id} value={type.id}>{type.label}</option>)}
          </select>
          <button type="button" className="btn btn-ghost" disabled={totalObjects >= catalog.max_objects} onClick={addObject}>Add object</button>
        </div>
        <div className="object-editor-list">
          {objects.map((object, index) => {
            const spec = objectSpecs.get(object.object_type)!;
            return (
              <div className="object-editor" key={`${object.object_type}-${index}`}>
                <div className="object-editor-heading">
                  <div><strong>{spec.label} {index + 1}</strong><span>{spec.description}</span></div>
                  <button type="button" className="btn-link danger-link" onClick={() => setObjects((current) => current.filter((_, itemIndex) => itemIndex !== index))}>Remove</button>
                </div>
                <div className="parameter-grid">
                  {spec.parameters.map((parameter) => {
                    const value = object[parameter.name] ?? parameter.default;
                    const invalid = !Number.isFinite(value) || value < parameter.minimum || value > parameter.maximum;
                    return (
                      <label key={parameter.name}>
                        <span>{parameter.label}</span>
                        <span className="number-input-wrap">
                          <input
                            className={`input ${invalid ? "invalid" : ""}`}
                            type="number"
                            min={parameter.minimum}
                            max={parameter.maximum}
                            step="any"
                            value={value}
                            aria-invalid={invalid}
                            onChange={(event) => {
                              const number = event.target.value === "" ? Number.NaN : Number(event.target.value);
                              setObjects((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, [parameter.name]: number } : item));
                              setSaved(null);
                            }}
                          />
                          <small>{parameter.unit}</small>
                        </span>
                        <small>{parameter.minimum}–{parameter.maximum}</small>
                      </label>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </fieldset>

      <div className="builder-review">
        <div>
          <p className="eyebrow">Review</p>
          <h3>{name || "Untitled setup"}</h3>
          <p>{robot.name} · {humanize(taskId)} · {scene?.label} · {totalObjects} objects</p>
        </div>
        <div className="readiness-panel">
          <span className="badge completed">Setup validated</span>
          <p>Eligible setups run a bounded CPU preparation before the fixed PPO training profile is enabled.</p>
        </div>
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        {currentSaved && (
          <div className="alert alert-success" role="status">
            Setup saved. {readinessCopy(currentSaved)}.
          </div>
        )}
        <div className="builder-actions">
          <button className="btn" onClick={save} disabled={busy || !name.trim() || !taskId || !sceneId || invalidObjects || totalObjects > catalog.max_objects}>
            {busy ? "Saving…" : "Save validated setup"}
          </button>
          {currentSaved && (
            <SetupTrainingActions
              setup={currentSaved}
              busy={busySetupId === currentSaved.id}
              error={setupError[currentSaved.id]}
              onPrepare={onPrepare}
              onStart={onStart}
              onBrowseExamples={onBrowseExamples}
            />
          )}
        </div>
      </div>
    </section>
  );
}

function isValidObject(object: CatalogObjectInput, spec: ObjectCatalogEntry): boolean {
  return spec.parameters.every((parameter) => {
    const value = object[parameter.name];
    return typeof value === "number" && Number.isFinite(value) && value >= parameter.minimum && value <= parameter.maximum;
  });
}
