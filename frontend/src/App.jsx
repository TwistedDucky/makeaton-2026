import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { initializeCsrf, login, logout, getCurrentUser } from "./api/auth";
import DashboardView from "./components/DashboardView";
import CustomersView from "./components/CustomersView";
import QuotationsView from "./components/QuotationsView";
import SubscriptionsView from "./components/SubscriptionsView";
import InvoicesView from "./components/InvoicesView";
import PaymentsView from "./components/PaymentsView";
import ReportsView from "./components/ReportsView";
import SettingsView from "./components/SettingsView";
import Member4BillingSimulator from "./components/Member4BillingSimulator";
import ProtectedRoute from "./components/common/ProtectedRoute";

import "./features/catalog/catalog.css";
import ProductsAdmin from "./features/catalog/ProductsAdmin";
import PlansAdmin from "./features/catalog/PlansAdmin";
import DiscountsAdmin from "./features/catalog/DiscountsAdmin";

// Auth pages from Member 1
import LoginPage from "./pages/auth/LoginPage";
import RegisterPage from "./pages/auth/RegisterPage";
import UnauthorizedPage from "./pages/UnauthorizedPage";

import {
  LayoutDashboard,
  Users,
  Briefcase,
  FileText,
  Package,
  Tag,
  Receipt,
  CreditCard,
  Zap,
  TrendingUp,
  Settings,
  Shield,
  Search,
  LogOut,
} from "lucide-react";

import "./App.css";

export function DashboardLayout() {
  const { user, setUser } = useAuth();
  const [currentModule, setCurrentModule] = useState("dashboard");
  const [backendStatus, setBackendStatus] = useState("Connecting...");
  const [globalSearch, setGlobalSearch] = useState("");

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
          // Auto-login as sales rep for demo convenience if no session
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
          <button
            className={`nav-item ${currentModule === "dashboard" ? "active" : ""}`}
            onClick={() => setCurrentModule("dashboard")}
          >
            <span className="nav-icon"><LayoutDashboard size={18} /></span>
            <span>Dashboard</span>
          </button>

          {!isCustomer && (
            <button
              className={`nav-item ${currentModule === "customers" ? "active" : ""}`}
              onClick={() => setCurrentModule("customers")}
            >
              <span className="nav-icon"><Users size={18} /></span>
              <span>Customers</span>
            </button>
          )}

          {!isCustomer && (
            <button
              className={`nav-item ${currentModule === "quotations" ? "active" : ""}`}
              onClick={() => setCurrentModule("quotations")}
            >
              <span className="nav-icon"><Briefcase size={18} /></span>
              <span>Quotations</span>
            </button>
          )}

          <button
            className={`nav-item ${currentModule === "subscriptions" ? "active" : ""}`}
            onClick={() => setCurrentModule("subscriptions")}
          >
            <span className="nav-icon"><FileText size={18} /></span>
            <span>{isCustomer ? "My Subscriptions" : "Subscriptions"}</span>
          </button>

          {!isCustomer && (
            <>
              <button
                className={`nav-item ${currentModule === "catalog" ? "active" : ""}`}
                onClick={() => setCurrentModule("catalog")}
              >
                <span className="nav-icon"><Package size={18} /></span>
                <span>Products & Plans</span>
              </button>

              <button
                className={`nav-item ${currentModule === "discounts" ? "active" : ""}`}
                onClick={() => setCurrentModule("discounts")}
              >
                <span className="nav-icon"><Tag size={18} /></span>
                <span>Discounts</span>
              </button>
            </>
          )}

          <button
            className={`nav-item ${currentModule === "invoices" ? "active" : ""}`}
            onClick={() => setCurrentModule("invoices")}
          >
            <span className="nav-icon"><Receipt size={18} /></span>
            <span>{isCustomer ? "My Invoices" : "Invoices"}</span>
          </button>

          <button
            className={`nav-item ${currentModule === "payments" ? "active" : ""}`}
            onClick={() => setCurrentModule("payments")}
          >
            <span className="nav-icon"><CreditCard size={18} /></span>
            <span>{isCustomer ? "My Payments" : "Payments"}</span>
          </button>

          {!isCustomer && (
            <button
              className={`nav-item ${currentModule === "billing-hook" ? "active" : ""}`}
              onClick={() => setCurrentModule("billing-hook")}
            >
              <span className="nav-icon"><Zap size={18} /></span>
              <span>Billing Simulator (M4)</span>
            </button>
          )}

          {!isCustomer && (
            <button
              className={`nav-item ${currentModule === "reports" ? "active" : ""}`}
              onClick={() => setCurrentModule("reports")}
            >
              <span className="nav-icon"><TrendingUp size={18} /></span>
              <span>Reports</span>
            </button>
          )}

          <button
            className={`nav-item ${currentModule === "settings" ? "active" : ""}`}
            onClick={() => setCurrentModule("settings")}
          >
            <span className="nav-icon"><Settings size={18} /></span>
            <span>Settings</span>
          </button>

          {isAdmin && (
            <button
              className={`nav-item ${currentModule === "admin" ? "active" : ""}`}
              onClick={() => setCurrentModule("admin")}
            >
              <span className="nav-icon"><Shield size={18} /></span>
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
            <span className="search-icon"><Search size={16} /></span>
            <input
              type="text"
              placeholder="Search contracts, quotations, customer email..."
              value={globalSearch}
              onChange={(e) => setGlobalSearch(e.target.value)}
            />
          </div>

          <div className="topbar-right">
            <div className="role-select-box">
              <span>Role:</span>
              <select
                value={role}
                onChange={(e) => {
                  const val = e.target.value;
                  if (val === "STAFF") handleDemoLogin("sales@example.com", "Staff123!");
                  else if (val === "CUSTOMER") handleDemoLogin("acme@corp.com", "Customer123!");
                  else if (val === "ADMIN") handleDemoLogin("admin@example.com", "Admin123!");
                }}
              >
                <option value="STAFF">Staff (Sales)</option>
                <option value="CUSTOMER">Customer (Acme)</option>
                <option value="ADMIN">Administrator</option>
              </select>
            </div>
            {user && (
              <button
                className="btn-secondary"
                style={{
                  padding: "6px 12px",
                  fontSize: "var(--font-size-small)",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                }}
                onClick={handleLogout}
              >
                <LogOut size={14} />
                <span>Logout</span>
              </button>
            )}
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
              <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
                <ProductsAdmin />
                <PlansAdmin />
              </div>
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
              <DiscountsAdmin />
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
                  Launch Django Admin Portal
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
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/unauthorized" element={<UnauthorizedPage />} />
          <Route path="/dashboard/*" element={<DashboardLayout />} />
          <Route path="/admin/*" element={<DashboardLayout />} />
          <Route path="/portal/*" element={<DashboardLayout />} />
          <Route path="/" element={<DashboardLayout />} />
          <Route path="*" element={<DashboardLayout />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
