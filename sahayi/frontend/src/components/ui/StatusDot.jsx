import { statusMeta, normalizeStatus } from "../../lib/format";

/**
 * Small status indicator dot used in lists and headers.
 * @param {{ status: string, pulse?: boolean }} props
 */
export default function StatusDot({ status, pulse = false }) {
  const meta = statusMeta(normalizeStatus(status));
  return (
    <span className={`relative inline-flex h-2.5 w-2.5`}>
      {pulse && (
        <span className={`absolute inline-flex h-full w-full rounded-full ${meta.dot} opacity-60 animate-ping`} />
      )}
      <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${meta.dot}`} />
    </span>
  );
}
