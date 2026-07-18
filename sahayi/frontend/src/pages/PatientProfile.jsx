import { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  Pill,
  Phone,
  Globe,
  Stethoscope,
  Activity,
  PhoneCall,
  History,
  Trash2,
  Save,
  X,
  Edit3,
  ShieldAlert,
  Users,
  MessageSquareHeart,
} from "lucide-react";

import Panel from "../components/ui/Panel";
import RiskBadge from "../components/ui/RiskBadge";
import RiskMeter from "../components/ui/RiskMeter";
import EscalationButton from "../components/Alerts/EscalationButton";
import { usePatientRecord } from "../hooks/usePatientRecord";
import { useWebSocket } from "../hooks/useWebSocket";
import { sahayiApi } from "../api/sahayi";
import { formatPhone, stripPhone, normalizeStatus, statusMeta, shortDate, clockTime } from "../lib/format";

const SIGNAL_FIELDS = ['fatigue', 'appetite', 'chest_pain', 'duration_days', 'severity'];

export default function PatientProfile({ user }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const { profile, risk, signals = [], loading, error, updatePatient, deletePatient } = usePatientRecord(id);
  const { live } = useWebSocket(user);

  const summary = live.summary && String(live.summary.patient_id) === String(id) ? live.summary : null;
  const hypothesis = live.hypothesis && String(live.hypothesis.patient_id) === String(id) ? live.hypothesis : null;

  const [relativeUpdates, setRelativeUpdates] = useState([]);
  useEffect(() => {
    let active = true;
    sahayiApi.getRelativeUpdates(id)
      .then((data) => { if (active) setRelativeUpdates(Array.isArray(data) ? data : []); })
      .catch(() => { if (active) setRelativeUpdates([]); });
    return () => { active = false; };
  }, [id, profile]);

  // Live relative submissions arrive over the dashboard socket.
  useEffect(() => {
    if (live?.relative_update && String(live.relative_update.patient_id) === String(id)) {
      setRelativeUpdates((prev) => [live.relative_update, ...prev.filter((u) => u.id !== live.relative_update.id)]);
    }
  }, [live, id]);

  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  useEffect(() => {
    if (profile?.patient) setEditForm(structuredClone(profile.patient));
  }, [profile]);

  if (loading) {
    return <p className="py-20 text-center text-sm text-ink-muted">Loading medical record…</p>;
  }
  if (error && !profile) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-5 text-sm font-medium text-risk-red">
        <ShieldAlert size={18} /> {error}
      </div>
    );
  }
  if (!profile?.patient) {
    return (
      <div className="py-20 text-center">
        <p className="font-display text-lg font-semibold text-ink">Record incomplete</p>
        <Link to="/patients" className="mt-3 inline-block text-sm font-semibold text-brand-600 hover:underline">Return to registry</Link>
      </div>
    );
  }

  const p = profile.patient;

  async function handleSave() {
    setIsSaving(true);
    try {
      await updatePatient(editForm);
      setIsEditing(false);
    } catch (err) {
      console.error(err);
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm(`Remove ${p.name}? All clinical records and history will be permanently deleted.`)) return;
    setIsDeleting(true);
    setDeleteError("");
    try {
      await deletePatient();
      navigate('/patients', { state: { success: { message: `${p.name} removed.` } } });
    } catch (err) {
      setDeleteError(`Failed to delete: ${err.message}`);
      setIsDeleting(false);
    }
  }

  const setField = (field, value) => setEditForm((f) => ({ ...f, [field]: value }));
  const setNested = (parent, field, value) => setEditForm((f) => ({ ...f, [parent]: { ...f[parent], [field]: value } }));
  const setMed = (i, field, value) => setEditForm((f) => ({ ...f, medicines: f.medicines.map((m, idx) => idx === i ? { ...m, [field]: value } : m) }));
  const addMed = () => setEditForm((f) => ({ ...f, medicines: [...f.medicines, { name: '', dose: '', frequency: '', timing: '' }] }));
  const removeMed = (i) => setEditForm((f) => ({ ...f, medicines: f.medicines.filter((_, idx) => idx !== i) }));

  return (
    <div className="w-full space-y-6 pb-12 animate-slideIn">
      {/* Header */}
      <div className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-lg font-bold text-brand-700">
              {p.name[0]}
            </div>
            <div>
              <p className="eyebrow">Active medical profile</p>
              <h1 className="font-display text-2xl font-bold tracking-tight text-ink">{p.name}</h1>
              <div className="mt-1 flex items-center gap-3 text-xs font-medium text-ink-muted">
                <span className="flex items-center gap-1"><Globe size={13} /> {p.language}</span>
                <span className="h-1 w-1 rounded-full bg-ink-faint" />
                <span className="flex items-center gap-1"><Phone size={13} /> {formatPhone(p.phone_number)}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isEditing ? (
              <>
                <button onClick={handleSave} disabled={isSaving} className="flex items-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50">
                  {isSaving ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" /> : <Save size={16} />} Save
                </button>
                <button onClick={() => { setIsEditing(false); setEditForm(structuredClone(p)); }} className="flex items-center gap-2 rounded-xl border border-line px-4 py-2.5 text-sm font-semibold text-ink-soft hover:bg-canvas">
                  <X size={16} /> Cancel
                </button>
              </>
            ) : (
              <>
                <button onClick={() => setIsEditing(true)} className="flex items-center gap-2 rounded-xl border border-line px-4 py-2.5 text-sm font-semibold text-ink-soft hover:bg-canvas">
                  <Edit3 size={16} /> Edit
                </button>
                <EscalationButton patientId={Number(id)} />
              </>
            )}
          </div>
        </div>
      </div>

      {deleteError && (
        <div className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-medium text-risk-red">
          <ShieldAlert size={18} /> {deleteError}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-6">
          {/* Clinical overview */}
          <Panel eyebrow="Overview" title="Clinical Snapshot" icon={Stethoscope}>
            {isEditing ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Full Name" value={editForm.name} onChange={(v) => setField('name', v)} />
                <Field label="Language" value={editForm.language} onChange={(v) => setField('language', v)} />
                <Field label="Phone" value={stripPhone(editForm.phone_number)} onChange={(v) => setField('phone_number', v)} />
              </div>
            ) : (
              <div className="space-y-5">
                <div>
                  <p className="eyebrow mb-2">Documented conditions</p>
                  {p.conditions?.length ? (
                    <div className="flex flex-wrap gap-2">
                      {p.conditions.map((c) => <span key={c} className="rounded-lg bg-canvas px-3 py-1.5 text-sm font-medium text-ink-soft">{c}</span>)}
                    </div>
                  ) : <p className="text-sm text-ink-muted">No conditions documented.</p>}
                </div>
                <div>
                  <p className="eyebrow mb-2">Active medications</p>
                  {p.medicines?.length ? (
                    <div className="grid gap-2 sm:grid-cols-2">
                      {p.medicines.map((m, i) => (
                        <div key={i} className="flex items-center gap-3 rounded-xl border border-line bg-surface p-3">
                          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-600"><Pill size={16} /></div>
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-ink">{m.name}</p>
                            <p className="truncate text-[11px] text-ink-muted">{[m.dose, m.frequency, m.timing].filter(Boolean).join(' · ')}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : <p className="text-sm text-ink-muted">No active medications.</p>}
                </div>
              </div>
            )}
          </Panel>

          {/* Support network */}
          <Panel eyebrow="Support" title="Emergency & Family Contacts" icon={Users}>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-xl border border-line bg-canvas p-4">
                <p className="eyebrow mb-1.5">Emergency contact</p>
                <p className="text-sm font-semibold text-ink">{p.emergency_contact?.name}</p>
                <p className="text-xs text-ink-muted">{formatPhone(p.emergency_contact?.phone)}</p>
              </div>
              <div className="space-y-2">
                <p className="eyebrow">Relatives</p>
                {p.relatives?.length ? p.relatives.map((r, i) => (
                  <div key={i} className="rounded-xl border border-line bg-canvas p-3">
                    <p className="text-sm font-semibold text-ink">{r.name || 'Unknown'}</p>
                    <p className="text-xs text-ink-muted">{r.relationship} · {formatPhone(r.phone)}</p>
                  </div>
                )) : <p className="text-sm text-ink-muted">No relatives documented.</p>}
              </div>
            </div>
          </Panel>

          {/* Signal timeline - clinical only */}
          <Panel eyebrow="History" title="Clinical Signal Timeline" icon={History}>
            {signals.length === 0 ? (
              <p className="py-8 text-center text-sm text-ink-muted">No clinical signals recorded yet.</p>
            ) : (
              <div className="grid gap-3 md:grid-cols-2">
                {signals.map((s) => (
                  <div key={s.id} className={`relative rounded-xl border p-4 ${s.red_flag ? 'border-red-200 bg-red-50' : 'border-line bg-surface'}`}>
                    {s.red_flag && (
                      <span className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-risk-red text-white shadow">
                        <ShieldAlert size={11} />
                      </span>
                    )}
                    <div className="flex items-center justify-between">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">{shortDate(s.created_at)}</p>
                      {s.severity != null && (
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${s.severity >= 4 ? 'bg-red-100 text-risk-red' : s.severity >= 2 ? 'bg-amber-100 text-risk-amber' : 'bg-green-100 text-risk-green'}`}>
                          Lvl {s.severity}
                        </span>
                      )}
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      {SIGNAL_FIELDS.filter((k) => s[k] !== null && s[k] !== undefined && s[k] !== '').map((k) => (
                        <div key={k}>
                          <p className="text-[10px] font-medium uppercase tracking-wide text-ink-faint">{k.replace('_', ' ')}</p>
                          <p className="text-sm font-semibold text-ink-soft">{String(s[k])}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>

        <div className="space-y-6">
          {/* Risk card */}
          <Panel eyebrow="Current risk" title="Risk Assessment" icon={Activity}>
            <div className="flex items-center justify-between">
              <RiskBadge status={risk?.status || 'green'} size="md" />
              <span className="font-mono text-3xl font-bold text-ink">{(Number(risk?.score) || 0).toFixed(2)}</span>
            </div>
            <div className="mt-4">
              <RiskMeter score={Number(risk?.score) || 0} status={risk?.status || 'green'} trend={risk?.trend} showTrend />
            </div>
            {risk?.breakdown && (
              <div className="mt-4 grid grid-cols-3 gap-2 border-t border-line pt-4 text-center">
                <Metric label="Severity" value={risk.breakdown.severity_component} />
                <Metric label="Duration" value={risk.breakdown.duration_component} />
                <Metric label="Change" value={risk.breakdown.change_component} />
              </div>
            )}
            {risk?.is_anomaly && (
              <p className="mt-3 flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-xs font-semibold text-risk-red">
                <ShieldAlert size={14} /> Anomaly detected vs. patient baseline (z={risk.z_score?.toFixed(2)})
              </p>
            )}
          </Panel>

          {/* Summary */}
          {summary && (
            <Panel eyebrow="Synthesis" title="Latest Clinical Summary" icon={Activity}>
              <p className="whitespace-pre-line text-sm leading-relaxed text-ink-soft">{summary.summary_text}</p>
            </Panel>
          )}

          {/* Relative updates - clinical summaries only, no raw transcripts */}
          <Panel eyebrow="Family" title="Relative Updates" icon={MessageSquareHeart} action={<span className="text-[11px] font-semibold text-ink-faint">{relativeUpdates.length} total</span>}>
            {relativeUpdates.length === 0 ? (
              <p className="py-6 text-center text-sm text-ink-muted">No updates from family yet.</p>
            ) : (
              <ul className="space-y-2.5">
                {relativeUpdates.map((u) => (
                  <li key={u.id} className="rounded-xl border border-line bg-surface p-3.5">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-ink">{u.relative_name}</p>
                      <span className="rounded-full bg-canvas px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-ink-faint">{u.update_type}</span>
                    </div>
                    <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{u.clinical_summary}</p>
                    {u.source_detail && (
                      <p className="mt-1 text-[11px] font-medium text-brand-600">{u.source_detail}</p>
                    )}
                    <p className="mt-1.5 text-[10px] text-ink-faint">{shortDate(u.created_at)} · {clockTime(u.created_at)}</p>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          {/* Call history */}
          <Panel eyebrow="Telephony" title="Call Logs" icon={PhoneCall} action={<span className="text-[11px] font-semibold text-ink-faint">{profile.calls.length} total</span>}>
            {profile.calls.length === 0 ? (
              <p className="py-6 text-center text-sm text-ink-muted">No communication history.</p>
            ) : (
              <ul className="space-y-2">
                {profile.calls.map((c) => (
                  <li key={c.session_id} className="flex items-center justify-between rounded-lg border border-line bg-surface px-3 py-2.5">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-ink">{c.status}</p>
                      <p className="text-[10px] text-ink-faint">{shortDate(c.started_at)} · {clockTime(c.started_at)}</p>
                    </div>
                    {c.risk_score > 0 && <span className="font-mono text-sm font-bold text-risk-red">{Number(c.risk_score).toFixed(1)}</span>}
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          {isEditing && (
            <button onClick={handleDelete} disabled={isDeleting} className="flex w-full items-center justify-center gap-2 rounded-xl border border-red-200 bg-red-50 py-3 text-sm font-semibold text-risk-red hover:bg-red-100">
              {isDeleting ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-risk-red border-t-transparent" /> : <Trash2 size={16} />} Delete Record
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">{label}</span>
      <input
        className="w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-sm font-medium text-ink outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function Metric({ label, value }) {
  return (
    <div>
      <p className="text-[10px] font-medium uppercase tracking-wide text-ink-faint">{label}</p>
      <p className="mt-0.5 font-mono text-base font-bold text-ink-soft">{Number(value) || 0}</p>
    </div>
  );
}
