import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

/**
 * Wraps any route that requires authentication (and optionally a specific role).
 *
 * Usage:
 *   <ProtectedRoute>                          — any logged-in user
 *   <ProtectedRoute roles={["ADMIN"]}         — admin only
 *   <ProtectedRoute roles={["ADMIN","STAFF"]} — admin or staff
 */
export default function ProtectedRoute({ children, roles }) {
    const { user, loading } = useAuth();
    const location = useLocation();

    // Still hydrating session from cookie — show nothing (avoids flash)
    if (loading) {
        return (
            <div className="min-h-screen bg-[#EEEBDA] flex items-center justify-center">
                <span className="w-8 h-8 border-2 border-[#282B4A]/20 border-t-[#282B4A] rounded-full animate-spin" />
            </div>
        );
    }

    // Not logged in — redirect to login and remember where they came from
    if (!user) {
        return <Navigate to="/login" state={{ from: location }} replace />;
    }

    // Logged in but wrong role
    if (roles && !roles.includes(user.role)) {
        return <Navigate to="/unauthorized" replace />;
    }

    return children;
}
