import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";

// Auth pages
import LoginPage        from "./pages/auth/LoginPage";
import RegisterPage     from "./pages/auth/RegisterPage";
import UnauthorizedPage from "./pages/UnauthorizedPage";

// Protected route wrapper
import ProtectedRoute from "./components/common/ProtectedRoute";

// Member 3's existing app (preserved exactly as-is)
import Member3App from "./Member3App";

import "./App.css";

export default function App() {
    return (
        <BrowserRouter>
            <AuthProvider>
                <Routes>
                    {/* ── Public routes ──────────────────────────────── */}
                    <Route path="/login"         element={<LoginPage />} />
                    <Route path="/register"      element={<RegisterPage />} />
                    <Route path="/unauthorized"  element={<UnauthorizedPage />} />

                    {/* ── Admin routes ───────────────────────────────── */}
                    <Route
                        path="/admin/*"
                        element={
                            <ProtectedRoute roles={["ADMIN"]}>
                                {/* TODO: replace with AdminLayout once built */}
                                <Member3App />
                            </ProtectedRoute>
                        }
                    />

                    {/* ── Staff + Admin routes ────────────────────────── */}
                    <Route
                        path="/dashboard/*"
                        element={
                            <ProtectedRoute roles={["ADMIN", "STAFF"]}>
                                <Member3App />
                            </ProtectedRoute>
                        }
                    />

                    {/* ── Customer portal ─────────────────────────────── */}
                    <Route
                        path="/portal/*"
                        element={
                            <ProtectedRoute roles={["CUSTOMER"]}>
                                {/* TODO: replace with CustomerPortal once built */}
                                <Member3App />
                            </ProtectedRoute>
                        }
                    />

                    {/* ── Root redirect ───────────────────────────────── */}
                    {/* Sends unauthenticated users to login;
                        ProtectedRoute handles the redirect after login */}
                    <Route path="/" element={<Navigate to="/login" replace />} />

                    {/* ── 404 fallback ─────────────────────────────────── */}
                    <Route path="*" element={<Navigate to="/login" replace />} />
                </Routes>
            </AuthProvider>
        </BrowserRouter>
    );
}
