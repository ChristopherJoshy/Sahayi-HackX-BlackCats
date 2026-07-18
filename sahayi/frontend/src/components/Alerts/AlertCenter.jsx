import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import { Bell, ShieldAlert, AlertTriangle, PhoneCall, Clock, Check } from "lucide-react";

/**
 * Build a unified alert list from live dashboard state.
 * Alerts are ranked critical-first and deduplicated by key.
 * @param {object} live Derived live state from useWebSocket.
 * @param {object[]} patients Dashboard patient cards (for critical-status alerts).
 * @returns {object[]} Alert items { key, level, icon, title, detail, to?, at? }.
 */
export function buildAlerts(live, patients = []) {
  const alerts = [];

  for (const em of live.emergencies || []) {
    alerts.push({
      key: `em-${em.kind}-${em.patient_id}-${em.at}`,
      level: 'critical',
      icon: ShieldAlert,
      title: 'Emergency cascade active',
      detail: `${em.patient_name || 'A patient'} · ${em.kind.replace(/_/g, ' ')}`,
      to: em.patient_id ? `/patient/${em.patient_id}` : null,
      at: em.at,
    });
  }

  for (const p of patients) {
    if (p.latest_status === 'red') {
      alerts.push({
        key: `crit-${p.patient_id}`,
        level: 'critical',
        icon: AlertTriangle,
        title: `${p.patient_name} is critical`,
        detail: p.latest_symptom && !p.latest_symptom.toLowerCase().startsWith('no symptom')
          ? p.latest_symptom
          : `Risk ${(Number(p.risk_score) || 0).toFixed(1)}`,
        to: `/patient/${p.patient_id}`,
      });
    }
  }

  for (const fu of live.followUps || []) {
    alerts.push({
      key: `fu-${fu.summary_id || fu.patient_id}`,
      level: 'watch',
      icon: Clock,
      title: 'Follow-up due',
      detail: fu.patient_name || 'A patient needs a follow-up review',
      to: fu.patient_id ? `/patient/${fu.patient_id}` : null,
    });
  }

  if (live.activeCall) {
    alerts.push({
      key: `call-${live.activeCall.session_id || live.activeCall.patient_id}`,
      level: 'info',
      icon: PhoneCall,
      title: 'Live patient call',
      detail: `${live.activeCall.patient_name} · ${live.activeCall.language}`,
      to: `/patient/${live.activeCall.patient_id}`,
    });
  }

  const rank = { critical: 0, watch: 1, info: 2 };
  return alerts.sort((a, b) => rank[a.level] - rank[b.level]);
}

/**
 * Navbar notification bell with a dropdown alert center.
 * @param {object[]} alerts Unified alert list.
 */
export default function AlertCenter({ alerts = [] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const criticalCount = alerts.filter((a) => a.level === 'critical').length;

  useEffect(() => {
    function onClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const tone = {
    critical: 'text-risk-red bg-red-50',
    watch: 'text-risk-amber bg-amber-50',
    info: 'text-brand-600 bg-brand-50',
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-line bg-surface text-ink-soft transition hover:bg-canvas"
        aria-label="Alerts"
      >
        <Bell size={18} />
        {alerts.length > 0 && (
          <span className={`absolute -right-1 -top-1 flex h-5 min-w-[1.25rem] items-center justify-center rounded-full px-1 text-[10px] font-bold ${criticalCount ? 'bg-risk-red text-white' : 'bg-risk-amber text-white'}`}>
            {alerts.length}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-12 z-50 w-80 overflow-hidden rounded-2xl border border-line bg-surface shadow-card-hover">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <p className="text-sm font-semibold text-ink">Alerts</p>
            <span className="rounded-full bg-canvas px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-muted">{alerts.length}</span>
          </div>
          <div className="max-h-96 overflow-y-auto scrollbar-thin">
            {alerts.length === 0 ? (
              <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
                <Check size={20} className="text-risk-green" />
                <p className="text-sm font-medium text-ink-muted">You're all caught up.</p>
              </div>
            ) : (
              <ul className="divide-y divide-line">
                {alerts.map((a) => {
                  const Icon = a.icon;
                  const body = (
                    <div className="flex items-start gap-3 px-4 py-3 transition hover:bg-canvas/70">
                      <span className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${tone[a.level]}`}>
                        <Icon size={15} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold text-ink">{a.title}</p>
                        <p className="truncate text-xs text-ink-muted">{a.detail}</p>
                      </div>
                    </div>
                  );
                  return a.to ? (
                    <li key={a.key}>
                      <Link to={a.to} onClick={() => setOpen(false)}>{body}</Link>
                    </li>
                  ) : (
                    <li key={a.key}>{body}</li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
