import { Search, User } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { useSearch } from "../../context/SearchContext";
import AlertCenter from "../Alerts/AlertCenter";

export default function Navbar({ user, alerts = [] }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { searchQuery, setSearchQuery } = useSearch();

  const onSearch = (e) => {
    const value = e.target.value;
    setSearchQuery(value);
    if (value && location.pathname === "/") navigate("/patients");
  };

  const initials = (user.displayName || "Doctor")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() || "")
    .join("");

  return (
    <header className="fixed inset-x-0 top-0 z-40 h-16 border-b border-line bg-surface/90 backdrop-blur">
      <div className="flex h-full items-center justify-between px-5 lg:px-8">
        <div className="flex items-center gap-10">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 font-display text-sm font-bold text-white">S</span>
            <span className="font-display text-lg font-bold tracking-tight text-ink">
              {import.meta.env.VITE_APP_NAME || "SAHAYI"}
            </span>
          </div>
          <div className="relative hidden lg:block">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
            <input
              type="text"
              placeholder="Search patients…"
              value={searchQuery}
              onChange={onSearch}
              className="h-10 w-[min(34vw,28rem)] rounded-xl border border-line bg-canvas pl-10 pr-4 text-sm text-ink outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <AlertCenter alerts={alerts} />
          <div className="text-right">
            <p className="text-sm font-semibold leading-none text-ink">{user.displayName || "Doctor"}</p>
            <p className="mt-1 max-w-[140px] truncate text-xs text-ink-muted">{user.email}</p>
          </div>
          <div className="flex h-10 w-10 items-center justify-center overflow-hidden rounded-xl bg-brand-50 text-sm font-bold text-brand-700">
            {user.photoURL ? <img src={user.photoURL} alt="" className="h-full w-full object-cover" /> : initials || <User size={18} />}
          </div>
        </div>
      </div>
    </header>
  );
}
