import { FileText, ClipboardList } from "lucide-react";
import RiskBadge from "../ui/RiskBadge";

/**
 * Doctor-facing clinical summary card. Observational only.
 * @param {{ summary?: object }} props
 */
export default function SummaryCard({ summary }) {
  if (!summary) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-dashed border-line bg-canvas p-5 text-sm text-ink-muted">
        <ClipboardList size={20} className="text-ink-faint" />
        No clinical summary generated yet. Summaries appear after a patient session.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-line bg-surface p-5">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText size={15} className="text-brand-600" />
          <p className="text-sm font-semibold text-ink">{summary.patient_name || 'Clinical Summary'}</p>
        </div>
        <RiskBadge status={summary.risk_score > 0.6 ? 'red' : summary.risk_score > 0.3 ? 'yellow' : 'green'} score={summary.risk_score} />
      </div>
      <p className="max-h-60 overflow-y-auto scrollbar-thin whitespace-pre-line text-sm leading-relaxed text-ink-soft">
        {summary.summary_text}
      </p>
    </div>
  );
}
