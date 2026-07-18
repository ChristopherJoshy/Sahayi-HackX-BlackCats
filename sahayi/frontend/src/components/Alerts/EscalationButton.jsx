/**
 * Button that triggers the family alert escalation flow.
 * @param {{ patientId: number, compact?: boolean }} props Component props.
 * @returns {JSX.Element} Rendered escalation button.
 */
import { useState } from "react";

import { sahayiApi } from "../../api/sahayi";
import { ShieldAlert } from "lucide-react";

export default function EscalationButton({ patientId, compact = false }) {
  const [status, setStatus] = useState("idle");

  async function handleEscalate() {
    setStatus("loading");
    try {
      await sahayiApi.escalatePatient(patientId);
      setStatus("sent");
    } catch {
      setStatus("error");
    }
  }

  const base = compact
    ? "rounded-lg bg-red-50 px-2.5 py-1.5 text-[11px] font-semibold text-risk-red hover:bg-red-100"
    : "rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white shadow-card hover:bg-red-700";

  const label = status === "loading" ? "Alerting…" : status === "sent" ? "Alert Sent" : status === "error" ? "Retry" : compact ? "Escalate" : "Escalate to Family";

  return (
    <button className={base} onClick={handleEscalate} title="Trigger a family check-in alert">
      {!compact && <ShieldAlert size={16} className="mr-2 inline" />}
      {label}
    </button>
  );
}
