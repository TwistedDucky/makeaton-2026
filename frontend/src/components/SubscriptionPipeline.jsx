import React, { useState } from "react";
import { transitionSubscription } from "../api/subscriptions";

const PIPELINE_STAGES = [
  { key: "DRAFT", label: "Draft", desc: "Initial contract setup" },
  { key: "QUOTATION", label: "Quotation", desc: "Sent for client review" },
  { key: "CONFIRMED", label: "Confirmed", desc: "Accepted by customer" },
  { key: "ACTIVE", label: "Active", desc: "Live contract & billing" },
  { key: "CLOSED", label: "Closed", desc: "Completed / Terminated" },
];

export default function SubscriptionPipeline({ subscription, onUpdated, onClose }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [closeReason, setCloseReason] = useState("");
  const [showCloseModal, setShowCloseModal] = useState(false);

  const currentIdx = PIPELINE_STAGES.findIndex((s) => s.key === subscription.status);

  async function handleTransition(targetStatus, reason = "") {
    setLoading(true);
    setError("");
    try {
      const updated = await transitionSubscription(subscription.id, targetStatus, reason);
      if (onUpdated) onUpdated(updated);
    } catch (err) {
      setError(err?.message || err?.error || "Failed to transition subscription");
    } finally {
      setLoading(false);
      setShowCloseModal(false);
    }
  }

  return (
    <div className="pipeline-container">
      <div className="pipeline-header">
        <div>
          <h3>{subscription.subscription_number}</h3>
          <span className="customer-tag">{subscription.customer_email}</span>
        </div>
        <button className="btn-secondary" onClick={onClose}>✕ Close</button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {/* Visual Stepper Bar */}
      <div className="stepper-wrapper">
        {PIPELINE_STAGES.map((stage, idx) => {
          const isPassed = idx < currentIdx;
          const isCurrent = idx === currentIdx;
          const isFuture = idx > currentIdx;
          const isClosed = subscription.status === "CLOSED";

          return (
            <div
              key={stage.key}
              className={`stepper-step ${isCurrent ? "current" : ""} ${isPassed ? "completed" : ""} ${isClosed && isCurrent ? "step-closed" : ""}`}
            >
              <div className="step-circle">
                {isPassed ? "✓" : idx + 1}
              </div>
              <div className="step-label">
                <strong>{stage.label}</strong>
                <small>{stage.desc}</small>
              </div>
              {idx < PIPELINE_STAGES.length - 1 && <div className="step-connector" />}
            </div>
          );
        })}
      </div>

      {/* Action Controls based on Current State */}
      <div className="pipeline-actions">
        <h4>State Machine Actions:</h4>
        <div className="action-button-group">
          {subscription.status === "DRAFT" && (
            <>
              <button
                className="btn-primary"
                disabled={loading}
                onClick={() => handleTransition("QUOTATION")}
              >
                Send as Quotation ➔
              </button>
              <button
                className="btn-accent"
                disabled={loading}
                onClick={() => handleTransition("CONFIRMED")}
              >
                Directly Confirm ➔
              </button>
              <button
                className="btn-danger"
                disabled={loading}
                onClick={() => setShowCloseModal(true)}
              >
                Cancel Contract
              </button>
            </>
          )}

          {subscription.status === "QUOTATION" && (
            <>
              <button
                className="btn-primary"
                disabled={loading}
                onClick={() => handleTransition("CONFIRMED")}
              >
                Confirm Subscription ➔
              </button>
              <button
                className="btn-danger"
                disabled={loading}
                onClick={() => setShowCloseModal(true)}
              >
                Decline / Close
              </button>
            </>
          )}

          {subscription.status === "CONFIRMED" && (
            <>
              <button
                className="btn-success"
                disabled={loading}
                onClick={() => handleTransition("ACTIVE")}
              >
                ⚡ Activate Contract (Start Billing)
              </button>
              <button
                className="btn-danger"
                disabled={loading}
                onClick={() => setShowCloseModal(true)}
              >
                Cancel Subscription
              </button>
            </>
          )}

          {subscription.status === "ACTIVE" && (
            <button
              className="btn-danger"
              disabled={loading}
              onClick={() => setShowCloseModal(true)}
            >
              Terminate / Close Subscription
            </button>
          )}

          {subscription.status === "CLOSED" && (
            <div className="closed-badge-notice">
              🔒 Contract is permanently Closed. No further state transitions allowed.
              {subscription.cancellation_reason && (
                <div className="reason-text">Reason: {subscription.cancellation_reason}</div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Contract & Billing Details */}
      <div className="pipeline-details-grid">
        <div className="details-card">
          <h4>Contract Details</h4>
          <div className="detail-row">
            <span>Plan:</span>
            <strong>{subscription.plan_name} ({subscription.plan_billing_period})</strong>
          </div>
          <div className="detail-row">
            <span>Payment Terms:</span>
            <strong>{subscription.payment_terms}</strong>
          </div>
          <div className="detail-row">
            <span>Start Date:</span>
            <span>{subscription.start_date || "—"}</span>
          </div>
          <div className="detail-row">
            <span>Expiry Date:</span>
            <span>{subscription.expiry_date || "Unlimited / Open-ended"}</span>
          </div>
        </div>

        <div className="details-card">
          <h4>Billing Cycle (Member 4 Integration)</h4>
          <div className="detail-row">
            <span>Current Period:</span>
            <span>
              {subscription.current_period_start || "—"} to {subscription.current_period_end || "—"}
            </span>
          </div>
          <div className="detail-row">
            <span>Next Billing Date:</span>
            <strong className="text-highlight">{subscription.next_billing_date || "—"}</strong>
          </div>
          <div className="detail-row">
            <span>Last Billed:</span>
            <span>{subscription.last_billed_date || "Not yet billed"}</span>
          </div>
        </div>
      </div>

      {/* Product Lines Table */}
      <div className="lines-table-container">
        <h4>Contract Product Lines</h4>
        <table className="data-table">
          <thead>
            <tr>
              <th>Product</th>
              <th>Variant</th>
              <th>Qty</th>
              <th>Unit Price</th>
              <th>Taxes</th>
              <th>Total Amount</th>
            </tr>
          </thead>
          <tbody>
            {(subscription.lines || []).map((line) => (
              <tr key={line.id}>
                <td><strong>{line.product_name}</strong></td>
                <td>{line.variant_display || "—"}</td>
                <td>{line.quantity}</td>
                <td>${Number(line.unit_price).toFixed(2)}</td>
                <td>${Number(line.taxes).toFixed(2)}</td>
                <td><strong>${Number(line.amount).toFixed(2)}</strong></td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan="5" style={{ textAlign: "right" }}>Subtotal:</td>
              <td>${Number(subscription.subtotal).toFixed(2)}</td>
            </tr>
            <tr>
              <td colSpan="5" style={{ textAlign: "right" }}>Taxes:</td>
              <td>${Number(subscription.tax_amount).toFixed(2)}</td>
            </tr>
            <tr className="grand-total-row">
              <td colSpan="5" style={{ textAlign: "right" }}>Total Contract Value:</td>
              <td>${Number(subscription.total_amount).toFixed(2)}</td>
            </tr>
          </tfoot>
        </table>
      </div>

      {/* Close/Cancel Reason Modal */}
      {showCloseModal && (
        <div className="modal-backdrop">
          <div className="modal-content">
            <h4>Close / Cancel Subscription</h4>
            <p>Please enter a reason for terminating this contract:</p>
            <textarea
              value={closeReason}
              onChange={(e) => setCloseReason(e.target.value)}
              placeholder="e.g., Customer requested early cancellation, non-payment, expired..."
              rows={3}
            />
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setShowCloseModal(false)}>Back</button>
              <button
                className="btn-danger"
                onClick={() => handleTransition("CLOSED", closeReason)}
              >
                Confirm Closure
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
