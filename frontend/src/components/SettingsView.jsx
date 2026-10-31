import React from "react";
import { useAuth } from "../context/AuthContext";

export default function SettingsView() {
  const { user } = useAuth();
  const role = user?.role || "GUEST";

  return (
    <div className="view-container">
      <div className="view-header">
        <div>
          <h2>System & Organization Settings</h2>
          <p>Subscription preferences, currency configurations, and account security.</p>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "1.5rem" }}>
        {/* User Profile Card */}
        <div className="card">
          <div className="card-header">
            <div>
              <h3>Account Profile</h3>
              <p className="card-subtitle">Current authenticated session details</p>
            </div>
            <span className={`role-badge role-${role.toLowerCase()}`}>{role}</span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem", marginTop: "1rem" }}>
            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--secondary-text)", textTransform: "uppercase" }}>
                Email Address
              </label>
              <div style={{ fontWeight: "600", fontSize: "0.95rem" }}>{user?.email || "guest@brightloop.local"}</div>
            </div>

            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--secondary-text)", textTransform: "uppercase" }}>
                Role Tier
              </label>
              <div style={{ fontWeight: "600", fontSize: "0.95rem" }}>{role}</div>
            </div>

            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--secondary-text)", textTransform: "uppercase" }}>
                Authentication Type
              </label>
              <div style={{ color: "var(--secondary-text)", fontSize: "0.9rem" }}>
                Django Session Cookie (with CSRF protection)
              </div>
            </div>
          </div>
        </div>

        {/* Organization Config Card */}
        <div className="card">
          <div className="card-header">
            <div>
              <h3>Organization Defaults</h3>
              <p className="card-subtitle">Global billing and tax parameters</p>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem", marginTop: "1rem" }}>
            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--secondary-text)", textTransform: "uppercase" }}>
                Organization Name
              </label>
              <div style={{ fontWeight: "600", fontSize: "0.95rem" }}>Brightloop SaaS Ltd.</div>
            </div>

            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--secondary-text)", textTransform: "uppercase" }}>
                Base Currency
              </label>
              <div style={{ fontWeight: "600", fontSize: "0.95rem" }}>USD ($)</div>
            </div>

            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--secondary-text)", textTransform: "uppercase" }}>
                Default Tax Rate
              </label>
              <div style={{ fontWeight: "600", fontSize: "0.95rem" }}>Standard VAT (18.00%)</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
