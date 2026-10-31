import React, { useState, useEffect } from "react";
import {
  getQuotations,
  getQuotationTemplates,
  createQuotationFromTemplate,
  sendQuotation,
  acceptQuotation,
  convertQuotationToSubscription,
} from "../api/sales";

export default function QuotationsView({ onConvertedToSubscription }) {
  const [quotations, setQuotations] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [customerId, setCustomerId] = useState("");
  const [quoteNotes, setQuoteNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");

  async function loadData() {
    setLoading(true);
    try {
      const [quotesRes, tmplsRes] = await Promise.all([
        getQuotations(),
        getQuotationTemplates(),
      ]);
      setQuotations(quotesRes.results || quotesRes || []);
      setTemplates(tmplsRes.results || tmplsRes || []);
    } catch (err) {
      console.error("Failed to load sales data", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function handleCreateFromTemplate(e) {
    e.preventDefault();
    if (!selectedTemplate) return;
    setSubmitting(true);
    setMessage("");

    try {
      await createQuotationFromTemplate({
        template_id: selectedTemplate.id,
        customer_id: Number(customerId) || 1, // fallback to user id 1 for testing
        notes: quoteNotes,
      });
      setMessage("✓ Quotation created successfully!");
      setSelectedTemplate(null);
      setQuoteNotes("");
      loadData();
    } catch (err) {
      setMessage(`❌ Failed: ${err?.error || err?.message || "Unknown error"}`);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSend(id) {
    try {
      await sendQuotation(id);
      loadData();
    } catch (err) {
      alert(err?.error || "Failed to send quotation");
    }
  }

  async function handleAccept(id) {
    try {
      await acceptQuotation(id);
      loadData();
    } catch (err) {
      alert(err?.error || "Failed to accept quotation");
    }
  }

  async function handleConvert(id) {
    try {
      const newSub = await convertQuotationToSubscription(id);
      loadData();
      if (onConvertedToSubscription) {
        onConvertedToSubscription(newSub);
      }
    } catch (err) {
      alert(err?.error || "Failed to convert to subscription");
    }
  }

  return (
    <div className="view-container">
      <div className="view-header">
        <div>
          <h2>Sales Quotations & Templates</h2>
          <p>Pre-fill product lines with quotation templates and seamlessly convert quotes to subscriptions.</p>
        </div>
        <button className="btn-secondary" onClick={loadData}>🔄 Refresh</button>
      </div>

      {message && <div className="notice-banner">{message}</div>}

      {/* Templates Section for Sales Reps */}
      <div className="templates-section">
        <h3>Available Quotation Templates</h3>
        {templates.length === 0 ? (
          <div className="empty-sub-card">
            No quotation templates configured yet. You can create templates in Django Admin at <code>/admin/sales/quotationtemplate/</code>.
          </div>
        ) : (
          <div className="templates-grid">
            {templates.map((tmpl) => (
              <div key={tmpl.id} className="template-card">
                <div className="tmpl-title">
                  <strong>{tmpl.name}</strong>
                  <span className="tmpl-plan">{tmpl.plan_name}</span>
                </div>
                <p className="tmpl-desc">{tmpl.description || "Standard pre-filled bundle"}</p>
                <div className="tmpl-meta">
                  <span>Valid: {tmpl.validity_days} days</span>
                  <span>Terms: {tmpl.payment_terms}</span>
                  <span>Lines: {tmpl.lines?.length || 0} items</span>
                </div>
                <button
                  className="btn-primary"
                  onClick={() => setSelectedTemplate(tmpl)}
                >
                  Generate Quote from Template ➔
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Generate Quote Modal / Form */}
      {selectedTemplate && (
        <div className="modal-backdrop">
          <div className="modal-content">
            <h4>Generate Quotation from: {selectedTemplate.name}</h4>
            <form onSubmit={handleCreateFromTemplate}>
              <div className="form-group">
                <label>Customer User ID</label>
                <input
                  type="number"
                  placeholder="e.g., 1 (or customer ID)"
                  value={customerId}
                  onChange={(e) => setCustomerId(e.target.value)}
                  required
                />
                <small>Associated user account for contract.</small>
              </div>

              <div className="form-group">
                <label>Notes / Custom Terms</label>
                <textarea
                  value={quoteNotes}
                  onChange={(e) => setQuoteNotes(e.target.value)}
                  placeholder="Special terms, discount reference, or notes for customer..."
                  rows={2}
                />
              </div>

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setSelectedTemplate(null)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? "Generating..." : "Create Quotation"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Quotations List */}
      <div className="quotations-section">
        <h3>Recent Quotations</h3>
        {loading ? (
          <div className="loading-state">Loading quotations...</div>
        ) : quotations.length === 0 ? (
          <div className="empty-state">No quotations created yet. Use a template above to generate one!</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Quote Number</th>
                <th>Customer</th>
                <th>Plan</th>
                <th>Valid Until</th>
                <th>Status</th>
                <th>Total Value</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {quotations.map((q) => (
                <tr key={q.id}>
                  <td><strong>{q.quotation_number}</strong></td>
                  <td>{q.customer_email}</td>
                  <td>{q.plan_name}</td>
                  <td>{q.valid_until}</td>
                  <td>
                    <span className={`status-badge status-${q.status.toLowerCase()}`}>
                      {q.status}
                    </span>
                  </td>
                  <td><strong>${Number(q.total_amount).toFixed(2)}</strong></td>
                  <td>
                    <div className="inline-action-buttons">
                      {q.status === "DRAFT" && (
                        <button className="btn-sm btn-primary" onClick={() => handleSend(q.id)}>
                          Send ➔
                        </button>
                      )}
                      {q.status === "SENT" && (
                        <button className="btn-sm btn-success" onClick={() => handleAccept(q.id)}>
                          Accept ✓
                        </button>
                      )}
                      {(q.status === "ACCEPTED" || q.status === "SENT") && (
                        <button className="btn-sm btn-accent" onClick={() => handleConvert(q.id)}>
                          Convert to Subscription ➔
                        </button>
                      )}
                      {q.status === "CONVERTED" && (
                        <span className="converted-tag">✓ Converted</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
