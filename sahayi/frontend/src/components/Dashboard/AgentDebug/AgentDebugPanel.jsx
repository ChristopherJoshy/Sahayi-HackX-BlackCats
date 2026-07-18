import { Speech, ShieldCheck, FileText, Send, Microscope } from "lucide-react";
import AgentTimelineGraph from "./AgentTimelineGraph";

const AGENT_CONFIG = [
  { id: "talker", name: "Voice Interface", icon: Speech, color: "text-sky-600", bg: "bg-sky-50" },
  { id: "note_taker", name: "Signal Extractor", icon: FileText, color: "text-amber-600", bg: "bg-amber-50" },
  { id: "safety", name: "Safety Validator", icon: ShieldCheck, color: "text-emerald-600", bg: "bg-emerald-50" },
  { id: "messenger", name: "Context Summarizer", icon: Send, color: "text-indigo-600", bg: "bg-indigo-50" },
  { id: "spotter", name: "Population Analyzer", icon: Microscope, color: "text-brand-600", bg: "bg-brand-50" },
];

/**
 * Live multi-agent status + event log. Debug-only view.
 * @param {{ events: object[], patients?: object[], live?: object }} props
 */
export default function AgentDebugPanel({ events = [], patients = [], live = {} }) {
  const latest = events[0]?.event;
  const activeAgents = {
    talker: latest === "call_started" || latest === "call_ended",
    note_taker: latest === "new_signal",
    safety: latest === "safety_check" || latest === "doctor_summary",
    messenger: latest === "doctor_summary",
    spotter: latest === "risk_update" || latest === "hypothesis_generated",
  };

  const getPatientName = (pid) => {
    if (!pid) return "System";
    const p = patients.find((x) => x.id === pid || x.patient_id === pid);
    return p ? p.patient_name || p.name : `Patient ${String(pid).slice(0, 8)}`;
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-2.5 md:grid-cols-5">
        {AGENT_CONFIG.map((a) => {
          const on = activeAgents[a.id];
          return (
            <div key={a.id} className={`rounded-xl border p-3 text-center transition ${on ? "border-brand-200 bg-brand-50" : "border-line bg-surface"}`}>
              <div className={`mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-full ${on ? `${a.bg} ${a.color}` : "bg-canvas text-ink-faint"}`}>
                <a.icon size={18} />
              </div>
              <p className={`text-[10px] font-semibold ${on ? "text-ink" : "text-ink-faint"}`}>{a.name}</p>
              {on && <span className="mt-1 inline-block rounded-full bg-white px-2 py-0.5 text-[8px] font-bold uppercase tracking-wide text-brand-600">Active</span>}
            </div>
          );
        })}
      </div>

      <div className="rounded-xl border border-line bg-surface p-4">
        <p className="eyebrow mb-3">Activity graph</p>
        <AgentTimelineGraph events={events} patients={patients} />
      </div>

      <div className="rounded-xl border border-line bg-surface">
        <div className="border-b border-line px-4 py-3">
          <p className="eyebrow">Event log</p>
        </div>
        <div className="max-h-72 overflow-x-auto scrollbar-thin">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-surface text-[10px] uppercase text-ink-faint">
              <tr>
                <th className="px-3 py-2 font-semibold">Time</th>
                <th className="px-3 py-2 font-semibold">Patient</th>
                <th className="px-3 py-2 font-semibold">Event</th>
                <th className="px-3 py-2 font-semibold">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {events.length === 0 ? (
                <tr><td colSpan={4} className="px-3 py-6 text-center text-ink-faint">Waiting for activity…</td></tr>
              ) : (
                events.slice(0, 20).map((e, i) => {
                  const p = e.payload || {};
                  const detail = (() => {
                    switch (e.event) {
                      case "new_signal": return `${p.fatigue ? "Fatigue " : ""}${p.chest_pain ? "Chest pain" : ""}${p.symptom_description ? p.symptom_description : ""}`.trim() || "Signal recorded";
                      case "risk_update": return `Score ${(Number(p.score) || 0).toFixed(2)} · ${p.status}`;
                      case "safety_check": return `Safe: ${p.safe_response ? "yes" : "no"}`;
                      case "doctor_summary": return "Summary generated";
                      case "call_started": return "Session started";
                      case "call_ended": return "Session ended";
                      case "emergency_started": return "Cascade started";
                      case "follow_up_due": return "Follow-up due";
                      default: return Object.keys(p).slice(0, 2).join(", ");
                    }
                  })();
                  return (
                    <tr key={i} className="hover:bg-canvas/60">
                      <td className="whitespace-nowrap px-3 py-2 text-ink-faint">{new Date(e.occurred_at || Date.now()).toLocaleTimeString()}</td>
                      <td className="whitespace-nowrap px-3 py-2 font-semibold text-ink">{getPatientName(p.patient_id ?? p.id)}</td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-brand-600">{e.event}</td>
                      <td className="px-3 py-2 text-ink-soft">{detail}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
