import { useEffect, useState } from "react";
import { AuthProvider } from "./context/AuthContext";
import { initializeCsrf } from "./api/auth";
import SubscriptionsView from "./components/SubscriptionsView";
import QuotationsView from "./components/QuotationsView";
import Member4BillingSimulator from "./components/Member4BillingSimulator";
import "./App.css";

function MainContent() {
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

  return (
    <div className="app-layout">
      {/* Top Navigation Bar */}
      <header className="app-header">
        <div className="brand-group">
          <div className="brand-badge">Member 3</div>
          <div>
            <h1>Subscription & Contracts Engine</h1>
            <p className="brand-subtitle">State Machine Pipeline, Contract Records, & Quotation Templates</p>
          </div>
        </div>

        <div className="status-indicator">
          <span className="status-dot online"></span>
          <span>{backendStatus}</span>
        </div>
      </header>

      {/* Primary Tab Navigation */}
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

      {/* Content Body */}
      <main className="app-main-content">
        {activeTab === "subscriptions" && <SubscriptionsView />}
        {activeTab === "quotations" && (
          <QuotationsView
            onConvertedToSubscription={() => {
              setActiveTab("subscriptions");
            }}
          />
        )}
        {activeTab === "billing-hook" && <Member4BillingSimulator />}
      </main>
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <MainContent />
    </AuthProvider>
  );
}

export default App;
