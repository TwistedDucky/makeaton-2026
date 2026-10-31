import React, { useState, useEffect } from "react";
import { getReports } from "../api/reports";
import { AlertTriangle, RefreshCw, X } from "lucide-react";

export default function ReportsView() {
  const [metrics, setMetrics] = useState([]);
  const [stageBreakdown, setStageBreakdown] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  async function loadReports() {
    setLoading(true);
    setError(null);
    try {
      const res = await getReports();
      const data = res?.data || res;
      if (data?.metrics && Array.isArray(data.metrics)) {
        setMetrics(data.metrics);
      } else {
        setMetrics([]);
      }
      if (data?.stageBreakdown && Array.isArray(data.stageBreakdown)) {
        setStageBreakdown(data.stageBreakdown);
      } else {
        setStageBreakdown([]);
      }
    } catch (err) {
      console.error("Failed to load reports:", err);
      const errMsg =
        err?.message ||
        (typeof err === "string" ? err : null) ||
        (err?.errors ? JSON.stringify(err.errors) : "Failed to load financial reports from server.");
      setError(errMsg);
      setMetrics([]);
      setStageBreakdown([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadReports();
  }, []);

  return (
    <div className="view-container">
      <div className="view-header">
        <div>
          <h2>Analytics & Financial Reports</h2>
          <p>Subscription revenue health, contract distribution, and financial forecasting.</p>
        </div>
        <button
          className="btn-secondary"
          onClick={loadReports}
          disabled={loading}
          style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
        >
          <RefreshCw size={14} className={loading ? "spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Real Error Notice Banner - No silent mock hiding errors */}
      {error && (
        <div
          className="notice-banner"
          style={{
            backgroundColor: "var(--color-status-overdue-bg)",
            borderColor: "var(--color-status-overdue-text)",
            color: "var(--color-status-overdue-text)",
            marginBottom: "1.5rem",
            padding: "0.85rem 1.25rem",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--color-status-overdue-text)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
            <AlertTriangle size={18} />
            <span>{error}</span>
          </span>
          <button
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "inherit",
              display: "flex",
              alignItems: "center",
            }}
            onClick={() => setError(null)}
          >
            <X size={16} />
          </button>
        </div>
      )}

      {loading ? (
        <div className="card" style={{ padding: "3rem", textAlign: "center", color: "var(--color-text-secondary)" }}>
          Loading reports and revenue analytics...
        </div>
      ) : metrics.length === 0 && stageBreakdown.length === 0 && !error ? (
        <div className="card" style={{ padding: "3rem", textAlign: "center", color: "var(--color-text-secondary)" }}>
          <div style={{ fontWeight: 600, fontSize: "1.1rem", marginBottom: "0.5rem", color: "var(--color-text-primary)" }}>
            No Financial Data Available
          </div>
          <p style={{ margin: 0 }}>
            Reports will populate once recurring subscriptions are activated and invoices are processed.
          </p>
        </div>
      ) : (
        <>
          {metrics.length > 0 && (
            <div className="kpi-grid">
              {metrics.map((m, i) => (
                <div key={i} className="kpi-card">
                  <div className="kpi-label">{m.label}</div>
                  <div className="kpi-value tabular-num">{m.value}</div>
                  {m.change && (
                    <div className="kpi-footer">
                      <span className="status-badge status-active">{m.change}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {stageBreakdown.length > 0 && (
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
                        backgroundColor: "var(--color-muted)",
                        border: "1px solid var(--color-border)",
                        borderRadius: "6px",
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          width: `${s.percentage}%`,
                          height: "100%",
                          backgroundColor: "var(--color-midnight-indigo)",
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
