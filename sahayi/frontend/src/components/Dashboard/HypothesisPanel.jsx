import { FlaskConical, AlertCircle, TrendingUp } from "lucide-react";
import { statusMeta } from "../../lib/format";

/**
 * Active clinical hypothesis + research gaps. Observational, never diagnostic.
 * @param {{ hypothesis?: object, population?: object[], compact?: boolean }} props
 */
export default function HypothesisPanel({ hypothesis, population = [], compact = false }) {
  const gaps = population.filter((item) => item.research_gap);

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-line bg-canvas p-4">
        <div className="flex items-center justify-between">
          <p className="eyebrow">Testable hypothesis</p>
          {hypothesis?.confidence && (
            <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-brand-600">
              {hypothesis.confidence} confidence
            </span>
          )}
        </div>
        <p className="mt-2 text-sm font-medium italic leading-relaxed text-ink-soft">
          “{hypothesis?.statement || "Insufficient evidence to generate a testable hypothesis yet."}”
        </p>
      </div>

      {gaps.length > 0 && (
        <div>
          <p className="eyebrow mb-2">Research gaps</p>
          <ul className="space-y-2">
            {gaps.slice(0, compact ? 3 : 6).map((gap) => (
              <li
                key={`${gap.id}-${gap.created_at}`}
                className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-sm font-medium text-risk-amber"
              >
                <AlertCircle size={14} className="shrink-0" />
                <span className="truncate">{gap.pattern_json?.cluster?.join(' + ') || 'Unspecified pattern'}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!hypothesis && gaps.length === 0 && (
        <p className="text-sm text-ink-muted">No hypotheses or research gaps identified yet.</p>
      )}
    </div>
  );
}
