import { NavLink } from "react-router-dom";
import { LayoutDashboard, Users, UserPlus, Settings, Bug } from "lucide-react";

const links = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/patients", label: "Patients", icon: Users },
  { to: "/setup", label: "Add", icon: UserPlus },
  { to: "/debug", label: "System", icon: Bug },
  { to: "/settings", label: "Settings", icon: Settings },
];

export default function MobileNav() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-50 flex items-center justify-around border-t border-line bg-surface px-4 py-2.5 shadow-[0_-2px_12px_rgba(15,23,42,0.06)] lg:hidden">
      {links.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          end={link.to === "/"}
          className={({ isActive }) => `flex flex-col items-center gap-0.5 text-[10px] font-semibold uppercase tracking-wide transition-colors ${isActive ? "text-brand-600" : "text-ink-faint"}`}
        >
          {({ isActive }) => (
            <>
              <link.icon size={20} strokeWidth={isActive ? 2.6 : 2} />
              {link.label}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
