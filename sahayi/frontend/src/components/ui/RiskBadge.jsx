import { normalizeStatus, statusMeta } from "../../lib/format";

/**
 * Compact risk/status pill. Shows the colour label (Stable / Watch / Critical).
 * @param {{ status: string, score?: number }} props
 */
export default function RiskBadge({ status, score, size = "sm" }) {
  const meta = statusMeta(normalizeStatus(status));
  const pad = size === "sm" ? "px-2.5 py-1 text-[10px]" : "px-3 py-1.5 text-xs";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-semibold uppercase tracking-wide ${meta.bg} ${meta.text} ${pad}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
      {typeof score === 'number' && (
        <span className="font-mono font-bold opacity-80">{score.toFixed(1)}</span>
      )}
    </span>
  );
}
