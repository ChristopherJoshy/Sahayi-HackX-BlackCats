import React, { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Users, UserPlus, ArrowRight, Trash2, Search } from "lucide-react";

import Panel from "../components/ui/Panel";
import RiskBadge from "../components/ui/RiskBadge";
import RiskMeter from "../components/ui/RiskMeter";
import { usePatientData } from "../hooks/usePatientData";
import { useSearch } from "../context/SearchContext";
import { normalizeStatus } from "../lib/format";

export default function Patients() {
  const { patients = [], loading, error, deletePatient } = usePatientData();
  const { searchQuery } = useSearch();
  const location = useLocation();
  const successResult = location.state?.success;
  const [deletingId, setDeletingId] = useState(null);
  const [deleteError, setDeleteError] = useState("");

  const filtered = (patients || []).filter((p) => {
    const q = searchQuery.toLowerCase();
    return !q || p.patient_name?.toLowerCase().includes(q) || String(p.patient_id).includes(q);
  });

  const ordered = [...filtered].sort((a, b) => {
    const rank = (p) => (normalizeStatus(p.latest_status) === 'red' ? 0 : normalizeStatus(p.latest_status) === 'yellow' ? 1 : 2);
    const r = rank(a) - rank(b);
    return r !== 0 ? r : (Number(b.risk_score) || 0) - (Number(a.risk_score) || 0);
  });

  async function handleDelete(e, patientId, name) {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm(`Remove ${name} from your registry? This cannot be undone.`)) return;
    setDeletingId(patientId);
    setDeleteError("");
    try {
      await deletePatient(patientId);
    } catch (err) {
      setDeleteError(`Failed to delete ${name}: ${err.message}`);
      setDeletingId(null);
    }
  }

  return (
    <div className="w-full space-y-6 pb-12 animate-slideIn">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Registry</p>
          <h1 className="mt-1 font-display text-2xl font-bold tracking-tight text-ink">Patients</h1>
          <p className="mt-1 text-sm text-ink-muted">
            {patients.length} monitored · sorted by clinical priority
          </p>
        </div>
        <Link
          to="/setup"
          className="flex items-center gap-2 rounded-xl bg-ink px-5 py-2.5 text-sm font-semibold text-white shadow-card transition hover:bg-slate-700 active:scale-[0.98]"
        >
          <UserPlus size={18} strokeWidth={2.5} />
          Register Patient
        </Link>
      </div>

      {successResult?.message && (
        <div className="rounded-xl border border-green-200 bg-green-50 p-4 text-sm font-medium text-risk-green">
          {successResult.message}
          {successResult.voice_number && (
            <div className="mt-2 flex flex-wrap gap-4 text-xs font-semibold">
              <span>Voice line: {successResult.voice_number}</span>
              <span>WhatsApp: {successResult.whatsapp_number}</span>
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-medium text-risk-red">{error}</div>
      )}
      {deleteError && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-medium text-risk-red">{deleteError}</div>
      )}

      {loading ? (
        <p className="py-16 text-center text-sm text-ink-muted">Loading patient registry…</p>
      ) : ordered.length === 0 ? (
        <Panel>
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-canvas text-ink-faint">
              <Users size={28} />
            </div>
            <h3 className="mt-4 font-display text-lg font-semibold text-ink">
              {searchQuery ? 'No matching patients' : 'No patients yet'}
            </h3>
            <p className="mt-1 max-w-sm text-sm text-ink-muted">
              {searchQuery
                ? `Nothing matches “${searchQuery}”. Try another name or ID.`
                : 'Register a patient to start remote monitoring and risk tracking.'}
            </p>
            {!searchQuery && (
              <Link to="/setup" className="mt-5 flex items-center gap-2 rounded-xl bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-700">
                Register Patient <ArrowRight size={16} />
              </Link>
            )}
          </div>
        </Panel>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {ordered.map((p) => (
            <Link
              key={p.patient_id}
              to={`/patient/${p.patient_id}`}
              className="group relative rounded-2xl border border-line bg-surface p-5 shadow-card transition hover:border-brand-300 hover:shadow-card-hover"
            >
              <button
                onClick={(e) => handleDelete(e, p.patient_id, p.patient_name)}
                disabled={deletingId === p.patient_id}
                className="absolute right-3 top-3 rounded-lg border border-line p-2 text-ink-faint transition hover:border-red-200 hover:text-risk-red"
                title="Remove patient"
              >
                {deletingId === p.patient_id ? <span className="block h-3.5 w-3.5 animate-spin rounded-full border-2 border-ink-faint border-t-transparent" /> : <Trash2 size={14} />}
              </button>
              <div className="flex items-center justify-between pr-8">
                <p className="truncate text-base font-semibold text-ink">{p.patient_name}</p>
                <RiskBadge status={p.latest_status} size="sm" />
              </div>
              <div className="mt-4">
                <RiskMeter score={Number(p.risk_score) || 0} status={p.latest_status} showTrend />
              </div>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {(p.conditions || []).slice(0, 3).map((c) => (
                  <span key={c} className="rounded-md bg-canvas px-2 py-1 text-[11px] font-medium text-ink-soft">{c}</span>
                ))}
                {(p.conditions || []).length === 0 && (
                  <span className="text-[11px] text-ink-faint">No documented conditions</span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
