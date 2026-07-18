/**
 * Shared display helpers for the SAHAYI clinical console.
 */

export const STATUS_META = {
  red: { label: 'Critical', hex: '#DC2626', text: 'text-risk-red', bg: 'bg-red-50', ring: 'ring-red-500', dot: 'bg-risk-red' },
  yellow: { label: 'Watch', hex: '#D97706', text: 'text-risk-amber', bg: 'bg-amber-50', ring: 'ring-amber-500', dot: 'bg-risk-amber' },
  green: { label: 'Stable', hex: '#16A34A', text: 'text-risk-green', bg: 'bg-green-50', ring: 'ring-green-500', dot: 'bg-risk-green' },
};

export function statusMeta(status) {
  return STATUS_META[status] || STATUS_META.green;
}

/** Normalize a backend status string ('red' | 'yellow' | 'green' | fallback). */
export function normalizeStatus(value) {
  const v = String(value || '').toLowerCase();
  if (v === 'red') return 'red';
  if (v === 'yellow' || v === 'amber') return 'yellow';
  return 'green';
}

/** Format a +91 / whatsapp phone for display. */
export function formatPhone(phone) {
  if (!phone) return '—';
  let clean = String(phone).replace(/whatsapp:/i, '').replace(/\s+/g, '');
  if (clean.startsWith('+91')) return `+91 ${clean.slice(3)}`;
  if (clean.startsWith('+')) return clean.replace('+', '+ ');
  if (clean.length === 10) return `+91 ${clean}`;
  return clean;
}

/** Strip display prefixes so a value can be edited in a textbox. */
export function stripPhone(val) {
  if (!val) return '';
  return String(val).replace(/whatsapp:/i, '').replace(/^\+91\s*/, '').trim();
}

/** Relative-ish clock for event feeds. */
export function timeAgo(iso) {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const diff = Math.max(0, Date.now() - then);
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function clockTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
}

export function shortDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}
