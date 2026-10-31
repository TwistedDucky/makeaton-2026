/**
 * Member3App — preserved exactly from the original App.jsx.
 * This is Member 3's subscription/quotation engine UI.
 * It will be replaced by proper routed pages once the full
 * layout shell is built.
 */
import { useEffect, useState } from "react";
import { useAuth } from "./context/AuthContext";
import { initializeCsrf } from "./api/auth";
import SubscriptionsView from "./components/SubscriptionsView";
import QuotationsView from "./components/QuotationsView";
import Member4BillingSimulator from "./components/Member4BillingSimulator";

export default function Member3App() {
    const { user, login, logout } = useAuth();
    const [activeTab, setActiveTab] = useState("subscriptions");
    const [backendStatus, setBackendStatus] = useState("Connecting...");

    useEffect(() => {
        initializeCsrf()
            .then((data) => {
                if (data.success) {
                    setBackendStatus("Connected (Session & CSRF Ready)");
                } else {
                    setBackendStatus("CSRF initialization failed");
                }
            })
            .catch(() => setBackendStatus("Could not connect to Django"));
    }, []);

    async function handleQuickLogin(email, password) {
        try {
            await login(email, password);
        } catch (err) {
            alert("Login failed: " + (err?.message || "Invalid credentials"));
        }
    }

    async function handleLogout() {
        try {
            await logout();
        } catch (err) {
            console.error("Logout failed", err);
        }
    }

    return (
        <div className="app-layout">
            {/* Top Header */}
            <header className="app-header">
                <div className="brand-group">
                    <div className="brand-badge">Member 3</div>
                    <div>
                        <h1>Subscription & Contracts Engine</h1>
                        <p className="brand-subtitle">
                            State Machine Pipeline, Contract Records, & Quotation Templates
                        </p>
                    </div>
                </div>

                <div className="header-right">
                    <div className="status-indicator">
                        <span className="status-dot online"></span>
                        <span>{backendStatus}</span>
                    </div>

                    {/* Quick Demo Login Switcher */}
                    <div className="auth-box">
                        {user ? (
                            <div className="logged-in-user">
                                <span>
                                    👤 <strong>{user.email}</strong> ({user.role || "Active"})
                                </span>
                                <button
                                    className="btn-sm btn-secondary"
                                    onClick={handleLogout}
                                >
                                    Log Out
                                </button>
                            </div>
                        ) : (
                            <div className="quick-login-bar">
                                <span className="login-hint">1-Click Test Login:</span>
                                <button
                                    className="btn-sm btn-primary"
                                    onClick={() => handleQuickLogin("sales@example.com", "Staff123!")}
                                >
                                    Sales Rep 👤
                                </button>
                                <button
                                    className="btn-sm btn-accent"
                                    onClick={() => handleQuickLogin("acme@corp.com", "Customer123!")}
                                >
                                    Customer 🏢
                                </button>
                                <button
                                    className="btn-sm btn-secondary"
                                    onClick={() => handleQuickLogin("admin@example.com", "Admin123!")}
                                >
                                    Admin 🛡️
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            </header>

            {/* Tab Navigation */}
            <nav className="tab-navigation">
                <button
                    className={`tab-button ${activeTab === "subscriptions" ? "tab-active" : ""}`}
                    onClick={() => setActiveTab("subscriptions")}
                >
                    📋 Subscriptions & Pipeline
                </button>
                <button
                    className={`tab-button ${activeTab === "quotations" ? "tab-active" : ""}`}
                    onClick={() => setActiveTab("quotations")}
                >
                    💼 Quotations & Templates
                </button>
                <button
                    className={`tab-button ${activeTab === "billing-hook" ? "tab-active" : ""}`}
                    onClick={() => setActiveTab("billing-hook")}
                >
                    ⚡ Member 4 Billing Hooks
                </button>
            </nav>

            {/* Content */}
            <main className="app-main-content">
                {activeTab === "subscriptions" && <SubscriptionsView />}
                {activeTab === "quotations" && (
                    <QuotationsView
                        onConvertedToSubscription={() => setActiveTab("subscriptions")}
                    />
                )}
                {activeTab === "billing-hook" && <Member4BillingSimulator />}
            </main>
        </div>
    );
}
