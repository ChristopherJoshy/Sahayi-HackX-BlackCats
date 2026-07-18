import SummaryCard from "../Alerts/SummaryCard";
import { BookOpen, Quote } from "lucide-react";

/**
 * Clinical research intelligence: narrative, citations, and population patterns.
 * @param {{ summary?: object, population?: object[], compact?: boolean }} props
 */
export default function ResearchPanel({ summary, population = [], compact = false }) {
  const citations = summary?.citations || [];

  if (compact) {
    return (
      <div className="space-y-4">
        {summary?.narrative && (
          <div>
            <p className="eyebrow mb-2">Clinical synthesis</p>
            <p className="rounded-xl border border-line bg-canvas p-3 text-sm leading-relaxed text-ink-soft">
              {summary.narrative}
            </p>
          </div>
        )}
        {population.length > 0 && (
          <div>
            <p className="eyebrow mb-2">Population patterns</p>
            <ul className="space-y-2">
              {population.slice(0, 4).map((item) => (
                <li
                  key={`${item.id}-${item.created_at}`}
                  className={`rounded-lg border p-2.5 text-sm ${
                    item.research_gap ? 'border-amber-200 bg-amber-50 text-risk-amber' : 'border-line bg-canvas text-ink-soft'
                  }`}
                >
                  <div className="font-medium">{item.pattern_json?.cluster?.join(' + ') || 'Pattern'}</div>
                  <div className="mt-1 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wide opacity-80">
                    <span>n={item.frequency}</span>
                    <span className={item.week_delta > 0 ? 'text-risk-red' : 'text-risk-green'}>
                      {item.week_delta > 0 ? '▲' : '▼'} {Math.abs(item.week_delta)}/wk
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
        {citations.length > 0 && (
          <div>
            <p className="eyebrow mb-2">Evidence</p>
            <ul className="space-y-1.5">
              {citations.slice(0, 3).map((cite) => (
                <li key={cite.pmid} className="flex items-start gap-2 text-xs text-ink-soft">
                  <Quote size={12} className="mt-0.5 shrink-0 text-brand-500" />
                  <span className="leading-snug">{cite.title}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SummaryCard summary={summary} />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-3">
          {summary?.narrative && (
            <div className="rounded-xl border border-line bg-canvas p-4 text-sm leading-relaxed text-ink-soft">
              {summary.narrative}
            </div>
          )}
          <p className="eyebrow">Latest citations</p>
          {citations.length === 0 ? (
            <p className="rounded-xl border border-line bg-canvas p-4 text-sm text-ink-muted">No citations available.</p>
          ) : (
            citations.map((cite) => (
              <article key={cite.pmid} className="rounded-xl border border-line bg-surface p-3">
                <div className="flex gap-2">
                  <Quote size={12} className="mt-1 shrink-0 text-brand-500" />
                  <div>
                    <p className="text-sm font-semibold text-ink">{cite.title}</p>
                    <p className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-ink-faint">PMID {cite.pmid} · {cite.year}</p>
                  </div>
                </div>
              </article>
            ))
          )}
        </div>
        <div className="space-y-3">
          <p className="eyebrow">Population insights</p>
          {population.length === 0 ? (
            <p className="rounded-xl border border-line bg-canvas p-4 text-sm text-ink-muted">No population data yet.</p>
          ) : (
            population.map((item) => (
              <article
                key={`${item.id}-${item.created_at}`}
                className={`rounded-xl border p-3 ${
                  item.research_gap ? 'border-amber-200 bg-amber-50' : 'border-line bg-surface'
                }`}
              >
                <p className={`text-sm font-semibold ${item.research_gap ? 'text-risk-amber' : 'text-ink'}`}>
                  {item.pattern_json?.cluster?.join(' + ') || 'Pattern'}
                </p>
                <div className="mt-2 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
                  <span>Frequency: {item.frequency}</span>
                  <span className={item.week_delta > 0 ? 'text-risk-red' : 'text-risk-green'}>
                    {item.week_delta > 0 ? '▲' : '▼'} Δ {item.week_delta}
                  </span>
                </div>
              </article>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
