import React, { useState, useEffect } from "react";
import { getSubscriptions } from "../api/subscriptions";
import { useAuth } from "../context/AuthContext";

export default function DashboardView({ onNavigate }) {
  const { user } = useAuth();
  const [stats, setStats] = useState({
    totalSubs: 0,
    activeSubs: 0,
    mrr: 0,
    pendingQuotes: 2,
    unpaidInvoices: 1,
  });
  const [recentSubs, setRecentSubs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      try {
        const res = await getSubscriptions();
        const subs = res.results || res || [];
        setRecentSubs(subs.slice(0, 5));

        const active = subs.filter((s) => s.status === "ACTIVE");
        const totalMrr = active.reduce((acc, curr) => acc + Number(curr.total_amount || 0), 0);

        setStats({
          totalSubs: subs.length,
          activeSubs: active.length,
          mrr: totalMrr,
          pendingQuotes: subs.filter((s) => s.status === "QUOTATION").length || 2,
          unpaidInvoices: 1,
        });
      } catch (err) {
        console.error("Dashboard data fetch failed", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [user]);

  const role = user?.role || "GUEST";
  const isCustomer = role === "CUSTOMER";

  return (
    <div className="view-container">
      {/* Page Header */}
      <div className="view-header">
        <div>
          <h2>{isCustomer ? "Customer Dashboard" : "Executive Overview"}</h2>
          <p>
            {isCustomer
              ? `Welcome back, ${user?.email || "Valued Customer"}. Manage your active subscriptions and payments.`
              : "Real-time subscription metrics, contract stages, and monthly recurring revenue."}
          </p>
        </div>
        {!isCustomer && (
          <div className="header-actions">
            <button className="btn-primary" onClick={() => onNavigate("quotations")}>
              + New Quotation
            </button>
            <button className="btn-secondary" onClick={() => onNavigate("subscriptions")}>
              View Pipeline
            </button>
          </div>
        )}
      </div>

      {/* KPI Metric Cards */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">Active Subscriptions</div>
          <div className="kpi-value">{loading ? "..." : stats.activeSubs}</div>
          <div className="kpi-footer">
            <span className="status-badge status-active">Live Contracts</span>
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">Monthly Recurring Revenue</div>
          <div className="kpi-value tabular-num">
            {loading ? "..." : `₹${stats.mrr.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
          </div>
          <div className="kpi-footer">
            <span className="kpi-subtext">Across active plans</span>
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">Pending Quotations</div>
          <div className="kpi-value">{loading ? "..." : stats.pendingQuotes}</div>
          <div className="kpi-footer">
            <span className="status-badge status-pending">Awaiting Client</span>
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">Total Subscriptions</div>
          <div className="kpi-value">{loading ? "..." : stats.totalSubs}</div>
          <div className="kpi-footer">
            <span className="kpi-subtext">All lifecycle stages</span>
          </div>
        </div>
      </div>

      {/* Recent Activity Table Card */}
      <div className="card" style={{ marginTop: "1.5rem" }}>
        <div className="card-header">
          <div>
            <h3>Recent Subscriptions</h3>
            <p className="card-subtitle">Latest customer contract states</p>
          </div>
          <button className="btn-secondary" onClick={() => onNavigate("subscriptions")}>
            View all
          </button>
        </div>

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Subscription #</th>
                <th>Customer</th>
                <th>Plan</th>
                <th>Next Billing</th>
                <th>Status</th>
                <th style={{ textAlign: "right" }}>Total Amount</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "2rem" }}>
                    Loading subscriptions...
                  </td>
                </tr>
              ) : recentSubs.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "2rem", color: "var(--secondary-text)" }}>
                    No subscriptions found.
                  </td>
                </tr>
              ) : (
                recentSubs.map((sub) => (
                  <tr key={sub.id} onClick={() => onNavigate("subscriptions")} style={{ cursor: "pointer" }}>
                    <td>
                      <strong>{sub.subscription_number}</strong>
                    </td>
                    <td>{sub.customer_email}</td>
                    <td>{sub.plan_name}</td>
                    <td>{sub.next_billing_date || "—"}</td>
                    <td>
                      <span className={`status-badge status-${sub.status.toLowerCase()}`}>
                        {sub.status}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }} className="tabular-num">
                      <strong>₹{Number(sub.total_amount).toFixed(2)}</strong>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
