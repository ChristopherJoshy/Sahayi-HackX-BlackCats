import { LogOut } from "lucide-react";
import ThemeToggle from "../components/ThemeToggle.jsx";

export default function Settings({ onLogout }) {
  return (
    <div className="w-full space-y-6 pb-12 animate-slideIn">
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight text-ink">Settings</h1>
        <p className="mt-1 text-sm text-ink-muted">Preferences and session for this device.</p>
      </div>

      <section className="panel p-5">
        <h2 className="eyebrow mb-3">Appearance</h2>
        <p className="mb-3 text-sm text-ink-soft">Switch between light and dark interface.</p>
        <ThemeToggle position="relative" />
      </section>

      <section className="panel p-5">
        <h2 className="eyebrow mb-3">Account</h2>
        <p className="mb-4 text-sm text-ink-soft">Sign out of the doctor console on this device.</p>
        <button
          onClick={onLogout}
          className="flex items-center gap-2 rounded-xl bg-red-50 px-5 py-2.5 text-sm font-semibold text-risk-red transition hover:bg-red-100"
        >
          <LogOut size={16} strokeWidth={2.5} />
          Logout
        </button>
      </section>
    </div>
  );
}
