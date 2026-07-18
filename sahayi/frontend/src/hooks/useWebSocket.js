import { useEffect, useMemo, useRef, useState } from "react";

import { getStoredToken } from "../auth/tokenAuth";
import { normalizeStatus, timeAgo } from "../lib/format";

/**
 * Manage the doctor dashboard WebSocket event stream and derive live state.
 * @param {object|null} user Authenticated doctor profile (token taken from storage).
 * @returns {object} Connection state, raw events, and derived live dashboard state.
 */
export function useWebSocket(user) {
  const [events, setEvents] = useState([]);
  const [connectionState, setConnectionState] = useState("idle");
  const socketRef = useRef(null);
  const retryRef = useRef(0);

  useEffect(() => {
    let closedByEffect = false;
    async function connect() {
      if (!user) {
        setConnectionState("idle");
        return;
      }
      const token = getStoredToken();
      if (closedByEffect) return;

      const socket = new WebSocket(`${import.meta.env.VITE_WS_URL}/ws/dashboard?token=${token}`);
      socketRef.current = socket;
      socket.onopen = () => {
        setConnectionState("connected");
        retryRef.current = 0;
      };
      /* Event shape: { event: string, payload: object, occurred_at: string } */
      socket.onmessage = (message) => {
        try {
          const parsed = JSON.parse(message.data);
          setEvents((current) => [parsed, ...current].slice(0, 80));
        } catch {
          // Ignore non-JSON frames so a keepalive or proxy message does not break the dashboard.
        }
      };
      socket.onclose = () => {
        setConnectionState("disconnected");
        if (!closedByEffect) {
          retryRef.current += 1;
          setTimeout(connect, Math.min(2000 * retryRef.current, 8000));
        }
      };
      socket.onerror = () => setConnectionState("error");
    }
    connect();
    return () => {
      closedByEffect = true;
      socketRef.current?.close();
    };
  }, [user]);

  const live = useMemo(() => {
    const byPatient = new Map();
    let activeCall = null;
    let summary = null;
    let hypothesis = null;
    const emergencies = [];
    const followUps = [];

    for (const e of events) {
      const p = e.payload || {};
      const pid = p.patient_id ?? p.id;
      switch (e.event) {
        case 'call_started':
          activeCall = p;
          break;
        case 'new_signal':
        case 'risk_update': {
          const prev = byPatient.get(pid) || {};
          byPatient.set(pid, { ...prev, ...p, status: normalizeStatus(p.status || p.latest_status), updated_at: e.occurred_at });
          break;
        }
        case 'doctor_summary': {
          summary = p;
          if (pid != null) {
            const prev = byPatient.get(pid) || {};
            byPatient.set(pid, { ...prev, patient_id: pid, summary_text: p.summary_text, risk_score: p.risk_score });
          }
          break;
        }
        case 'hypothesis_generated':
          hypothesis = p;
          break;
        case 'emergency_started':
        case 'emergency_relative_contacted':
        case 'emergency_doctor_contacted':
        case 'emergency_unreachable':
          emergencies.push({ ...e.payload, kind: e.event, at: timeAgo(e.occurred_at) });
          break;
        case 'follow_up_due':
          followUps.push(e.payload);
          break;
        default:
          break;
      }
    }

    return {
      activeCall,
      summary,
      hypothesis,
      emergencies,
      followUps,
      livePatients: [...byPatient.values()],
    };
  }, [events]);

  return { events, latestEvent: events[0] || null, connectionState, live };
}
