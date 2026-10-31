import React from "react";

export default function ReportsView() {
  const metrics = [
    { label: "Monthly Recurring Revenue (MRR)", value: "₹6,683.86", change: "+12.4% vs last month" },
    { label: "Annual Run-Rate (ARR)", value: "₹80,206.32", change: "+18.2% YoY" },
    { label: "Average Revenue Per User (ARPU)", value: "₹1,670.96", change: "Healthy SaaS benchmark" },
    { label: "Net Revenue Retention (NRR)", value: "114%", change: "Low contract churn (< 2%)" },
  ];

  const stageBreakdown = [
    { stage: "Active", count: 4, percentage: 50, color: "var(--status-active-text)", bg: "var(--status-active-bg)" },
    { stage: "Quotation / Under Review", count: 2, percentage: 25, color: "var(--status-pending-text)", bg: "var(--status-pending-bg)" },
    { stage: "Confirmed", count: 1, percentage: 12.5, color: "var(--status-confirmed-text)", bg: "var(--status-confirmed-bg)" },
    { stage: "Draft", count: 1, percentage: 12.5, color: "var(--secondary-text)", bg: "var(--muted-beige)" },
  ];

  return (
    <div className="view-container">
      <div className="view-header">
        <div>
          <h2>Analytics & Financial Reports</h2>
          <p>Subscription revenue health, contract distribution, and financial forecasting.</p>
        </div>
      </div>

      <div className="kpi-grid">
        {metrics.map((m, i) => (
          <div key={i} className="kpi-card">
            <div className="kpi-label">{m.label}</div>
            <div className="kpi-value tabular-num">{m.value}</div>
            <div className="kpi-footer">
              <span className="status-badge status-active">{m.change}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: "1.5rem" }}>
        <div className="card-header">
          <div>
            <h3>Subscription Portfolio Distribution</h3>
            <p className="card-subtitle">Active contracts by lifecycle state</p>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem", padding: "1rem 0" }}>
          {stageBreakdown.map((s, i) => (
            <div key={i}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.4rem", fontSize: "0.9rem" }}>
                <span>
                  <strong>{s.stage}</strong> ({s.count} contracts)
                </span>
                <span className="tabular-num">
                  <strong>{s.percentage}%</strong>
                </span>
              </div>
              <div
                style={{
                  width: "100%",
                  height: "12px",
                  backgroundColor: "var(--soft-vanilla)",
                  border: "1px solid var(--border)",
                  borderRadius: "6px",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${s.percentage}%`,
                    height: "100%",
                    backgroundColor: "var(--midnight-indigo)",
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
