import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Users,
  AlertTriangle,
  Activity,
  Plus,
  Calendar,
  ArrowUpRight,
  PhoneCall,
  ShieldAlert,
  FlaskConical,
  BookOpen,
  Radio,
  Sparkles,
} from "lucide-react";

import Panel from "../components/ui/Panel";
import RiskBadge from "../components/ui/RiskBadge";
import RiskMeter from "../components/ui/RiskMeter";
import StatusDot from "../components/ui/StatusDot";
import EscalationButton from "../components/Alerts/EscalationButton";
import ResearchPanel from "../components/Dashboard/ResearchPanel";
import HypothesisPanel from "../components/Dashboard/HypothesisPanel";
import { usePatientData } from "../hooks/usePatientData";
import { normalizeStatus, statusMeta } from "../lib/format";

export default function Dashboard({ user, live = {}, patients: livePatients = [], connectionState = "connected" }) {
  const { patients = [], population = [], loading, error } = usePatientData();
  const [insightTab, setInsightTab] = useState("live");

  // Merge live socket updates over the GET snapshot so risk/status refresh in real time.
  const liveById = new Map(livePatients.map((p) => [p.patient_id, p]));
  const allPatients = patients.map((p) => {
    const liveEntry = liveById.get(p.patient_id);
    if (!liveEntry) return p;
    return {
      ...p,
      risk_score: liveEntry.risk_score ?? p.risk_score,
      latest_status: liveEntry.status ?? liveEntry.latest_status ?? p.latest_status,
      latest_symptom: liveEntry.latest_symptom ?? p.latest_symptom,
      severity: liveEntry.severity ?? p.severity,
      latest_summary: liveEntry.summary_text ? { ...p.latest_summary, summary_text: liveEntry.summary_text, risk_score: liveEntry.risk_score } : p.latest_summary,
    };
  });
  // Include any patients that arrived via live events but not in the GET snapshot yet.
  for (const liveEntry of liveById.values()) {
    if (!allPatients.some((p) => p.patient_id === liveEntry.patient_id)) {
      allPatients.push(liveEntry);
    }
  }
  const total = allPatients.length;
  const critical = allPatients.filter((p) => normalizeStatus(p.latest_status) === 'red').length;
  const watch = allPatients.filter((p) => normalizeStatus(p.latest_status) === 'yellow').length;

  // Critical-first ordering: red -> yellow -> green, then by risk score.
  const ordered = [...allPatients].sort((a, b) => {
    const rank = (p) => (normalizeStatus(p.latest_status) === 'red' ? 0 : normalizeStatus(p.latest_status) === 'yellow' ? 1 : 2);
    const r = rank(a) - rank(b);
    return r !== 0 ? r : (Number(b.risk_score) || 0) - (Number(a.risk_score) || 0);
  });

  const attention = ordered.filter((p) => normalizeStatus(p.latest_status) !== 'green');
  const emergency = live.emergencies?.[0];
  const summary = live.summary || allPatients.find((p) => p.latest_summary)?.latest_summary || null;

  const today = new Date().toLocaleDateString('en-IN', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  });

  const kpis = [
    { label: 'Patients Monitored', value: total, icon: Users, tone: 'text-brand-600 bg-brand-50' },
    { label: 'Critical', value: critical, icon: AlertTriangle, tone: 'text-risk-red bg-red-50' },
    { label: 'Needs Watch', value: watch, icon: Activity, tone: 'text-risk-amber bg-amber-50' },
  ];

  const tabs = [
    { id: 'live', label: 'Live', icon: PhoneCall },
    { id: 'insights', label: 'Insights', icon: Sparkles },
  ];

  return (
    <div className="w-full space-y-6 pb-4 animate-slideIn">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
            <StatusDot status={connectionState === 'connected' ? 'green' : 'yellow'} pulse={connectionState === 'connected'} />
            Live · {connectionState}
          </div>
          <h1 className="mt-2 font-display text-2xl font-bold tracking-tight text-ink">
            Good to see you, {user.displayName?.split(' ')[0] || 'Doctor'}.
          </h1>
          <p className="mt-1 text-sm text-ink-muted">
            {total} {total === 1 ? 'patient' : 'patients'} under remote monitoring.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-2 rounded-xl border border-line bg-surface px-4 py-2.5 text-sm font-medium text-ink-soft shadow-card sm:flex">
            <Calendar size={16} className="text-brand-600" />
            {today}
          </div>
          <Link to="/setup" className="flex items-center gap-2 rounded-xl bg-ink px-5 py-2.5 text-sm font-semibold text-white shadow-card transition hover:bg-slate-700 active:scale-[0.98]">
            <Plus size={18} strokeWidth={2.5} /> Add Patient
          </Link>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-medium text-risk-red">
          <AlertTriangle size={18} /> {error}
        </div>
      )}

      {emergency && (
        <div className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-semibold text-risk-red animate-slideIn">
          <ShieldAlert size={18} className="animate-pulse" />
          Emergency cascade active for {emergency.patient_name || 'a patient'} · {emergency.kind.replace(/_/g, ' ')}
        </div>
      )}

      {/* KPI strip */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {kpis.map((k) => (
          <div key={k.label} className="panel flex items-center justify-between p-4">
            <div>
              <p className="eyebrow">{k.label}</p>
              <p className="mt-1.5 font-display text-3xl font-bold text-ink">{k.value}</p>
            </div>
            <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${k.tone}`}>
              <k.icon size={20} />
            </div>
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-6">
          {/* Attention Queue */}
          <Panel
            eyebrow="Act now"
            title="Attention Queue"
            icon={AlertTriangle}
            action={
              <span className="rounded-full bg-red-50 px-3 py-1 text-[10px] font-bold uppercase tracking-wide text-risk-red">
                {attention.length} need review
              </span>
            }
          >
            {attention.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-center">
                <StatusDot status="green" />
                <p className="mt-3 text-sm font-medium text-ink-muted">All patients are stable right now.</p>
              </div>
            ) : (
              <ul className="divide-y divide-line">
                {attention.map((p) => {
                  const meta = statusMeta(normalizeStatus(p.latest_status));
                  const reason = p.latest_symptom && !p.latest_symptom.toLowerCase().startsWith('no symptom')
                    ? p.latest_symptom
                    : (p.severity ? `Severity ${p.severity}/5 recorded` : 'Status flagged by monitoring');
                  return (
                    <li key={p.patient_id}>
                      <Link to={`/patient/${p.patient_id}`} className="group flex items-center gap-4 py-3.5 transition-colors hover:bg-canvas/60">
                        <span className={`h-9 w-1 rounded-full ${meta.dot}`} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <p className="truncate text-sm font-semibold text-ink">{p.patient_name}</p>
                            <RiskBadge status={p.latest_status} size="sm" />
                          </div>
                          <p className="mt-0.5 truncate text-xs text-ink-muted">{reason}</p>
                        </div>
                        <div className="hidden w-40 sm:block">
                          <RiskMeter score={Number(p.risk_score) || 0} status={p.latest_status} showTrend={false} />
                        </div>
                        <ArrowUpRight size={18} className="text-ink-faint transition-colors group-hover:text-ink" />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </Panel>

          {/* All patients */}
          <Panel eyebrow="Cohort" title="Patient Risk Overview" icon={Users}>
            {loading ? (
              <p className="py-8 text-center text-sm text-ink-muted">Loading patient roster…</p>
            ) : ordered.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-center">
                <Users size={32} className="text-ink-faint" />
                <p className="mt-3 text-sm font-medium text-ink-muted">No patients registered yet.</p>
                <Link to="/setup" className="mt-4 text-sm font-semibold text-brand-600 hover:underline">Add your first patient</Link>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {ordered.map((p) => (
                  <Link key={p.patient_id} to={`/patient/${p.patient_id}`} className="group rounded-xl border border-line bg-surface p-4 transition hover:border-brand-300 hover:shadow-card-hover">
                    <div className="flex items-center justify-between">
                      <p className="truncate text-sm font-semibold text-ink">{p.patient_name}</p>
                      <RiskBadge status={p.latest_status} score={Number(p.risk_score) || 0} size="sm" />
                    </div>
                    <div className="mt-3">
                      <RiskMeter score={Number(p.risk_score) || 0} status={p.latest_status} showTrend />
                    </div>
                    {p.conditions?.length > 0 && (
                      <p className="mt-3 truncate text-xs text-ink-muted">{p.conditions.join(' · ')}</p>
                    )}
                  </Link>
                ))}
              </div>
            )}
          </Panel>
        </div>

        {/* Right rail — tabbed so insights don't crowd a large roster */}
        <div className="space-y-6">
          <div className="panel overflow-hidden">
            <div className="flex border-b border-line">
              {tabs.map((t) => {
                const active = insightTab === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => setInsightTab(t.id)}
                    className={`flex flex-1 items-center justify-center gap-2 py-3 text-sm font-semibold transition ${
                      active ? "border-b-2 border-brand-600 text-ink" : "text-ink-faint hover:text-ink-soft"
                    }`}
                  >
                    <t.icon size={16} /> {t.label}
                  </button>
                );
              })}
            </div>

            <div className="p-5">
              {insightTab === 'live' ? (
                <div className="space-y-5">
                  {/* Live call */}
                  <div>
                    <p className="eyebrow mb-2">Live interaction</p>
                    {live.activeCall ? (
                      <div className="flex items-center gap-3 rounded-xl border border-line bg-canvas p-3">
                        <span className="relative flex h-10 w-10 items-center justify-center rounded-full bg-brand-50 text-brand-600">
                          <PhoneCall size={18} />
                          <span className="absolute -right-0.5 -top-0.5 flex h-3 w-3">
                            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-risk-green opacity-70" />
                            <span className="relative inline-flex h-3 w-3 rounded-full bg-risk-green" />
                          </span>
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-semibold text-ink">{live.activeCall.patient_name}</p>
                          <p className="text-xs text-ink-muted">{live.activeCall.language} · Active session</p>
                        </div>
                        <Link to={`/patient/${live.activeCall.patient_id}`} className="text-xs font-semibold text-brand-600 hover:underline">Open</Link>
                      </div>
                    ) : (
                      <p className="text-sm text-ink-muted">No active patient call.</p>
                    )}
                  </div>

                  {/* Latest summary, only if present */}
                  {summary && (
                    <div>
                      <p className="eyebrow mb-2">Latest clinical summary</p>
                      <div className="rounded-xl border border-line bg-canvas p-3">
                        <div className="mb-1.5 flex items-center justify-between">
                          <p className="text-xs font-semibold text-ink">{summary.patient_name || 'Patient'}</p>
                          {summary.patient_id && <EscalationButton patientId={summary.patient_id} compact />}
                        </div>
                        <p className="max-h-44 overflow-y-auto scrollbar-thin whitespace-pre-line text-sm leading-relaxed text-ink-soft">
                          {summary.summary_text}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-5">
                  <div>
                    <p className="eyebrow mb-2 flex items-center gap-1.5"><FlaskConical size={13} /> Active hypothesis</p>
                    <HypothesisPanel hypothesis={live.hypothesis} population={population} compact />
                  </div>
                  <div>
                    <p className="eyebrow mb-2 flex items-center gap-1.5"><Radio size={13} /> Population & research</p>
                    <ResearchPanel summary={summary} population={population} compact />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
