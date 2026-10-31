import { useEffect, useState } from "react";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { initializeCsrf, login, logout } from "./api/auth";
import SubscriptionsView from "./components/SubscriptionsView";
import QuotationsView from "./components/QuotationsView";
import Member4BillingSimulator from "./components/Member4BillingSimulator";
import "./App.css";

function DashboardLayout() {
  const { user, setUser } = useAuth();
  const [currentModule, setCurrentModule] = useState("subscriptions");
  const [backendStatus, setBackendStatus] = useState("Connecting...");
  const [globalSearch, setGlobalSearch] = useState("");

  useEffect(() => {
    initializeCsrf()
      .then((data) => {
        if (data.success) {
          setBackendStatus("Online");
        } else {
          setBackendStatus("CSRF Pending");
        }
      })
      .catch(() => setBackendStatus("Offline"));
  }, []);

  async function handleDemoLogin(email, password) {
    try {
      await initializeCsrf();
      const res = await login(email, password);
      setUser(res.data || { email });
    } catch (err) {
      alert("Login failed: " + (err?.message || "Invalid credentials"));
    }
  }

  async function handleLogout() {
    try {
      await logout();
      setUser(null);
    } catch (err) {
      console.error("Logout failed", err);
    }
  }

  const role = user?.role || "GUEST";
  const isCustomer = role === "CUSTOMER";

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
          <span className="user-avatar">{user ? user.email[0].toUpperCase() : "?"}</span>
          <div className="user-details">
            <strong>{user ? user.email.split("@")[0] : "Guest User"}</strong>
            <span className={`role-badge role-${role.toLowerCase()}`}>{role}</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section-label">CONTRACTS & SALES</div>

          <button
            className={`nav-item ${currentModule === "subscriptions" ? "active" : ""}`}
            onClick={() => setCurrentModule("subscriptions")}
          >
            <span className="nav-icon">📋</span>
            <span>Subscriptions</span>
          </button>

          {!isCustomer && (
            <button
              className={`nav-item ${currentModule === "quotations" ? "active" : ""}`}
              onClick={() => setCurrentModule("quotations")}
            >
              <span className="nav-icon">💼</span>
              <span>Quotations</span>
            </button>
          )}

          {!isCustomer && (
            <button
              className={`nav-item ${currentModule === "billing-hook" ? "active" : ""}`}
              onClick={() => setCurrentModule("billing-hook")}
            >
              <span className="nav-icon">⚡</span>
              <span>Billing Engine (M4)</span>
            </button>
          )}

          <div className="nav-section-label">TEAM MODULES</div>

          <button
            className={`nav-item ${currentModule === "catalog" ? "active" : ""}`}
            onClick={() => setCurrentModule("catalog")}
          >
            <span className="nav-icon">📦</span>
            <span>Products & Plans (M2)</span>
          </button>

          <button
            className={`nav-item ${currentModule === "invoices" ? "active" : ""}`}
            onClick={() => setCurrentModule("invoices")}
          >
            <span className="nav-icon">🧾</span>
            <span>Invoices (M4)</span>
          </button>

          <button
            className={`nav-item ${currentModule === "admin" ? "active" : ""}`}
            onClick={() => setCurrentModule("admin")}
          >
            <span className="nav-icon">🛡️</span>
            <span>Django Admin</span>
          </button>
        </nav>

        <div className="sidebar-footer">
          <div className="system-health">
            <span className="health-dot"></span>
            <span>Backend: {backendStatus}</span>
          </div>
          <small className="build-version">Brightloop v1.0 • Member 3</small>
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
            {/* Quick Demo Switcher */}
            <div className="demo-switcher">
              <span className="switcher-label">Demo Role:</span>
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
          {currentModule === "subscriptions" && <SubscriptionsView />}

          {currentModule === "quotations" && (
            <QuotationsView
              onConvertedToSubscription={() => setCurrentModule("subscriptions")}
            />
          )}

          {currentModule === "billing-hook" && <Member4BillingSimulator />}

          {currentModule === "catalog" && (
            <div className="placeholder-module-card">
              <h3>Member 2: Products & Plans Catalog</h3>
              <p>
                Products, pricing variants, and billing periods (`daily`, `weekly`, `monthly`, `yearly`) are fully integrated and available via REST API at <code>/api/catalog/</code>.
              </p>
              <div className="module-links">
                <button className="btn-primary" onClick={() => setCurrentModule("quotations")}>
                  View Quotations using Catalog Products ➔
                </button>
                <a
                  href="http://localhost:8001/admin/catalog/product/"
                  target="_blank"
                  rel="noreferrer"
                  className="btn-secondary"
                >
                  Manage Products in Admin ↗
                </a>
              </div>
            </div>
          )}

          {currentModule === "invoices" && (
            <div className="placeholder-module-card">
              <h3>Member 4: Invoice Generation & Payments</h3>
              <p>
                The subscription state machine actively provides due contract data via <code>get_due_subscriptions()</code> and advances billing cycles via <code>advance_next_billing_date()</code>.
              </p>
              <div className="module-links">
                <button className="btn-primary" onClick={() => setCurrentModule("billing-hook")}>
                  Open Member 4 Billing Simulator ➔
                </button>
                <a
                  href="http://localhost:8001/admin/billing/invoice/"
                  target="_blank"
                  rel="noreferrer"
                  className="btn-secondary"
                >
                  Manage Invoices in Admin ↗
                </a>
              </div>
            </div>
          )}

          {currentModule === "admin" && (
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
