import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, ApiError, Catalog, GalleryExample, ParamSpec } from "../api";

export function Composer({ onSubmitted }: { onSubmitted: () => void }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    api.catalog().then(setCatalog).catch(() => setLoadError(true));
  }, []);

  if (loadError) {
    return <div className="alert alert-error">Couldn't load training options. Reload the page to retry.</div>;
  }
  if (!catalog) {
    return <div className="skeleton" style={{ height: "16rem" }} aria-label="Loading training options" />;
  }
  if (catalog.gallery_enabled) {
    return <GalleryComposer catalog={catalog} onSubmitted={onSubmitted} />;
  }
  return <LegacyComposer catalog={catalog} onSubmitted={onSubmitted} />;
}

function GalleryComposer({ catalog, onSubmitted }: { catalog: Catalog; onSubmitted: () => void }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [profileId, setProfileId] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const selected = catalog.examples.find((example) => example.id === selectedId) ?? null;

  function choose(example: GalleryExample) {
    setSelectedId(example.id);
    setProfileId(example.recommended_profile);
    setValues(
      Object.fromEntries(
        example.optional_params.map((param) => [
          param.name,
          String(example.recommended_params[param.name] ?? param.default),
        ]),
      ),
    );
    setServerErrors({});
    setFormError(null);
  }

  const violations = useMemo(
    () => validateValues(selected?.optional_params ?? [], values),
    [selected, values],
  );
  const valid = selected !== null && Object.keys(violations).length === 0;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selected || !valid) return;
    setBusy(true);
    setFormError(null);
    setServerErrors({});
    try {
      await api.submitJob({
        gallery_example_id: selected.id,
        gallery_profile_id: profileId,
        params: Object.fromEntries(
          selected.optional_params.map((param) => [param.name, Number(values[param.name])]),
        ),
      });
      onSubmitted();
    } catch (error) {
      if (error instanceof ApiError && error.fieldError) {
        setServerErrors({ [error.fieldError.field]: error.fieldError.message });
      } else {
        setFormError("Couldn't start this training job. Try again in a moment.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="gallery-composer">
      <header className="composer-heading">
        <p className="eyebrow">Verified training examples</p>
        <h1 className="section-title">Choose what to train</h1>
        <p className="section-sub">
          Seven complete robot tasks with a server-selected runtime and compute profile. Pick a story, review it, and start.
        </p>
      </header>

      {catalog.examples.length === 0 ? (
        <div className="empty-state"><h2>No accepted examples yet</h2><p>The catalog is waiting for verified runtime evidence.</p></div>
      ) : (
        <div className="gallery-grid" role="radiogroup" aria-label="Verified training examples">
          {catalog.examples.map((example) => (
            <button
              key={example.id}
              type="button"
              role="radio"
              aria-checked={example.id === selectedId}
              className={`gallery-card ${example.id === selectedId ? "selected" : ""}`}
              onClick={() => choose(example)}
            >
              <div className="gallery-card-top">
                <img src={example.avatar} alt={`${example.label} avatar`} />
                <span className="badge backend-badge">{example.backend_label}</span>
              </div>
              <div className="gallery-card-copy">
                <p className="eyebrow">{example.task}</p>
                <h2>{example.label}</h2>
                <p>{example.description}</p>
              </div>
              <dl className="gallery-card-facts">
                <div><dt>Expected</dt><dd>{example.expected_result}</dd></div>
                <div><dt>Compute</dt><dd>{example.hardware_label}</dd></div>
                <div><dt>Time</dt><dd>{example.observed_duration}</dd></div>
                <div><dt>Cost</dt><dd>{example.observed_cost}</dd></div>
              </dl>
              <span className="recommended-line">Recommended · {humanize(example.recommended_profile)}</span>
            </button>
          ))}
        </div>
      )}

      {selected && (
        <section className="gallery-review" aria-labelledby="review-title">
          <div className="gallery-review-identity">
            <img src={selected.avatar} alt="" />
            <div>
              <p className="eyebrow">Review</p>
              <h2 id="review-title">{selected.label} · {selected.task}</h2>
              <p>{selected.expected_result}</p>
            </div>
          </div>
          <div className="review-facts">
            <div><span>Policy</span><strong>{selected.backend_label}</strong></div>
            <div><span>Hardware</span><strong>{selected.hardware_label}</strong></div>
            <div><span>Success</span><strong>{selected.success_criterion}</strong></div>
            <div><span>Primary KPI</span><strong>{selected.primary_metric}</strong></div>
          </div>

          <div className="review-controls">
            {selected.workload_profiles.length > 1 ? (
              <div className="field">
                <label htmlFor="gallery-profile">Workload size</label>
                <select
                  id="gallery-profile"
                  className="input"
                  value={profileId}
                  onChange={(event) => setProfileId(event.target.value)}
                >
                  {selected.workload_profiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.label ?? humanize(profile.id)}{profile.recommended ? " · recommended" : ""}
                    </option>
                  ))}
                </select>
                <span className="hint">The backend, image, and hardware remain fixed by the verified catalog.</span>
                {serverErrors.gallery_profile_id && <span className="field-error">{serverErrors.gallery_profile_id}</span>}
              </div>
            ) : (
              <div className="fixed-profile"><span>Workload</span><strong>{humanize(profileId)}</strong><small>Recommended and fixed</small></div>
            )}
            {selected.optional_params.map((param) => {
              const error = serverErrors[param.name] ?? violations[param.name];
              return (
                <div className="field" key={param.name}>
                  <label htmlFor={`gallery-${param.name}`}>{param.label}</label>
                  <input
                    id={`gallery-${param.name}`}
                    className={`input ${error ? "invalid" : ""}`}
                    inputMode={param.type === "int" ? "numeric" : "decimal"}
                    value={values[param.name] ?? ""}
                    onChange={(event) => {
                      setValues({ ...values, [param.name]: event.target.value });
                      setServerErrors(({ [param.name]: _, ...rest }) => rest);
                    }}
                    aria-invalid={!!error}
                  />
                  <span className="hint">Optional reproducibility seed · {param.min}–{param.max}</span>
                  {error && <span className="field-error">{error}</span>}
                </div>
              );
            })}
          </div>
          {formError && <div className="alert alert-error" role="alert">{formError}</div>}
          {serverErrors.gallery_example_id && <div className="alert alert-error" role="alert">{serverErrors.gallery_example_id}</div>}
          <div className="review-submit">
            <p>No uploaded code, Docker build, backend selector, or hardware selector is involved.</p>
            <button className="btn" disabled={!valid || busy}>{busy ? "Starting…" : "Start training"}</button>
          </div>
        </section>
      )}
    </form>
  );
}

function LegacyComposer({ catalog, onSubmitted }: { catalog: Catalog; onSubmitted: () => void }) {
  const flagship = catalog.presets.find((preset) => preset.default) ?? catalog.presets[0];
  const [presetId, setPresetId] = useState(flagship?.id ?? "");
  const [values, setValues] = useState<Record<string, string>>(() => legacyValues(catalog, flagship?.id));
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const preset = catalog.presets.find((item) => item.id === presetId);
  const algorithm = catalog.algorithms.find((item) => item.id === preset?.algorithm);
  const violations = useMemo(() => validateValues(algorithm?.params ?? [], values), [algorithm, values]);
  const valid = !!preset && !!algorithm && Object.keys(violations).length === 0;

  function selectPreset(id: string) {
    setPresetId(id);
    setValues(legacyValues(catalog, id));
    setServerErrors({});
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!preset || !algorithm || !valid) return;
    setBusy(true);
    setFormError(null);
    try {
      await api.submitJob({
        preset: preset.id,
        params: Object.fromEntries(algorithm.params.map((param) => [param.name, Number(values[param.name])])),
      });
      onSubmitted();
    } catch (error) {
      if (error instanceof ApiError && error.fieldError) setServerErrors({ [error.fieldError.field]: error.fieldError.message });
      else setFormError("Couldn't submit the job. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <h1 className="section-title">New training job</h1>
      <p className="section-sub">Choose a GPU-accelerated Go1 PPO workload.</p>
      <div className="env-grid" role="radiogroup" aria-label="GPU workload">
        {catalog.presets.map((item) => (
          <button key={item.id} type="button" role="radio" aria-checked={item.id === presetId} className={`env-card ${item.id === presetId ? "selected" : ""}`} onClick={() => selectPreset(item.id)}>
            <h3>{item.label ?? item.id}</h3><p>{item.description}</p><p>{Number(item.params.total_timesteps).toLocaleString()} timesteps</p>
          </button>
        ))}
      </div>
      <div className="card legacy-parameters">
        <h2>Parameters</h2>
        {(algorithm?.params ?? []).map((param) => {
          const error = serverErrors[param.name] ?? violations[param.name];
          return (
            <div className="field" key={param.name}>
              <label htmlFor={`param-${param.name}`}>{param.label}</label>
              <input id={`param-${param.name}`} className={`input ${error ? "invalid" : ""}`} value={values[param.name] ?? ""} onChange={(event) => setValues({ ...values, [param.name]: event.target.value })} aria-invalid={!!error} />
              <span className="hint">{param.min}–{param.max} · default {param.default}</span>
              {error && <span className="field-error">{error}</span>}
            </div>
          );
        })}
      </div>
      {formError && <div className="alert alert-error" role="alert">{formError}</div>}
      <button className="btn" disabled={!valid || busy}>{busy ? "Submitting…" : "Start training"}</button>
    </form>
  );
}

function legacyValues(catalog: Catalog, presetId?: string): Record<string, string> {
  const preset = catalog.presets.find((item) => item.id === presetId);
  const algorithm = catalog.algorithms.find((item) => item.id === preset?.algorithm);
  return Object.fromEntries(
    (algorithm?.params ?? []).map((param) => [param.name, String(preset?.params[param.name] ?? param.default)]),
  );
}

function validateValues(params: ParamSpec[], values: Record<string, string>): Record<string, string> {
  const violations: Record<string, string> = {};
  for (const param of params) {
    const raw = values[param.name];
    if (raw === undefined || raw === "") violations[param.name] = "required";
    else {
      const number = Number(raw);
      if (Number.isNaN(number)) violations[param.name] = "must be a number";
      else if (param.type === "int" && !Number.isInteger(number)) violations[param.name] = "must be an integer";
      else if (number < param.min || number > param.max) violations[param.name] = `must be between ${param.min} and ${param.max}`;
    }
  }
  return violations;
}

function humanize(value: string): string {
  return value.replace(/[-_]/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
