import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, ApiError, Catalog, ParamSpec } from "../api";

// Job composer rendered entirely from the /training-options catalog: env cards,
// algorithm select, bounded parameter inputs, preset prefill.
export function Composer({ onSubmitted }: { onSubmitted: () => void }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [envId, setEnvId] = useState("");
  const [algoId, setAlgoId] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .catalog()
      .then((c) => {
        setCatalog(c);
        if (c.environments.length) selectEnv(c, c.environments[0].id);
      })
      .catch(() => setLoadError(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const env = catalog?.environments.find((e) => e.id === envId);
  const algo = catalog?.algorithms.find((a) => a.id === algoId);

  function selectEnv(c: Catalog, id: string) {
    const e = c.environments.find((x) => x.id === id)!;
    setEnvId(id);
    const nextAlgo = e.algorithms.includes(algoId) ? algoId : e.algorithms[0];
    selectAlgo(c, nextAlgo);
  }

  function selectAlgo(c: Catalog, id: string) {
    setAlgoId(id);
    const a = c.algorithms.find((x) => x.id === id)!;
    setValues(Object.fromEntries(a.params.map((p) => [p.name, String(p.default)])));
    setServerErrors({});
  }

  function applyPreset(presetId: string) {
    if (!catalog || !presetId) return;
    const preset = catalog.presets.find((p) => p.id === presetId)!;
    setEnvId(preset.environment);
    setAlgoId(preset.algorithm);
    const a = catalog.algorithms.find((x) => x.id === preset.algorithm)!;
    setValues(
      Object.fromEntries(
        a.params.map((p) => [p.name, String(preset.params[p.name] ?? p.default)])
      )
    );
    setServerErrors({});
  }

  // Client-side bounds check mirroring the catalog constraints.
  const violations = useMemo(() => {
    const out: Record<string, string> = {};
    for (const p of algo?.params ?? []) {
      const raw = values[p.name];
      if (raw === undefined || raw === "") {
        out[p.name] = "required";
        continue;
      }
      const num = Number(raw);
      if (Number.isNaN(num)) out[p.name] = "must be a number";
      else if (p.type === "int" && !Number.isInteger(num)) out[p.name] = "must be an integer";
      else if (num < p.min || num > p.max) out[p.name] = `must be between ${p.min} and ${p.max}`;
    }
    return out;
  }, [algo, values]);

  const valid = Object.keys(violations).length === 0 && !!env && !!algo;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!valid || !algo) return;
    setBusy(true);
    setFormError(null);
    setServerErrors({});
    try {
      await api.submitJob({
        environment: envId,
        algorithm: algoId,
        params: Object.fromEntries(algo.params.map((p) => [p.name, Number(values[p.name])])),
      });
      onSubmitted();
    } catch (err) {
      if (err instanceof ApiError && err.fieldError) {
        setServerErrors({ [err.fieldError.field]: err.fieldError.message });
      } else {
        setFormError("Couldn't submit the job. Try again in a moment.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (loadError) {
    return <div className="alert alert-error">Couldn't load training options. Reload the page to retry.</div>;
  }
  if (!catalog) {
    return <div className="skeleton" style={{ height: "16rem" }} aria-label="Loading training options" />;
  }

  return (
    <form onSubmit={submit}>
      <h1 className="section-title">New training job</h1>
      <p className="section-sub">Pick an environment, choose a policy, tune the parameters.</p>

      <div className="field" style={{ maxWidth: 320 }}>
        <label htmlFor="preset">Start from a preset (optional)</label>
        <select id="preset" className="input" defaultValue="" onChange={(e) => applyPreset(e.target.value)}>
          <option value="">— custom —</option>
          {catalog.presets.map((p) => (
            <option key={p.id} value={p.id}>
              {p.id}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label>Environment</label>
        <div className="env-grid" role="radiogroup" aria-label="Environment">
          {catalog.environments.map((e) => (
            <button
              key={e.id}
              type="button"
              role="radio"
              aria-checked={e.id === envId}
              className={`env-card ${e.id === envId ? "selected" : ""}`}
              onClick={() => selectEnv(catalog, e.id)}
            >
              <h3>{e.label}</h3>
              <p>{e.description}</p>
            </button>
          ))}
        </div>
        {serverErrors.environment && <span className="field-error">{serverErrors.environment}</span>}
      </div>

      <div className="field" style={{ maxWidth: 320 }}>
        <label htmlFor="algo">Policy</label>
        <select id="algo" className="input" value={algoId} onChange={(e) => selectAlgo(catalog, e.target.value)}>
          {(env?.algorithms ?? []).map((id) => {
            const a = catalog.algorithms.find((x) => x.id === id)!;
            return (
              <option key={id} value={id}>
                {a.label}
              </option>
            );
          })}
        </select>
        {algo && <span className="hint">{algo.description}</span>}
        {serverErrors.algorithm && <span className="field-error">{serverErrors.algorithm}</span>}
      </div>

      <div className="card" style={{ marginBottom: "var(--sp-5)" }}>
        <h2 style={{ fontSize: "var(--fs-md)", marginBottom: "var(--sp-4)" }}>Parameters</h2>
        {(algo?.params ?? []).map((p: ParamSpec) => {
          const error = serverErrors[p.name] ?? violations[p.name];
          return (
            <div className="field" key={p.name} style={{ maxWidth: 320 }}>
              <label htmlFor={`param-${p.name}`}>{p.label}</label>
              <input
                id={`param-${p.name}`}
                className={`input ${error ? "invalid" : ""}`}
                inputMode={p.type === "int" ? "numeric" : "decimal"}
                value={values[p.name] ?? ""}
                onChange={(e) => {
                  setValues({ ...values, [p.name]: e.target.value });
                  setServerErrors(({ [p.name]: _, ...rest }) => rest);
                }}
                aria-invalid={!!error}
              />
              <span className="hint">
                {p.min} – {p.max} · default {p.default}
              </span>
              {error && <span className="field-error">{error}</span>}
            </div>
          );
        })}
      </div>

      {formError && <div className="alert alert-error" role="alert">{formError}</div>}
      <button className="btn" disabled={!valid || busy}>
        {busy ? "Submitting…" : "Start training"}
      </button>
    </form>
  );
}
