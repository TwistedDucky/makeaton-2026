import { useEffect, useState } from "react";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { initializeCsrf, login, logout, getCurrentUser } from "./api/auth";
import DashboardView from "./components/DashboardView";
import CustomersView from "./components/CustomersView";
import CatalogView from "./components/CatalogView";
import QuotationsView from "./components/QuotationsView";
import SubscriptionsView from "./components/SubscriptionsView";
import InvoicesView from "./components/InvoicesView";
import PaymentsView from "./components/PaymentsView";
import DiscountsView from "./components/DiscountsView";
import ReportsView from "./components/ReportsView";
import SettingsView from "./components/SettingsView";
import Member4BillingSimulator from "./components/Member4BillingSimulator";
import ProtectedRoute from "./components/common/ProtectedRoute";
import "./App.css";

function DashboardLayout() {
  const { user, setUser } = useAuth();
  const [currentModule, setCurrentModule] = useState("dashboard");
  const [backendStatus, setBackendStatus] = useState("Connecting...");
  const [globalSearch, setGlobalSearch] = useState("");
  const [showNotifications, setShowNotifications] = useState(false);

  async function handleDemoLogin(email, password) {
    try {
      await initializeCsrf();
      const res = await login(email, password);
      const loggedUser = res?.data || res || { email, role: "STAFF" };
      setUser(loggedUser);
    } catch (err) {
      console.error("Login failed", err);
    }
  }

  useEffect(() => {
    initializeCsrf()
      .then((data) => {
        if (data.success) {
          setBackendStatus("Online");
          // If no user session is active, auto-login as sales rep for demo convenience
          getCurrentUser()
            .then((res) => {
              const u = res?.data || res;
              if (u && u.email) {
                setUser(u);
              } else {
                handleDemoLogin("sales@example.com", "Staff123!");
              }
            })
            .catch(() => {
              handleDemoLogin("sales@example.com", "Staff123!");
            });
        } else {
          setBackendStatus("CSRF Pending");
        }
      })
      .catch(() => setBackendStatus("Offline"));
  }, []);

  async function handleLogout() {
    try {
      await logout();
      setUser(null);
    } catch (err) {
      console.error("Logout failed", err);
    }
  }

  const userObj = user?.data || user;
  const role = userObj?.role || "STAFF";
  const isCustomer = role === "CUSTOMER";
  const isAdmin = role === "ADMIN";

  const notifications = [
    { id: 1, title: "Quotation Accepted", desc: "Acme Corp approved Q-1001 ($208.86)", time: "10m ago" },
    { id: 2, title: "Contract Billing Due", desc: "SUB-2026-0001 ready for invoice cycle", time: "1h ago" },
    { id: 3, title: "Payment Recorded", desc: "Stark Industries paid INV-2026-0002 ($1,475.00)", time: "3h ago" },
  ];

  return (
    <div className="brightloop-app">
      {/* 1. Midnight Indigo Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-logo-mark">B</div>
          <div className="brand-text">
            <h2>Brightloop</h2>
            <span>Subscription OS</span>
          </div>
        </div>

        <div className="sidebar-user-pill">
          <span className="user-avatar">
            {userObj?.email ? userObj.email[0].toUpperCase() : "S"}
          </span>
          <div className="user-details">
            <strong>
              {userObj?.email ? userObj.email.split("@")[0] : "Sales Staff"}
            </strong>
            <span className={`role-badge role-${(role || "staff").toLowerCase()}`}>
              {role}
            </span>
          </div>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section-label">OVERVIEW</div>

          <button
            className={`nav-item ${currentModule === "dashboard" ? "active" : ""}`}
            onClick={() => setCurrentModule("dashboard")}
          >
            <span className="nav-icon">📊</span>
            <span>Dashboard</span>
          </button>

          {!isCustomer && (
            <button
              className={`nav-item ${currentModule === "customers" ? "active" : ""}`}
              onClick={() => setCurrentModule("customers")}
            >
              <span className="nav-icon">👥</span>
              <span>Customers</span>
            </button>
          )}

          <div className="nav-section-label">{isCustomer ? "MY PORTAL" : "SALES & CONTRACTS"}</div>

          {!isCustomer && (
            <button
              className={`nav-item ${currentModule === "quotations" ? "active" : ""}`}
              onClick={() => setCurrentModule("quotations")}
            >
              <span className="nav-icon">💼</span>
              <span>Quotations</span>
            </button>
          )}

          <button
            className={`nav-item ${currentModule === "subscriptions" ? "active" : ""}`}
            onClick={() => setCurrentModule("subscriptions")}
          >
            <span className="nav-icon">📋</span>
            <span>{isCustomer ? "My Subscriptions" : "Subscriptions"}</span>
          </button>

          {!isCustomer && (
            <>
              <div className="nav-section-label">CATALOG & PRICING</div>

              <button
                className={`nav-item ${currentModule === "catalog" ? "active" : ""}`}
                onClick={() => setCurrentModule("catalog")}
              >
                <span className="nav-icon">📦</span>
                <span>Products & Plans</span>
              </button>

              <button
                className={`nav-item ${currentModule === "discounts" ? "active" : ""}`}
                onClick={() => setCurrentModule("discounts")}
              >
                <span className="nav-icon">🏷️</span>
                <span>Discounts</span>
              </button>
            </>
          )}

          <div className="nav-section-label">FINANCE & BILLING</div>

          <button
            className={`nav-item ${currentModule === "invoices" ? "active" : ""}`}
            onClick={() => setCurrentModule("invoices")}
          >
            <span className="nav-icon">🧾</span>
            <span>{isCustomer ? "My Invoices" : "Invoices"}</span>
          </button>

          <button
            className={`nav-item ${currentModule === "payments" ? "active" : ""}`}
            onClick={() => setCurrentModule("payments")}
          >
            <span className="nav-icon">💳</span>
            <span>{isCustomer ? "My Payments" : "Payments"}</span>
          </button>

          {!isCustomer && (
            <button
              className={`nav-item ${currentModule === "billing-hook" ? "active" : ""}`}
              onClick={() => setCurrentModule("billing-hook")}
            >
              <span className="nav-icon">⚡</span>
              <span>Billing Simulator (M4)</span>
            </button>
          )}

          {!isCustomer && (
            <>
              <div className="nav-section-label">MANAGEMENT</div>

              <button
                className={`nav-item ${currentModule === "reports" ? "active" : ""}`}
                onClick={() => setCurrentModule("reports")}
              >
                <span className="nav-icon">📈</span>
                <span>Reports</span>
              </button>
            </>
          )}

          <button
            className={`nav-item ${currentModule === "settings" ? "active" : ""}`}
            onClick={() => setCurrentModule("settings")}
          >
            <span className="nav-icon">⚙️</span>
            <span>Settings</span>
          </button>

          {isAdmin && (
            <button
              className={`nav-item ${currentModule === "admin" ? "active" : ""}`}
              onClick={() => setCurrentModule("admin")}
            >
              <span className="nav-icon">🛡️</span>
              <span>Django Admin</span>
            </button>
          )}
        </nav>

        <div className="sidebar-footer">
          <div className="system-health">
            <span className="health-dot"></span>
            <span>Backend: {backendStatus}</span>
          </div>
          <small className="build-version">Brightloop v1.0 • Midnight & Vanilla</small>
        </div>
      </aside>

      {/* 2. Main Content Area */}
      <div className="main-wrapper">
        {/* Top Navigation Bar */}
        <header className="topbar">
          <div className="topbar-search">
            <span className="search-icon">🔍</span>
            <input
              type="text"
              placeholder="Search contracts, quotations, customer email..."
              value={globalSearch}
              onChange={(e) => setGlobalSearch(e.target.value)}
            />
          </div>

          <div className="topbar-right">
            {/* Notification Bell */}
            <div style={{ position: "relative" }}>
              <button
                className="btn-secondary"
                style={{ padding: "0.45rem 0.75rem", borderRadius: "8px", position: "relative" }}
                onClick={() => setShowNotifications(!showNotifications)}
                title="Notifications"
              >
                🔔
                <span
                  style={{
                    position: "absolute",
                    top: "-4px",
                    right: "-4px",
                    backgroundColor: "#DC2626",
                    color: "#FFFFFF",
                    fontSize: "0.65rem",
                    fontWeight: "700",
                    borderRadius: "50%",
                    width: "16px",
                    height: "16px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  3
                </span>
              </button>

              {showNotifications && (
                <div
                  style={{
                    position: "absolute",
                    right: 0,
                    top: "42px",
                    width: "280px",
                    backgroundColor: "#FFFFFF",
                    border: "1px solid var(--border)",
                    borderRadius: "8px",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
                    padding: "0.75rem",
                    zIndex: 100,
                  }}
                >
                  <strong style={{ fontSize: "0.85rem", color: "var(--midnight-indigo)" }}>
                    System Notifications
                  </strong>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
                    {notifications.map((n) => (
                      <div
                        key={n.id}
                        style={{
                          padding: "0.4rem 0.5rem",
                          backgroundColor: "var(--soft-vanilla)",
                          borderRadius: "4px",
                          fontSize: "0.75rem",
                        }}
                      >
                        <div style={{ fontWeight: "600", color: "var(--midnight-indigo)" }}>{n.title}</div>
                        <div style={{ color: "var(--secondary-text)" }}>{n.desc}</div>
                        <div style={{ fontSize: "0.65rem", color: "#9CA3AF", marginTop: "0.2rem" }}>{n.time}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Quick Demo Switcher */}
            <div className="demo-switcher">
              <span className="switcher-label">Role:</span>
              <button
                className={`switch-btn ${role === "STAFF" ? "selected" : ""}`}
                onClick={() => handleDemoLogin("sales@example.com", "Staff123!")}
              >
                Staff (Sales)
              </button>
              <button
                className={`switch-btn ${role === "CUSTOMER" ? "selected" : ""}`}
                onClick={() => handleDemoLogin("acme@corp.com", "Customer123!")}
              >
                Customer (Acme)
              </button>
              <button
                className={`switch-btn ${role === "ADMIN" ? "selected" : ""}`}
                onClick={() => handleDemoLogin("admin@example.com", "Admin123!")}
              >
                Admin
              </button>
              {user && (
                <button className="switch-btn logout-btn" onClick={handleLogout}>
                  Logout
                </button>
              )}
            </div>
          </div>
        </header>

        {/* Dynamic View Content */}
        <main className="content-area">
          {currentModule === "dashboard" && (
            <ProtectedRoute>
              <DashboardView onNavigate={setCurrentModule} />
            </ProtectedRoute>
          )}

          {currentModule === "customers" && (
            <ProtectedRoute allowedRoles={["STAFF", "ADMIN"]}>
              <CustomersView onNavigate={setCurrentModule} />
            </ProtectedRoute>
          )}

          {currentModule === "quotations" && (
            <ProtectedRoute>
              <QuotationsView onConvertedToSubscription={() => setCurrentModule("subscriptions")} />
            </ProtectedRoute>
          )}

          {currentModule === "subscriptions" && (
            <ProtectedRoute>
              <SubscriptionsView />
            </ProtectedRoute>
          )}

          {currentModule === "catalog" && (
            <ProtectedRoute allowedRoles={["STAFF", "ADMIN"]}>
              <CatalogView />
            </ProtectedRoute>
          )}

          {currentModule === "invoices" && (
            <ProtectedRoute>
              <InvoicesView onNavigate={setCurrentModule} />
            </ProtectedRoute>
          )}

          {currentModule === "payments" && (
            <ProtectedRoute>
              <PaymentsView />
            </ProtectedRoute>
          )}

          {currentModule === "discounts" && (
            <ProtectedRoute allowedRoles={["STAFF", "ADMIN"]}>
              <DiscountsView />
            </ProtectedRoute>
          )}

          {currentModule === "billing-hook" && (
            <ProtectedRoute allowedRoles={["STAFF", "ADMIN"]}>
              <Member4BillingSimulator />
            </ProtectedRoute>
          )}

          {currentModule === "reports" && (
            <ProtectedRoute allowedRoles={["STAFF", "ADMIN"]}>
              <ReportsView />
            </ProtectedRoute>
          )}

          {currentModule === "settings" && (
            <ProtectedRoute>
              <SettingsView />
            </ProtectedRoute>
          )}

          {currentModule === "admin" && (
            <ProtectedRoute allowedRoles={["ADMIN"]}>
              <div className="placeholder-module-card">
                <h3>System Administration Portal</h3>
                <p>
                  Django Admin provides direct database inspection for Accounts, Products, Quotations, Subscriptions, and Invoices.
                </p>
                <a
                  href="http://localhost:8001/admin/"
                  target="_blank"
                  rel="noreferrer"
                  className="btn-primary"
                  style={{ display: "inline-block", textDecoration: "none" }}
                >
                  Launch Django Admin Portal ↗
                </a>
              </div>
            </ProtectedRoute>
          )}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <DashboardLayout />
    </AuthProvider>
  );
}
