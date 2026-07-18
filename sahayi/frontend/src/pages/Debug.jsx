import { Bug } from "lucide-react";
import { useWebSocket } from "../hooks/useWebSocket";
import { usePatientData } from "../hooks/usePatientData";
import AgentDebugPanel from "../components/Dashboard/AgentDebug/AgentDebugPanel";

export default function Debug({ user }) {
  const { events, connectionState, live } = useWebSocket(user);
  const { patients = [] } = usePatientData(events[0]);

  return (
    <div className="w-full space-y-6 pb-12 animate-slideIn">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
            <span className={`h-2 w-2 rounded-full ${connectionState === "connected" ? "bg-risk-green" : "bg-risk-amber"}`} />
            Live · {connectionState}
          </p>
          <h1 className="mt-2 flex items-center gap-2 font-display text-2xl font-bold tracking-tight text-ink">
            <Bug className="text-brand-600" size={24} /> System Telemetry
          </h1>
          <p className="mt-1 text-sm text-ink-muted">Real-time multi-agent activity for this doctor.</p>
        </div>
      </div>

      <div className="panel p-5">
        <AgentDebugPanel events={events} patients={patients} live={live} />
      </div>
    </div>
  );
}
