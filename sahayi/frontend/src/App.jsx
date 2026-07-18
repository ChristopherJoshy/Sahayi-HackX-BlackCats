import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { setAuthToken } from "./api/sahayi";
import { clearToken, getDoctorUser, getStoredToken, isAuthenticated, setStoredToken } from "./auth/tokenAuth";
import Navbar from "./components/Layout/Navbar";
import Sidebar from "./components/Layout/Sidebar";
import MobileNav from "./components/Layout/MobileNav";
import AlertCenter from "./components/Alerts/AlertCenter";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import PatientProfile from "./pages/PatientProfile";
import Patients from "./pages/Patients";
import Setup from "./pages/Setup";
import Settings from "./pages/Settings";
import Debug from "./pages/Debug";
import { useWebSocket } from "./hooks/useWebSocket";
import { sahayiApi } from "./api/sahayi";
import { buildAlerts } from "./components/Alerts/AlertCenter";

export default function App() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const { events, live, connectionState } = useWebSocket(user);
  const [patients, setPatients] = useState([]);

  useEffect(() => {
    if (isAuthenticated()) {
      setAuthToken(getStoredToken());
      setUser(getDoctorUser());
    }
    setReady(true);
  }, []);

  const handleLogout = () => {
    clearToken();
    setAuthToken("");
    setUser(null);
  };

  const handleLogin = (token) => {
    setStoredToken(token);
    setAuthToken(token);
    setUser(getDoctorUser());
  };

  // Keep a small patient roster snapshot for the alert center (cheap, dashboard-scoped).
  const lastEventAt = events[0]?.occurred_at;
  const emergencyCount = (live.emergencies || []).length;
  useEffect(() => {
    if (!user) return;
    let active = true;
    sahayiApi.listDashboardPatients()
      .then((rows) => active && setPatients(rows))
      .catch(() => {});
    return () => { active = false; };
  }, [user, lastEventAt, emergencyCount]);

  const alerts = buildAlerts(live, patients);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas">
        <div className="text-center">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
          <p className="mt-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-faint">Connecting to SAHAYI…</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="app-shell">
      <Navbar user={user} alerts={alerts} />
      <Sidebar />
      <div className="content-area lg:ml-[4.5rem]">
        <main className="min-w-0 px-4 py-5 lg:px-8">
          <Routes>
            <Route path="/" element={<Dashboard user={user} live={live} patients={patients} connectionState={connectionState} />} />
            <Route path="/patients" element={<Patients />} />
            <Route path="/setup" element={<Setup />} />
            <Route path="/settings" element={<Settings onLogout={handleLogout} />} />
            <Route path="/patient/:id" element={<PatientProfile user={user} />} />
            <Route path="/debug" element={<Debug user={user} />} />
          </Routes>
        </main>
      </div>
      <MobileNav />
    </div>
  );
}
