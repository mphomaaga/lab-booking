import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { LoginForm } from "../components/login/LoginForm";
import { LoadingMessage } from "../components/ui/LoadingMessage";

export function LoginPage() {
  const { user, loading } = useAuth();

  // Already logged in, or just logged in: go to /book.
  if (user !== null) return <Navigate to="/book" replace />;
  // A stored token is still being checked: wait, so a valid one goes to /book.
  if (loading) return <LoadingMessage />;

  return (
    <main className="login-page">
      <div className="login-card">
        <p className="login-app-name">Lab booking</p>
        <h1>Log in</h1>
        <LoginForm />
      </div>
    </main>
  );
}
