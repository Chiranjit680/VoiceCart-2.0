import { Navigate, Outlet, Link, useLocation } from "react-router-dom";
import { ShoppingCart, ClipboardList, Mic, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";

const navItems = [
  { to: "/", label: "Voice", icon: Mic },
  { to: "/orders", label: "Orders", icon: ClipboardList },
];

/** Top bar plus the page. Everything here needs a login, so visitors without one go to the sign-in page. */
export function AppLayout() {
  const { pathname } = useLocation();
  const { isAuthenticated, logout, user } = useAuth();

  if (!isAuthenticated) return <Navigate to="/auth" replace />;

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-card px-3 sm:gap-6 sm:px-4">
        <Link to="/" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
            <ShoppingCart className="h-4 w-4 text-primary-foreground" />
          </div>
          <span className="hidden text-lg font-bold tracking-tight text-foreground sm:inline">VoiceCart</span>
        </Link>

        <nav className="flex flex-1 items-center gap-1">
          {navItems.map(({ to, label, icon: Icon }) => {
            const active = to === "/" ? pathname === "/" : pathname.startsWith(to);
            return (
              <Link
                key={to}
                to={to}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                  active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>

        {user?.email ? <span className="hidden text-sm text-muted-foreground sm:inline">{user.email}</span> : null}
        <button
          onClick={logout}
          aria-label="Logout"
          className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <LogOut className="h-4 w-4" />
          <span className="hidden sm:inline">Logout</span>
        </button>
      </header>

      <main>
        <Outlet />
      </main>
    </div>
  );
}
