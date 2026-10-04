import { Suspense, useState } from "react";
import { Outlet, Link, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Button } from "./ui/Button";
import { Logo } from "./Logo";
import { cn } from "../utils/cn";

/**
 * Shown while a lazily-loaded route chunk is being fetched. Styled to match
 * PLAYOOT so navigation never flashes a bare white/blank screen.
 */
function RouteFallback() {
  return (
    <div className="flex min-h-[55vh] flex-col items-center justify-center gap-5">
      <Logo size={46} showWordmark={false} />
      <div className="h-1.5 w-44 overflow-hidden rounded-full bg-white/10">
        <div className="h-full w-1/2 animate-shimmer rounded-full bg-gradient-to-r from-purple-500 via-fuchsia-500 to-cyan-400 bg-[length:200%_auto]" />
      </div>
      <p className="text-sm text-gray-400">Loading…</p>
    </div>
  );
}

export function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  const navLinks = [
    { path: "/dashboard", label: "Dashboard", icon: "📊" },
    { path: "/create", label: "Create Quiz", icon: "✨" },
  ];

  return (
    <div className="min-h-screen text-gray-100 flex flex-col">
      {/* Animated aurora backdrop */}
      <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute -top-48 -left-40 h-[42rem] w-[42rem] rounded-full bg-purple-600/25 blur-[130px] animate-float" />
        <div className="absolute top-1/3 -right-40 h-[34rem] w-[34rem] rounded-full bg-pink-500/20 blur-[130px] animate-float [animation-delay:-6s]" />
        <div className="absolute -bottom-48 left-1/4 h-[30rem] w-[30rem] rounded-full bg-cyan-500/20 blur-[130px] animate-float [animation-delay:-3s]" />
      </div>

      <header className="glass-nav sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16 gap-3">
            <Link to="/" className="text-lg min-w-0" onClick={() => setMenuOpen(false)}>
              <Logo size={34} />
            </Link>

            <nav className="hidden md:flex items-center gap-2">
              {user ? (
                <>
                  {navLinks.map((link) => {
                    const active = location.pathname === link.path;
                    return (
                      <Link
                        key={link.path}
                        to={link.path}
                        className={cn(
                          "flex items-center gap-1.5 text-sm font-medium px-3.5 py-2 rounded-full transition-all duration-200",
                          active
                            ? "bg-gradient-to-r from-purple-600/90 to-fuchsia-600/90 text-white shadow-playoot-sm"
                            : "text-gray-300 hover:text-white hover:bg-white/10"
                        )}
                      >
                        <span>{link.icon}</span>
                        {link.label}
                      </Link>
                    );
                  })}
                  <Button variant="ghost" size="sm" onClick={logout}>
                    Logout
                  </Button>
                </>
              ) : (
                <div className="flex items-center gap-3">
                  <Link to="/join">
                    <Button variant="ghost" size="sm">Join</Button>
                  </Link>
                  <Link to="/login">
                    <Button variant="secondary" size="sm">Sign In</Button>
                  </Link>
                  <Link to="/register">
                    <Button variant="brand" size="sm">Get Started</Button>
                  </Link>
                </div>
              )}
            </nav>

            {/* Mobile controls */}
            <div className="flex md:hidden items-center gap-2 flex-shrink-0">
              {user ? (
                <>
                  <Link to="/join" onClick={() => setMenuOpen(false)}>
                    <Button variant="ghost" size="sm">Join</Button>
                  </Link>
                  <button
                    type="button"
                    aria-label="Toggle navigation menu"
                    aria-expanded={menuOpen}
                    onClick={() => setMenuOpen((o) => !o)}
                    className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/5 border border-white/10 text-gray-200 hover:bg-white/10 transition-colors"
                  >
                    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
                      {menuOpen ? (
                        <path d="M6 6l12 12M18 6L6 18" />
                      ) : (
                        <path d="M4 7h16M4 12h16M4 17h16" />
                      )}
                    </svg>
                  </button>
                </>
              ) : (
                <Link to="/login"><Button variant="secondary" size="sm">Sign In</Button></Link>
              )}
            </div>
          </div>
        </div>

        {/* Mobile dropdown menu */}
        {user && (
          <div
            className={cn(
              "md:hidden overflow-hidden transition-[max-height] duration-300 ease-out",
              menuOpen ? "max-h-80 border-t border-white/10" : "max-h-0"
            )}
          >
            <nav className="px-4 py-3 space-y-1">
              {navLinks.map((link) => (
                <Link
                  key={link.path}
                  to={link.path}
                  onClick={() => setMenuOpen(false)}
                  className={cn(
                    "flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-colors",
                    location.pathname === link.path
                      ? "bg-gradient-to-r from-purple-600/90 to-fuchsia-600/90 text-white"
                      : "text-gray-200 hover:bg-white/10"
                  )}
                >
                  <span>{link.icon}</span>
                  {link.label}
                </Link>
              ))}
              <button
                type="button"
                onClick={() => { setMenuOpen(false); logout(); }}
                className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-gray-300 hover:bg-white/10 transition-colors"
              >
                <span>🚪</span>
                Logout
              </button>
            </nav>
          </div>
        )}
      </header>

      <main className="relative flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-10">
        <Suspense fallback={<RouteFallback />}>
          <Outlet />
        </Suspense>
      </main>

      <footer className="relative glass-nav border-t border-white/10 py-6">
        <div className="max-w-7xl mx-auto px-4 text-center text-sm text-gray-500">
          <span className="bg-gradient-to-r from-purple-300 to-cyan-300 bg-clip-text text-transparent font-medium">
            PLAYOOT IN EVERYWHERE
          </span>{" "}
          — Multiplayer Quiz Platform
        </div>
      </footer>
    </div>
  );
}
