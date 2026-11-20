import { Navigate, Outlet } from "react-router-dom";
import { LoadingMessage } from "../components/ui/LoadingMessage";
import { useAuth } from "./AuthContext";
import { getToken } from "./tokenStorage";

/** Every route except /login needs a token. */
export function RequireAuth() {
  const { user, loading } = useAuth();
  if (getToken() === null) return <Navigate to="/login" replace />;
  if (loading) return <LoadingMessage />;
  if (user === null) return <Navigate to="/login" replace />;
  return <Outlet />;
}

/** /admin also needs is_admin (rule 5.13); everyone else goes to /book. */
export function RequireAdmin() {
  const { user } = useAuth();
  if (!user?.is_admin) return <Navigate to="/book" replace />;
  return <Outlet />;
}
