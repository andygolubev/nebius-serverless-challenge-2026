import { FormEvent, useState } from "react";
import { api, ApiError, session } from "../api";

// Two-step passwordless login: email → one-time code (with resend). Reached
// deliberately from the public showcase, so it always offers a way back.
export function Login({ onLogin, onCancel }: { onLogin: () => void; onCancel: () => void }) {
  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function sendCode(e?: FormEvent) {
    e?.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      await api.requestCode(email);
      setStep("code");
      setNotice(`We sent a 6-digit code to ${email}. It expires in 10 minutes.`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setError("Too many codes requested. Wait a few minutes and try again.");
      } else if (err instanceof ApiError && err.status === 422) {
        setError("That doesn't look like a valid email address.");
      } else {
        setError("Couldn't send the code. Check your connection and try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function verify(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await api.verifyCode(email, code);
      session.set(res.token, res.email);
      onLogin();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Wrong or expired code. Try again, or resend a new one.");
      } else {
        setError("Verification failed. Try again in a moment.");
      }
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="card login-card">
        <div className="brand" style={{ marginBottom: "var(--sp-4)" }}>
          <span className="brand-dot" aria-hidden />
          Sim2Policy
        </div>

        {step === "email" ? (
          <form onSubmit={sendCode}>
            <h1 className="section-title">Sign in</h1>
            <p className="section-sub">Enter your email and we'll send you a one-time code.</p>
            <div className="field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                className="input"
                type="email"
                autoComplete="email"
                autoFocus
                required
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            {error && <div className="alert alert-error" role="alert">{error}</div>}
            <button className="btn" style={{ width: "100%" }} disabled={busy || !email}>
              {busy ? "Sending…" : "Send code"}
            </button>
            <p style={{ textAlign: "center", marginBottom: 0 }}>
              <button type="button" className="btn-link" onClick={onCancel}>
                ← Back to verified runs
              </button>
            </p>
          </form>
        ) : (
          <form onSubmit={verify}>
            <h1 className="section-title">Check your inbox</h1>
            {notice && <p className="section-sub">{notice}</p>}
            <div className="code-inputs">
              <input
                className="code-input"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                autoFocus
                aria-label="6-digit code"
                placeholder="••••••"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              />
            </div>
            {error && <div className="alert alert-error" role="alert">{error}</div>}
            <button className="btn" style={{ width: "100%" }} disabled={busy || code.length !== 6}>
              {busy ? "Verifying…" : "Sign in"}
            </button>
            <p style={{ textAlign: "center", marginBottom: 0 }}>
              <button type="button" className="btn-link" onClick={() => sendCode()} disabled={busy}>
                Resend code
              </button>
              {" · "}
              <button
                type="button"
                className="btn-link"
                onClick={() => {
                  setStep("email");
                  setError(null);
                  setCode("");
                }}
              >
                Use a different email
              </button>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
