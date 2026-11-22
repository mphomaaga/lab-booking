import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../theme/theme";

export function Layout() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="layout">
      <header className="layout-header">
        <div className="layout-top">
          <span className="app-name">Lab booking</span>
          <span className="layout-user">
            <span className="student-number">{user?.student_number}</span>
            <button
              type="button"
              className="btn theme-toggle"
              aria-pressed={theme === "dark"}
              onClick={toggleTheme}
            >
              Dark mode
            </button>
            <button type="button" className="btn" onClick={logout}>
              Log out
            </button>
          </span>
        </div>
        <nav className="layout-nav" aria-label="Main">
          <NavLink to="/book" className="nav-link">
            Book a slot
          </NavLink>
          <NavLink to="/my-bookings" className="nav-link">
            My bookings
          </NavLink>
          {user?.is_admin && (
            <NavLink to="/admin" className="nav-link">
              Admin
            </NavLink>
          )}
        </nav>
      </header>
      <main className="layout-main">
        <Outlet />
      </main>
    </div>
  );
}
