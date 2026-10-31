import React from "react";
import { useAuth } from "../../context/AuthContext";
import Spinner from "./Spinner";

/**
 * ProtectedRoute component:
 * Guards children based on authentication and optional role restrictions.
 *
 * @param {React.ReactNode} children - The component(s) to render if permitted.
 * @param {string[]} [allowedRoles] - Optional list of permitted roles (e.g. ['ADMIN', 'STAFF']).
 */
export default function ProtectedRoute({ children, allowedRoles }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "40vh" }}>
        <Spinner />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="card" style={{ maxWidth: "460px", margin: "3rem auto", textAlign: "center", padding: "2.5rem" }}>
        <div className="brand-logo-mark" style={{ margin: "0 auto 1rem" }}>B</div>
        <h3>Sign In to Brightloop</h3>
        <p style={{ color: "var(--secondary-text)", fontSize: "0.9rem", marginBottom: "1.5rem" }}>
          This page requires an authenticated session. Use the <strong>Role Switcher</strong> in the top navigation bar to authenticate as Staff, Customer, or Admin.
        </p>
      </div>
    );
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return (
      <div className="card" style={{ maxWidth: "480px", margin: "3rem auto", textAlign: "center", padding: "2.5rem" }}>
        <h3>Access Restricted</h3>
        <p style={{ color: "var(--secondary-text)", fontSize: "0.9rem" }}>
          Your current account role (<strong>{user.role}</strong>) is not permitted to view this module.
        </p>
        <span className="role-badge role-customer" style={{ marginTop: "1rem" }}>
          Current Role: {user.role}
        </span>
      </div>
    );
  }

  return children;
}
