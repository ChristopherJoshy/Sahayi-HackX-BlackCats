import { NavLink } from "react-router-dom";
import { useState } from "react";
import { LayoutDashboard, Users, UserPlus, Bug, Settings, HeartPulse } from "lucide-react";

const links = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/patients", label: "My Patients", icon: Users },
  { to: "/setup", label: "Add Patient", icon: UserPlus },
  { to: "/debug", label: "Care Tools", icon: Bug },
];

/**
 * Dynamic rail: collapsed to icons by default, expands when the cursor is near
 * the left edge or hovers the rail itself. Closes on mouse-leave.
 */
export default function Sidebar() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Edge trigger — opens the rail when the cursor approaches the left side. */}
      <div
        className="fixed left-0 top-16 z-30 hidden h-[calc(100vh-4rem)] w-3 lg:block"
        onMouseEnter={() => setOpen(true)}
      />
      <aside
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className={`fixed left-0 top-16 z-40 hidden h-[calc(100vh-4rem)] flex-col justify-between border-r border-white/10 bg-ink transition-[width] duration-200 ease-out lg:flex ${
          open ? "w-60" : "w-[4.5rem]"
        }`}
      >
        <div className="overflow-hidden">
          <p className={`px-5 pb-3 pt-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500 transition-opacity ${open ? "opacity-100" : "opacity-0"}`}>
            Sahayi
          </p>
          <nav className="space-y-1 px-3">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.to === "/"}
                title={link.label}
                className={({ isActive }) => `rail-link ${isActive ? "rail-link-active" : "rail-link-inactive"} ${open ? "" : "justify-center"}`}
              >
                <link.icon size={18} strokeWidth={2.2} />
                <span className={`whitespace-nowrap transition-opacity duration-150 ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}>
                  {link.label}
                </span>
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="space-y-1 border-t border-white/10 px-3 pt-4">
          <NavLink
            to="/settings"
            title="Settings"
            className={({ isActive }) => `rail-link ${isActive ? "rail-link-active" : "rail-link-inactive"} ${open ? "" : "justify-center"}`}
          >
            <Settings size={18} strokeWidth={2.2} />
            <span className={`whitespace-nowrap transition-opacity duration-150 ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}>Settings</span>
          </NavLink>
          <div className={`mt-3 flex items-center gap-2 rounded-xl bg-white/5 px-3 py-2.5 text-slate-400 transition-opacity ${open ? "opacity-100" : "opacity-0"}`}>
            <HeartPulse size={16} className="shrink-0 text-brand-400" />
            <span className="whitespace-nowrap text-[10px] font-semibold uppercase tracking-wide">Sahayi v1</span>
          </div>
        </div>
      </aside>
    </>
  );
}
