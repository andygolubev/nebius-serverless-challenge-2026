import { useEffect, useState } from "react";

type Job = {
  id: string;
  preset: string;
  seed: number | null;
  status: string;
  updated_at: string;
};

const TENANT = "demo";
const headers = { "Content-Type": "application/json", "X-Tenant-Id": TENANT };

export function App() {
  const [presets, setPresets] = useState<string[]>([]);
  const [preset, setPreset] = useState("ant-demo");
  const [seed, setSeed] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const res = await fetch("/jobs", { headers });
    if (res.ok) setJobs(await res.json());
  }

  useEffect(() => {
    fetch("/training-options")
      .then((r) => r.json())
      .then((d) => {
        setPresets(d.presets);
        if (d.presets.length) setPreset(d.presets[0]);
      })
      .catch(() => setPresets(["ant-demo"]));
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 1500);
    return () => clearInterval(t);
  }, []);

  async function submit() {
    setError(null);
    const body = JSON.stringify({ preset, seed: seed ? Number(seed) : null });
    const res = await fetch("/jobs", { method: "POST", headers, body });
    if (!res.ok) {
      setError(`Submit failed: ${res.status}`);
      return;
    }
    setSeed("");
    refresh();
  }

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: 760, margin: "2rem auto", padding: "0 1rem" }}>
      <h1>Sim2Policy — train a locomotion policy</h1>
      <p style={{ color: "#555" }}>Pick a preset, submit a job, watch it progress, fetch results.</p>

      <section style={{ display: "flex", gap: 8, alignItems: "center", margin: "1rem 0" }}>
        <select value={preset} onChange={(e) => setPreset(e.target.value)}>
          {presets.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <input
          placeholder="seed (optional)"
          value={seed}
          onChange={(e) => setSeed(e.target.value)}
          style={{ width: 130 }}
        />
        <button onClick={submit}>Submit job</button>
      </section>
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      <h2>Jobs</h2>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
            <th>Job</th>
            <th>Preset</th>
            <th>Status</th>
            <th>Results</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
              <td title={j.id}>{j.id.slice(0, 8)}</td>
              <td>{j.preset}</td>
              <td>{j.status}</td>
              <td>
                {j.status === "completed" ? (
                  <a href={`/jobs/${j.id}/artifacts`} target="_blank" rel="noreferrer">
                    artifacts
                  </a>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
