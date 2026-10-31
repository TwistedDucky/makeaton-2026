import React, { useState, useEffect } from "react";
import {
  getQuotations,
  getQuotationTemplates,
  createQuotationFromTemplate,
  createCustomQuotation,
  sendQuotation,
  acceptQuotation,
  declineQuotation,
  convertQuotationToSubscription,
} from "../api/sales";
import { getProducts, getPlans } from "../api/catalog";
import { apiRequest } from "../api/client";
import { useAuth } from "../context/AuthContext";

export default function QuotationsView({ onConvertedToSubscription }) {
  const { user } = useAuth();
  const [quotations, setQuotations] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [selectedCustomerId, setSelectedCustomerId] = useState("");
  const [quoteNotes, setQuoteNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");

  // Custom Quote Modal State
  const [showCustomModal, setShowCustomModal] = useState(false);
  const [previewQuote, setPreviewQuote] = useState(null);
  const [customPlanId, setCustomPlanId] = useState("1");
  const [customTerms, setCustomTerms] = useState("NET_30");
  const [customValidityDays, setCustomValidityDays] = useState(30);
  const [availablePlans, setAvailablePlans] = useState([]);
  const [availableProducts, setAvailableProducts] = useState([]);
  const [customLines, setCustomLines] = useState([
    { product_id: 1, quantity: 1, unit_price: "2000.00", taxes: "360.00" },
  ]);

  const role = user?.role || "STAFF";
  const isCustomer = role === "CUSTOMER";

  async function loadData() {
    setLoading(true);
    try {
      const [quotesRes, tmplsRes, usersRes, prodsRes, plansRes] = await Promise.all([
        getQuotations(),
        getQuotationTemplates(),
        apiRequest("/users/").catch(() => ({ results: [] })),
        getProducts({ page_size: 100 }).catch(() => ({ results: [] })),
        getPlans({ page_size: 100 }).catch(() => ({ results: [] })),
      ]);
      setQuotations(quotesRes.results || quotesRes || []);
      setTemplates(tmplsRes.results || tmplsRes || []);

      const pList = prodsRes.results || prodsRes || [];
      const plList = plansRes.results || plansRes || [];
      if (pList.length > 0) {
        setAvailableProducts(pList);
        setCustomLines([
          {
            product_id: pList[0].id,
            quantity: 1,
            unit_price: pList[0].sales_price,
            taxes: (Number(pList[0].sales_price) * 0.18).toFixed(2),
          },
        ]);
      }
      if (plList.length > 0) {
        setAvailablePlans(plList);
        setCustomPlanId(String(plList[0].id));
      }

      const userList = usersRes.results || usersRes || [];
      const custs = userList.filter((u) => u.role === "CUSTOMER");
      if (custs.length > 0) {
        setCustomers(custs);
        setSelectedCustomerId(String(custs[0].id));
      } else {
        const fallbacks = [
          { id: 3, email: "acme@corp.com", first_name: "Acme", last_name: "Corp" },
          { id: 4, email: "stark@industries.com", first_name: "Stark", last_name: "Industries" },
        ];
        setCustomers(fallbacks);
        setSelectedCustomerId("3");
      }
    } catch (err) {
      console.error("Failed to load sales data", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [user]);

  async function handleCreateFromTemplate(e) {
    e.preventDefault();
    if (!selectedTemplate) return;
    setSubmitting(true);
    setMessage("");

    try {
      await createQuotationFromTemplate({
        template_id: selectedTemplate.id,
        customer_id: Number(selectedCustomerId),
        notes: quoteNotes,
      });
      setMessage("✓ Quotation created successfully from template!");
      setSelectedTemplate(null);
      setQuoteNotes("");
      loadData();
    } catch (err) {
      setMessage(`❌ Failed: ${err?.error || err?.message || "Unknown error"}`);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCreateCustom(e) {
    e.preventDefault();
    setSubmitting(true);
    setMessage("");

    const validUntil = new Date();
    validUntil.setDate(validUntil.getDate() + Number(customValidityDays));
    const validUntilStr = validUntil.toISOString().split("T")[0];

    try {
      await createCustomQuotation({
        customer: Number(selectedCustomerId),
        plan: Number(customPlanId),
        valid_until: validUntilStr,
        payment_terms: customTerms,
        notes: quoteNotes || "Customized subscription quotation.",
        lines: customLines.map((l) => ({
          product: Number(l.product_id),
          quantity: Number(l.quantity),
          unit_price: l.unit_price,
          taxes: l.taxes,
        })),
      });
      setMessage("✓ Custom quotation created successfully!");
      setShowCustomModal(false);
      setQuoteNotes("");
      loadData();
    } catch (err) {
      setMessage(`❌ Failed: ${err?.error || err?.message || "Failed to create custom quotation"}`);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSend(id) {
    try {
      await sendQuotation(id);
      setMessage("✓ Quotation dispatched to customer!");
      loadData();
    } catch (err) {
      alert(err?.error || "Failed to send quotation");
    }
  }

  async function handleAccept(id) {
    try {
      await acceptQuotation(id);
      setMessage("✓ Quotation accepted by client!");
      loadData();
    } catch (err) {
      alert(err?.error || "Failed to accept quotation");
    }
  }

  async function handleDecline(id) {
    const reason = prompt("Enter decline reason (optional):") || "";
    try {
      await declineQuotation(id, reason);
      setMessage("Quotation marked as declined.");
      loadData();
    } catch (err) {
      alert(err?.error || "Failed to decline quotation");
    }
  }

  async function handleConvert(id) {
    try {
      const newSub = await convertQuotationToSubscription(id);
      setMessage(`✓ Quotation converted into Subscription ${newSub.subscription_number}!`);
      loadData();
      if (onConvertedToSubscription) {
        onConvertedToSubscription(newSub);
      }
    } catch (err) {
      alert(err?.error || "Failed to convert to subscription");
    }
  }

  function addCustomLine() {
    setCustomLines([
      ...customLines,
      { product_id: 2, quantity: 1, unit_price: "100.00", taxes: "18.00" },
    ]);
  }

  function removeCustomLine(idx) {
    setCustomLines(customLines.filter((_, i) => i !== idx));
  }

  function updateCustomLine(idx, field, val) {
    const updated = [...customLines];
    updated[idx][field] = val;
    setCustomLines(updated);
  }

  const displayQuotations = isCustomer
    ? quotations.filter((q) => q.customer_email === user?.email || q.customer_email === "acme@corp.com")
    : quotations;

  return (
    <div className="view-container">
      {/* Header */}
      <div className="view-header">
        <div>
          <h2>{isCustomer ? "My Quotations & Offers" : "Sales Quotations & Templates"}</h2>
          <p>
            {isCustomer
              ? "Review offers prepared by Brightloop sales reps. Accept or decline proposed contracts."
              : "Pre-fill product lines with quotation templates and seamlessly convert quotes to subscriptions."}
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          {!isCustomer && (
            <button className="btn-primary" onClick={() => setShowCustomModal(true)}>
              + New Custom Quote
            </button>
          )}
          <button className="btn-secondary" onClick={loadData}>
            🔄 Refresh
          </button>
        </div>
      </div>

      {message && <div className="notice-banner">{message}</div>}

      {/* Templates Section for Sales Reps */}
      {!isCustomer && (
        <div className="card" style={{ marginBottom: "1.75rem" }}>
          <div className="card-header">
            <div>
              <h3>Quotation Templates</h3>
              <p className="card-subtitle">One-click starter templates configured by the sales lead</p>
            </div>
            <a
              href="http://localhost:8001/admin/sales/quotationtemplate/"
              target="_blank"
              rel="noreferrer"
              className="btn-secondary"
              style={{ fontSize: "0.8rem", padding: "0.35rem 0.75rem" }}
            >
              Manage in Admin
            </a>
          </div>

          {templates.length === 0 ? (
            <div className="empty-state">No quotation templates configured yet.</div>
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
                  <button className="btn-primary" onClick={() => setSelectedTemplate(tmpl)}>
                    Generate quote from template
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Quotations List */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3>{isCustomer ? "Offers Awaiting Your Review" : "Active Quotations Directory"}</h3>
            <p className="card-subtitle">
              {isCustomer
                ? "Click 'Review & Sign' to inspect proposal lines and activate your contract"
                : "Manage proposal lifecycles: Draft to Sent to Accepted to Converted"}
            </p>
          </div>
        </div>

        {loading ? (
          <div className="loading-state">Loading quotations...</div>
        ) : displayQuotations.length === 0 ? (
          <div className="empty-state">
            <p>No quotations found.</p>
            <small>
              {isCustomer
                ? "No pending quotations are currently assigned to your account."
                : "Generate a new quote from one of the templates above or click '+ New Custom Quote'!"}
            </small>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Quote #</th>
                  <th>Customer</th>
                  <th>Plan</th>
                  <th>Valid Until</th>
                  <th>Status</th>
                  <th style={{ textAlign: "right" }}>Total Value</th>
                  <th style={{ textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {displayQuotations.map((q) => (
                  <tr key={q.id}>
                    <td>
                      <strong>{q.quotation_number}</strong>
                    </td>
                    <td>{q.customer_email}</td>
                    <td>{q.plan_name}</td>
                    <td>{q.valid_until}</td>
                    <td>
                      <span
                        className={`status-badge ${
                          q.status === "ACCEPTED" || q.status === "CONVERTED"
                            ? "status-active"
                            : q.status === "SENT"
                            ? "status-confirmed"
                            : q.status === "EXPIRED" || q.status === "DECLINED"
                            ? "status-overdue"
                            : "status-pending"
                        }`}
                      >
                        {q.status}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }} className="tabular-num">
                      <strong>₹{Number(q.total_amount).toFixed(2)}</strong>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <div style={{ display: "inline-flex", gap: "0.4rem" }}>
                        <button
                          className="btn-secondary"
                          style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
                          onClick={() => setPreviewQuote(q)}
                        >
                          View
                        </button>

                        {/* Customer Actions */}
                        {isCustomer && q.status === "SENT" && (
                          <>
                            <button
                              className="btn-primary"
                              style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
                              onClick={() => handleAccept(q.id)}
                            >
                              Accept and sign
                            </button>
                            <button
                              className="btn-danger"
                              style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
                              onClick={() => handleDecline(q.id)}
                            >
                              Decline
                            </button>
                          </>
                        )}

                        {/* Staff Actions */}
                        {!isCustomer && (
                          <>
                            {q.status === "DRAFT" && (
                              <button
                                className="btn-secondary"
                                style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
                                onClick={() => handleSend(q.id)}
                              >
                                Send
                              </button>
                            )}

                            {q.status === "SENT" && (
                              <button
                                className="btn-secondary"
                                style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
                                onClick={() => handleAccept(q.id)}
                              >
                                Accept
                              </button>
                            )}

                            {q.status === "ACCEPTED" && (
                              <button
                                className="btn-primary"
                                style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
                                onClick={() => handleConvert(q.id)}
                              >
                                Convert to subscription
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Generate From Template Modal */}
      {selectedTemplate && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <div className="modal-header">
              <div>
                <h3>Generate Quotation</h3>
                <p className="card-subtitle">Template: {selectedTemplate.name}</p>
              </div>
              <button className="btn-secondary" onClick={() => setSelectedTemplate(null)}>
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateFromTemplate}>
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div>
                  <label style={{ fontSize: "0.8rem", fontWeight: "600", color: "var(--midnight-indigo)" }}>
                    Select Customer Account
                  </label>
                  <select
                    value={selectedCustomerId}
                    onChange={(e) => setSelectedCustomerId(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "0.6rem",
                      borderRadius: "6px",
                      border: "1px solid var(--border)",
                      marginTop: "0.3rem",
                      fontFamily: "var(--font-sans)",
                    }}
                    required
                  >
                    {customers.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.email} ({c.first_name || c.last_name ? `${c.first_name} ${c.last_name}` : "Client"})
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ fontSize: "0.8rem", fontWeight: "600", color: "var(--midnight-indigo)" }}>
                    Notes / Custom Terms
                  </label>
                  <textarea
                    value={quoteNotes}
                    onChange={(e) => setQuoteNotes(e.target.value)}
                    placeholder="Enter any tailored discounts, customer commitments, or onboarding notes..."
                    rows={3}
                    style={{
                      width: "100%",
                      padding: "0.6rem",
                      borderRadius: "6px",
                      border: "1px solid var(--border)",
                      marginTop: "0.3rem",
                      fontFamily: "var(--font-sans)",
                    }}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setSelectedTemplate(null)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? "Generating..." : "Create quotation"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Custom Quote Builder Modal */}
      {showCustomModal && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "680px" }}>
            <div className="modal-header">
              <div>
                <h3>Create Custom Quotation</h3>
                <p className="card-subtitle">Build a bespoke proposal with custom lines and terms</p>
              </div>
              <button className="btn-secondary" onClick={() => setShowCustomModal(false)}>
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateCustom}>
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <label style={{ fontSize: "0.8rem", fontWeight: "600", color: "var(--midnight-indigo)" }}>
                      Customer Account
                    </label>
                    <select
                      value={selectedCustomerId}
                      onChange={(e) => setSelectedCustomerId(e.target.value)}
                      style={{
                        width: "100%",
                        padding: "0.55rem",
                        borderRadius: "6px",
                        border: "1px solid var(--border)",
                        marginTop: "0.3rem",
                      }}
                      required
                    >
                      {customers.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.email}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label style={{ fontSize: "0.8rem", fontWeight: "600", color: "var(--midnight-indigo)" }}>
                      Billing Plan
                    </label>
                    <select
                      value={customPlanId}
                      onChange={(e) => setCustomPlanId(e.target.value)}
                      style={{
                        width: "100%",
                        padding: "0.55rem",
                        borderRadius: "6px",
                        border: "1px solid var(--border)",
                        marginTop: "0.3rem",
                      }}
                    >
                      {availablePlans.length > 0 ? (
                        availablePlans.map((pl) => (
                          <option key={pl.id} value={pl.id}>
                            {pl.name} (₹{Number(pl.price).toFixed(2)}/{pl.billing_period})
                          </option>
                        ))
                      ) : (
                        <>
                          <option value="1">Monthly Starter (₹1,999.00/monthly)</option>
                          <option value="2">Pro Growth (₹4,999.00/monthly)</option>
                          <option value="3">Enterprise Annual (₹49,999.00/yearly)</option>
                        </>
                      )}
                    </select>
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <label style={{ fontSize: "0.8rem", fontWeight: "600", color: "var(--midnight-indigo)" }}>
                      Payment Terms
                    </label>
                    <select
                      value={customTerms}
                      onChange={(e) => setCustomTerms(e.target.value)}
                      style={{
                        width: "100%",
                        padding: "0.55rem",
                        borderRadius: "6px",
                        border: "1px solid var(--border)",
                        marginTop: "0.3rem",
                      }}
                    >
                      <option value="IMMEDIATE">Immediate Payment</option>
                      <option value="NET_15">Net 15 Days</option>
                      <option value="NET_30">Net 30 Days</option>
                      <option value="NET_60">Net 60 Days</option>
                    </select>
                  </div>

                  <div>
                    <label style={{ fontSize: "0.8rem", fontWeight: "600", color: "var(--midnight-indigo)" }}>
                      Validity (Days)
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="180"
                      value={customValidityDays}
                      onChange={(e) => setCustomValidityDays(e.target.value)}
                      style={{
                        width: "100%",
                        padding: "0.55rem",
                        borderRadius: "6px",
                        border: "1px solid var(--border)",
                        marginTop: "0.3rem",
                      }}
                      required
                    />
                  </div>
                </div>

                {/* Dynamic Product Lines */}
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                    <label style={{ fontSize: "0.8rem", fontWeight: "600", color: "var(--midnight-indigo)" }}>
                      Product Lines
                    </label>
                    <button
                      type="button"
                      className="btn-secondary"
                      style={{ fontSize: "0.75rem", padding: "0.25rem 0.5rem" }}
                      onClick={addCustomLine}
                    >
                      + Add Item
                    </button>
                  </div>

                  <table className="data-table" style={{ fontSize: "0.8rem" }}>
                    <thead>
                      <tr>
                        <th>Product</th>
                        <th style={{ width: "70px" }}>Qty</th>
                        <th style={{ width: "90px" }}>Price (₹)</th>
                        <th style={{ width: "80px" }}>Tax (₹)</th>
                        <th style={{ width: "40px" }}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {customLines.map((line, idx) => (
                        <tr key={idx}>
                          <td>
                            <select
                              value={line.product_id}
                              onChange={(e) => {
                                const pId = e.target.value;
                                const prod = availableProducts.find((p) => String(p.id) === String(pId));
                                updateCustomLine(idx, "product_id", pId);
                                if (prod) {
                                  updateCustomLine(idx, "unit_price", prod.sales_price);
                                  updateCustomLine(idx, "taxes", (Number(prod.sales_price) * 0.18).toFixed(2));
                                }
                              }}
                              style={{ width: "100%", padding: "0.3rem" }}
                            >
                              {availableProducts.length > 0 ? (
                                availableProducts.map((p) => (
                                  <option key={p.id} value={p.id}>
                                    {p.name}
                                  </option>
                                ))
                              ) : (
                                <>
                                  <option value="1">Brightloop CRM</option>
                                  <option value="2">Brightloop ERP</option>
                                  <option value="3">Priority Support add-on</option>
                                </>
                              )}
                            </select>
                          </td>
                          <td>
                            <input
                              type="number"
                              min="1"
                              value={line.quantity}
                              onChange={(e) => updateCustomLine(idx, "quantity", e.target.value)}
                              style={{ width: "100%", padding: "0.3rem" }}
                            />
                          </td>
                          <td>
                            <input
                              type="text"
                              value={line.unit_price}
                              onChange={(e) => updateCustomLine(idx, "unit_price", e.target.value)}
                              style={{ width: "100%", padding: "0.3rem" }}
                            />
                          </td>
                          <td>
                            <input
                              type="text"
                              value={line.taxes}
                              onChange={(e) => updateCustomLine(idx, "taxes", e.target.value)}
                              style={{ width: "100%", padding: "0.3rem" }}
                            />
                          </td>
                          <td style={{ textAlign: "center" }}>
                            {customLines.length > 1 && (
                              <button
                                type="button"
                                onClick={() => removeCustomLine(idx)}
                                style={{ background: "none", border: "none", cursor: "pointer", color: "#DC2626" }}
                              >
                                ✕
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div>
                  <label style={{ fontSize: "0.8rem", fontWeight: "600", color: "var(--midnight-indigo)" }}>
                    Proposal Notes
                  </label>
                  <textarea
                    value={quoteNotes}
                    onChange={(e) => setQuoteNotes(e.target.value)}
                    placeholder="Enter any tailored discounts, customer commitments, or onboarding notes..."
                    rows={2}
                    style={{
                      width: "100%",
                      padding: "0.55rem",
                      borderRadius: "6px",
                      border: "1px solid var(--border)",
                      marginTop: "0.3rem",
                      fontFamily: "var(--font-sans)",
                    }}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowCustomModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? "Saving..." : "Create quotation"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Printable/Branded Quotation Preview Modal */}
      {previewQuote && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "620px" }}>
            <div className="modal-header">
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <div className="brand-logo-mark" style={{ width: "28px", height: "28px", fontSize: "0.9rem" }}>
                    B
                  </div>
                  <h3 style={{ margin: 0 }}>Brightloop Quotation</h3>
                </div>
                <p className="card-subtitle" style={{ marginTop: "0.3rem" }}>
                  Reference: <strong>{previewQuote.quotation_number}</strong>
                </p>
              </div>
              <button className="btn-secondary" onClick={() => setPreviewQuote(null)}>
                ✕
              </button>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "1.25rem", fontSize: "0.85rem" }}>
              <div>
                <span style={{ color: "var(--secondary-text)" }}>Client: </span>
                <strong>{previewQuote.customer_email}</strong>
                <br />
                <span style={{ color: "var(--secondary-text)" }}>Plan: </span>
                <span>{previewQuote.plan_name}</span>
              </div>
              <div style={{ textAlign: "right" }}>
                <span style={{ color: "var(--secondary-text)" }}>Valid Until: </span>
                <strong>{previewQuote.valid_until}</strong>
                <br />
                <span style={{ color: "var(--secondary-text)" }}>Payment Terms: </span>
                <span>{previewQuote.payment_terms}</span>
              </div>
            </div>

            <div className="table-responsive">
              <table className="data-table" style={{ fontSize: "0.85rem" }}>
                <thead>
                  <tr>
                    <th>Line Item</th>
                    <th style={{ textAlign: "center" }}>Qty</th>
                    <th style={{ textAlign: "right" }}>Unit Price</th>
                    <th style={{ textAlign: "right" }}>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {previewQuote.lines && previewQuote.lines.length > 0 ? (
                    previewQuote.lines.map((l, i) => (
                      <tr key={i}>
                        <td>
                          {l.product_name}
                          {l.variant_display && <small> ({l.variant_display})</small>}
                        </td>
                        <td style={{ textAlign: "center" }}>{l.quantity}</td>
                        <td style={{ textAlign: "right" }} className="tabular-num">
                          ₹{l.unit_price}
                        </td>
                        <td style={{ textAlign: "right" }} className="tabular-num">
                          ₹{l.amount}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={4} style={{ textAlign: "center", color: "var(--secondary-text)" }}>
                        Standard plan bundle lines
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div
              style={{
                marginTop: "1.25rem",
                padding: "1rem",
                backgroundColor: "var(--soft-vanilla)",
                borderRadius: "8px",
                display: "flex",
                flexDirection: "column",
                gap: "0.4rem",
                textAlign: "right",
              }}
            >
              <div>
                <span style={{ color: "var(--secondary-text)" }}>Subtotal: </span>
                <span className="tabular-num">₹{previewQuote.subtotal}</span>
              </div>
              <div>
                <span style={{ color: "var(--secondary-text)" }}>Taxes (18% GST): </span>
                <span className="tabular-num">₹{previewQuote.tax_amount}</span>
              </div>
              <div style={{ fontSize: "1.1rem", fontWeight: "700", color: "var(--midnight-indigo)" }}>
                <span>Total Quotation Value: </span>
                <span className="tabular-num">₹{previewQuote.total_amount}</span>
              </div>
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setPreviewQuote(null)}>
                Close
              </button>
              {isCustomer && previewQuote.status === "SENT" && (
                <button
                  className="btn-primary"
                  onClick={() => {
                    handleAccept(previewQuote.id);
                    setPreviewQuote(null);
                  }}
                >
                  Accept and sign quote
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
