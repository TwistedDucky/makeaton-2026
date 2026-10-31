import React, { useState, useEffect } from "react";
import { getDueSubscriptions, advanceBilling } from "../api/subscriptions";

export default function Member4BillingSimulator() {
  const [targetDate, setTargetDate] = useState(new Date().toISOString().split("T")[0]);
  const [dueList, setDueList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState("");

  async function loadDueSubscriptions() {
    setLoading(true);
    setActionMessage("");
    try {
      const res = await getDueSubscriptions(targetDate);
      setDueList(res.data || []);
    } catch (err) {
      console.error("Failed to load due subscriptions", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDueSubscriptions();
  }, [targetDate]);

  async function handleAdvance(subId) {
    try {
      const res = await advanceBilling(subId);
      setActionMessage(`✓ Successfully advanced subscription #${subId} to next billing date: ${res.data.next_billing_date}`);
      loadDueSubscriptions();
    } catch (err) {
      setActionMessage(`❌ Failed to advance billing: ${err?.message || err?.error || "Error"}`);
    }
  }

  return (
    <div className="view-container">
      <div className="view-header">
        <div>
          <h2>Member 4 Automated Invoicing Integration</h2>
          <p>Test the exact hooks built for Member 4's billing automation: <code>get_due_subscriptions()</code> and <code>advance_next_billing_date()</code>.</p>
        </div>
      </div>

      <div className="simulator-controls">
        <label>
          Target Billing Date:
          <input
            type="date"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
          />
        </label>
        <button className="btn-secondary" onClick={loadDueSubscriptions}>Query Due Subscriptions</button>
      </div>

      {actionMessage && <div className="notice-banner">{actionMessage}</div>}

      <div className="due-list-container">
        <h3>Subscriptions Due on or before {targetDate} ({dueList.length})</h3>

        {loading ? (
          <div className="loading-state">Querying database...</div>
        ) : dueList.length === 0 ? (
          <div className="empty-state">
            No active subscriptions are due for billing on {targetDate}.
            <small>Ensure a subscription is in <strong>ACTIVE</strong> state with <code>next_billing_date &le; {targetDate}</code>.</small>
          </div>
        ) : (
          <div className="due-cards-grid">
            {dueList.map((item) => (
              <div key={item.id} className="due-card">
                <div className="due-card-header">
                  <strong>Subscription #{item.id}</strong>
                  <span className="customer-tag">Customer #{item.customer_id}</span>
                </div>

                <div className="period-box">
                  <span>Billing Period:</span>
                  <strong>{item.period_start} to {item.period_end}</strong>
                </div>

                <div style={{ fontSize: "var(--font-size-small)", marginTop: "4px", color: "var(--color-text-secondary)" }}>
                  <span>Payment Terms: </span>
                  <strong>
                    {item.payment_terms_days === 0
                      ? "Immediate (0 days)"
                      : item.payment_terms_days !== undefined
                      ? `Net ${item.payment_terms_days} days`
                      : "Default (30 days)"}
                  </strong>
                </div>

                <div className="lines-summary">
                  <strong>Lines to Invoice:</strong>
                  <ul>
                    {item.lines.map((l, i) => (
                      <li key={i}>
                        {l.product_name} &times; {l.quantity} @ ₹{String(l.unit_price)}
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="due-card-actions">
                  <button
                    className="btn-primary btn-block"
                    onClick={() => handleAdvance(item.id)}
                  >
                    Simulate invoice generation & advance period
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
