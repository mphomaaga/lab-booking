import { useRef, useState, type FormEvent } from "react";
import { ApiError, errorMessage } from "../../api/errors";
import { useAuth } from "../../auth/AuthContext";
import { ErrorMessage } from "../ui/ErrorMessage";
import "./login.css";

const GENERIC_ERROR = "Could not log in. Please try again.";

/** Text to show for a failed login, chosen from the contract's error code. */
function loginErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    // 401 invalid_credentials: the contract's own message (same for unknown number and wrong password).
    if (error.code === "invalid_credentials") return error.message;
    // status 0 is the client's "can't reach the server" error; its text is already plain English.
    if (error.status === 0) return errorMessage(error);
  }
  return GENERIC_ERROR;
}

/**
 * Student number + password form (US-1). Logs in through the auth context; the page
 * redirects to /book once the context has a user.
 */
export function LoginForm() {
  const { login } = useAuth();
  const [studentNumber, setStudentNumber] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const passwordRef = useRef<HTMLInputElement>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      // The student number is sent exactly as typed: no format check, no trimming (US-1).
      await login(studentNumber, password);
      // Success: the auth context now has the user and LoginPage redirects to /book.
    } catch (caught) {
      setError(loginErrorMessage(caught));
      setBusy(false);
      // Keep the student number, clear the password and put the cursor back in it.
      if (caught instanceof ApiError && caught.code === "invalid_credentials") {
        setPassword("");
        passwordRef.current?.focus();
      }
    }
  }

  return (
    <form className="login-form" onSubmit={handleSubmit} aria-busy={busy}>
      <ErrorMessage message={error} />

      <div className="login-field">
        <label htmlFor="login-student-number">Student number</label>
        <input
          id="login-student-number"
          name="student_number"
          type="text"
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          required
          readOnly={busy}
          value={studentNumber}
          onChange={(event) => setStudentNumber(event.target.value)}
        />
      </div>

      <div className="login-field">
        <label htmlFor="login-password">Password</label>
        <input
          id="login-password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          readOnly={busy}
          ref={passwordRef}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </div>

      <button type="submit" className="btn btn-primary" disabled={busy}>
        {busy ? "Logging in..." : "Log in"}
      </button>
    </form>
  );
}
