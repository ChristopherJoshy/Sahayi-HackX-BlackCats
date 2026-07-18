import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { statusMeta, normalizeStatus } from "../../lib/format";

const TREND = {
  WORSENING: { icon: TrendingUp, cls: 'text-risk-red', label: 'Worsening' },
  IMPROVING: { icon: TrendingDown, cls: 'text-risk-green', label: 'Improving' },
  STABLE: { icon: Minus, cls: 'text-ink-faint', label: 'Stable' },
};

/**
 * "Vitals Pulse" — the signature risk meter.
 * A segmented bar that fills to the risk score and shifts colour by status,
 * with an optional trend readout. Encodes severity at a glance, no chart needed.
 *
 * @param {{ score: number, status: string, trend?: string, showTrend?: boolean, height?: string }} props
 */
export default function RiskMeter({ score = 0, status, trend = 'STABLE', showTrend = true, height = 'h-2.5' }) {
  const meta = statusMeta(normalizeStatus(status));
  const pct = Math.max(2, Math.min(100, Math.round((Number(score) || 0) * 100)));
  const t = TREND[trend] || TREND.STABLE;
  const TrendIcon = t.icon;

  return (
    <div className="w-full">
      <div className={`flex w-full items-center gap-2 ${height} rounded-full bg-slate-100 overflow-hidden`}>
        <div
          className={`h-full rounded-full ${meta.dot} transition-[width] duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showTrend && (
        <div className="mt-1.5 flex items-center justify-between">
          <span className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide ${t.cls}`}>
            <TrendIcon size={12} />
            {t.label}
          </span>
          <span className="font-mono text-[10px] font-semibold text-ink-muted">
            {pct}%
          </span>
        </div>
      )}
    </div>
  );
}
