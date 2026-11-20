import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAdmin, RequireAuth } from "./auth/RouteGuards";
import { Layout } from "./components/Layout";
import { AdminPage } from "./pages/AdminPage";
import { BookPage } from "./pages/BookPage";
import { LoginPage } from "./pages/LoginPage";
import { MyBookingsPage } from "./pages/MyBookingsPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route path="/book" element={<BookPage />} />
          <Route path="/my-bookings" element={<MyBookingsPage />} />
          <Route element={<RequireAdmin />}>
            <Route path="/admin" element={<AdminPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/book" replace />} />
    </Routes>
  );
}
