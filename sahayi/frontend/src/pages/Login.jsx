import { useState } from "react";
import ThemeToggle from "../components/ThemeToggle";
import { DEFAULT_TOKEN, getStoredToken } from "../auth/tokenAuth";

/**
 * Doctor portal sign-in. Shared-token MVP: any doctor pastes the dashboard token.
 * @param {{ onLogin: (token: string) => void }} props
 */
export default function Login({ onLogin }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [token, setToken] = useState(getStoredToken() || DEFAULT_TOKEN);

  async function handleLogin(e) {
    if (e) e.preventDefault();
    if (loading) return;
    setLoading(true);
    setError(null);
    const value = (token || "").trim();
    if (!value) {
      setError("Enter the dashboard access token.");
      setLoading(false);
      return;
    }
    try {
      onLogin(value);
    } catch (err) {
      setError(err.message || "Sign-in failed.");
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4 py-10">
      <ThemeToggle position="fixed-tr" />

      <div className="grid w-full max-w-4xl overflow-hidden rounded-3xl border border-line bg-surface shadow-card md:grid-cols-2">
        {/* Brand panel */}
        <div className="relative hidden flex-col justify-between bg-ink p-10 text-white md:flex">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-500 font-display text-base font-bold">S</span>
            <span className="font-display text-xl font-bold tracking-tight">SAHAYI</span>
          </div>
          <div>
            <h2 className="font-display text-2xl font-bold leading-tight">Patient insights, when you need them.</h2>
            <p className="mt-3 max-w-xs text-sm text-slate-300">
              Remote monitoring for your rural cohort — risk, symptoms, and trends in one calm console.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {["Live risk", "Symptoms", "Trends", "Alerts"].map((t) => (
              <span key={t} className="rounded-full bg-white/10 px-3 py-1 text-[11px] font-semibold text-slate-200">{t}</span>
            ))}
          </div>
        </div>

        {/* Form panel */}
        <div className="p-8 sm:p-10">
          <h1 className="font-display text-2xl font-bold tracking-tight text-ink">Doctor sign-in</h1>
          <p className="mt-1 text-sm text-ink-muted">Enter your dashboard access token to continue.</p>

          <form onSubmit={handleLogin} className="mt-8 space-y-4">
            <label className="block space-y-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">Access token</span>
              <input
                type="text"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="Dashboard token"
                className="w-full rounded-xl border border-line bg-canvas px-4 py-3 text-sm font-medium text-ink outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
              />
            </label>
            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-600 py-3 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60"
            >
              {loading ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" /> : null}
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          {error && (
            <div className="mt-4 flex items-center gap-2 rounded-xl bg-red-50 px-3 py-2 text-xs font-medium text-risk-red">
              {error}
            </div>
          )}

          <p className="mt-6 text-center text-[11px] text-ink-faint">For authorised medical professionals only.</p>
        </div>
      </div>
    </div>
  );
}
