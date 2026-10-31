import React, { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import {
  getInvoices,
  getInvoice,
  confirmInvoice,
  cancelInvoice,
  generateInvoices,
} from "../api/billing";
import { AlertTriangle, X, CheckCircle2, Tag } from "lucide-react";

/**
 * String-based money formatter: avoids parseFloat and float precision issues.
 * Member 4 contract: Money fields are always strings like "118.00".
 */
function formatMoney(val, prefix = "₹") {
  if (val === null || val === undefined || val === "") return `${prefix}0.00`;
  const str = String(val).trim();
  const isNegative = str.startsWith("-");
  const clean = isNegative ? str.slice(1) : str;
  const parts = clean.split(".");
  const intPart = parts[0] || "0";
  const fracPart = parts[1] || "00";
  const formattedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  let formattedFrac = fracPart;
  if (formattedFrac.length === 1) formattedFrac += "0";
  else if (formattedFrac.length > 2) formattedFrac = formattedFrac.slice(0, 2);
  return `${isNegative ? "-" : ""}${prefix}${formattedInt}.${formattedFrac}`;
}

/**
 * Checks if a string money value is strictly greater than 0 without using parseFloat.
 */
function isNonZero(val) {
  if (!val) return false;
  const s = String(val).trim();
  if (s.startsWith("-")) return false;
  const digits = s.replace(/[^\d]/g, "");
  return parseInt(digits, 10) > 0;
}

/**
 * Parses Member 4 error response shape: { success: false, message, errors }.
 * Handles 409 (illegal status), 400 (validation), 403 (wrong role), 404 (not found).
 */
function formatErrorMessage(err, fallback = "Operation failed.") {
  if (!err) return fallback;
  if (typeof err === "string") return err;
  let msg = err.message || err.detail || "";
  if (err.errors) {
    if (Array.isArray(err.errors)) {
      const details = err.errors.join(", ");
      msg = msg ? `${msg}: ${details}` : details;
    } else if (typeof err.errors === "object") {
      const errParts = Object.entries(err.errors).map(
        ([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : v}`
      );
      const details = errParts.join("; ");
      msg = msg ? `${msg} (${details})` : details;
    }
  }
  return msg || fallback;
}

export default function InvoicesView({ onNavigate }) {
  const { user } = useAuth();
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedInvoice, setSelectedInvoice] = useState(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [amountsChangedNotice, setAmountsChangedNotice] = useState(null);
  const [actionNotice, setActionNotice] = useState(null);
  const [errorNotice, setErrorNotice] = useState(null);
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [generateTargetDate, setGenerateTargetDate] = useState(
    new Date().toISOString().split("T")[0]
  );
  const [generating, setGenerating] = useState(false);

  const role = user?.role || "GUEST";
  const isCustomer = role === "CUSTOMER";
  const isStaff = role === "STAFF" || role === "ADMIN";

  // Fetch invoices from Member 4's GET /api/billing/invoices/
  // Response shape: list = { count, next, previous, results }
  // Server filters by role - NO client-side customer filtering.
  async function fetchInvoices() {
    setLoading(true);
    setErrorNotice(null);
    try {
      const params = {};
      if (statusFilter !== "all") params.status = statusFilter;
      if (searchQuery.trim()) params.search = searchQuery.trim();

      const res = await getInvoices(params);
      const dataList =
        res?.results ?? (Array.isArray(res) ? res : (res?.data?.results ?? res?.data ?? []));
      setInvoices(Array.isArray(dataList) ? dataList : []);
    } catch (err) {
      console.error("Failed to fetch invoices:", err);
      setErrorNotice(formatErrorMessage(err, "Failed to load invoices from server."));
      setInvoices([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchInvoices();
  }, [statusFilter]);

  // Open invoice detail with lines[] and discounts[]: GET /api/billing/invoices/{id}/
  // Response shape: detail = plain object
  async function handleViewInvoice(inv) {
    setErrorNotice(null);
    try {
      const res = await getInvoice(inv.id);
      const detail = res?.data?.id ? res.data : (res?.id ? res : inv);
      setSelectedInvoice(detail);
    } catch (err) {
      console.error("Failed to view invoice detail:", err);
      setErrorNotice(formatErrorMessage(err, "Failed to load invoice details."));
      setSelectedInvoice(inv);
    }
  }

  // Confirm draft invoice: POST /api/billing/invoices/{id}/confirm/
  // Response shape: confirm = { success, message, data: { invoice, amounts_changed } }
  // Critical: Read res.data.invoice, not res.data
  async function handleConfirmInvoice(invoiceId) {
    setActionNotice(null);
    setErrorNotice(null);
    try {
      const res = await confirmInvoice(invoiceId);
      // Member 4 contract: res.data = { invoice, amounts_changed }
      const updatedInvoice = res?.data?.invoice || (res?.data?.id ? res.data : {});
      const amountsChanged = Boolean(res?.data?.amounts_changed);

      if (amountsChanged) {
        setAmountsChangedNotice(
          "Notice: Invoice amounts changed during confirmation because an applied discount expired or became unavailable. The invoice has been re-priced."
        );
      } else {
        setActionNotice(res?.message || "Invoice successfully confirmed.");
      }

      setInvoices((prev) =>
        prev.map((i) =>
          i.id === invoiceId
            ? { ...i, status: "confirmed", ...updatedInvoice }
            : i
        )
      );

      if (selectedInvoice && selectedInvoice.id === invoiceId) {
        setSelectedInvoice((prev) => ({
          ...prev,
          status: "confirmed",
          ...updatedInvoice,
        }));
      }
    } catch (err) {
      console.error("Confirm invoice error:", err);
      setErrorNotice(formatErrorMessage(err, "Failed to confirm invoice."));
    }
  }

  // Cancel invoice: POST /api/billing/invoices/{id}/cancel/
  // Response shape: cancel = { success, message, data: <invoice> }
  async function handleCancelInvoice(invoice) {
    if (isNonZero(invoice.amount_paid)) {
      setErrorNotice(
        "Cancellation blocked: Payments have already been recorded against this invoice (HTTP 409)."
      );
      return;
    }

    setActionNotice(null);
    setErrorNotice(null);
    try {
      const res = await cancelInvoice(invoice.id);
      const updatedInvoice = res?.data || {};
      const msg = res?.message || `Invoice ${invoice.number} cancelled.`;
      setActionNotice(msg);
      setInvoices((prev) =>
        prev.map((i) =>
          i.id === invoice.id
            ? { ...i, status: "cancelled", outstanding: "0.00", ...updatedInvoice }
            : i
        )
      );
      if (selectedInvoice && selectedInvoice.id === invoice.id) {
        setSelectedInvoice((prev) => ({
          ...prev,
          status: "cancelled",
          outstanding: "0.00",
          ...updatedInvoice,
        }));
      }
    } catch (err) {
      console.error("Cancel invoice error:", err);
      setErrorNotice(formatErrorMessage(err, `Failed to cancel invoice ${invoice.number}.`));
    }
  }

  // Generate invoices for target date: POST /api/billing/invoices/generate/
  // Response shape: generate = { success, message, data: { created, skipped_existing, advanced, capped, errors } }
  async function handleGenerateInvoices(e) {
    e.preventDefault();
    setGenerating(true);
    setActionNotice(null);
    setErrorNotice(null);
    try {
      const res = await generateInvoices({ target_date: generateTargetDate });
      const stats = res?.data;
      let summary = res?.message || "Billing cycle executed successfully.";
      if (stats && typeof stats.created === "number") {
        summary = `Generation complete: ${stats.created} invoice(s) created, ${stats.advanced ?? 0} subscription(s) advanced.`;
        if (stats.skipped_existing) summary += ` (${stats.skipped_existing} up to date)`;
        if (stats.capped) summary += ` (${stats.capped} capped)`;
        if (stats.errors && stats.errors.length > 0) {
          summary += ` [${stats.errors.length} error(s)]`;
        }
      }
      setActionNotice(`✓ ${summary}`);
      setShowGenerateModal(false);
      fetchInvoices();
    } catch (err) {
      console.error("Generate invoices error:", err);
      setErrorNotice(formatErrorMessage(err, "Failed to generate invoices."));
      setShowGenerateModal(false);
    } finally {
      setGenerating(false);
    }
  }

  // Server filters by role. Client only applies status and search filters on the fetched list.
  const displayedInvoices = invoices.filter((inv) => {
    if (statusFilter !== "all" && inv.status !== statusFilter) {
      return false;
    }
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      const matchNumber = (inv.number || "").toLowerCase().includes(query);
      const matchCustomer = (inv.customer || "").toLowerCase().includes(query);
      if (!matchNumber && !matchCustomer) return false;
    }
    return true;
  });

  return (
    <div className="view-container">
      {/* View Header */}
      <div className="view-header">
        <div>
          <h2>{isCustomer ? "My Invoices" : "Invoices & Billing Statements"}</h2>
          <p>
            {isCustomer
              ? "Review your recurring billing statements, tax breakdowns, and payment status."
              : "Invoice lifecycle records generated by the billing engine."}
          </p>
        </div>
        {/* Staff-only actions */}
        {isStaff && (
          <div className="header-actions">
            <button
              className="btn-primary"
              onClick={() => setShowGenerateModal(true)}
            >
              Generate invoices
            </button>
            <button
              className="btn-secondary"
              onClick={() => onNavigate("billing-hook")}
            >
              Billing simulator
            </button>
          </div>
        )}
      </div>

      {/* Critical Notice: Amounts Changed Banner */}
      {amountsChangedNotice && (
        <div
          className="notice-banner"
          style={{
            backgroundColor: "var(--color-status-pending-bg)",
            borderColor: "var(--color-status-pending-text)",
            color: "var(--color-status-pending-text)",
            marginBottom: "1rem",
            padding: "1rem 1.25rem",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--color-status-pending-text)",
            fontWeight: "600",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
            <AlertTriangle size={18} />
            <span>{amountsChangedNotice}</span>
          </span>
          <button
            className="btn-secondary"
            style={{ padding: "0.25rem 0.6rem", fontSize: "0.8rem" }}
            onClick={() => setAmountsChangedNotice(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Error Notice Banner */}
      {errorNotice && (
        <div
          className="notice-banner"
          style={{
            backgroundColor: "var(--color-status-overdue-bg)",
            borderColor: "var(--color-status-overdue-text)",
            color: "var(--color-status-overdue-text)",
            marginBottom: "1rem",
            padding: "0.75rem 1rem",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--color-status-overdue-text)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
            <AlertTriangle size={18} />
            <span>{errorNotice}</span>
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
            onClick={() => setErrorNotice(null)}
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* Action Notification */}
      {actionNotice && (
        <div
          className="notice-banner"
          style={{
            backgroundColor: "var(--color-muted)",
            borderColor: "var(--color-border)",
            color: "var(--color-text-primary)",
            marginBottom: "1rem",
            padding: "0.75rem 1rem",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--color-border)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
            <CheckCircle2 size={16} style={{ color: "var(--color-status-active-text)" }} />
            <span>{actionNotice}</span>
          </span>
          <button
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "var(--color-text-secondary)",
              display: "flex",
              alignItems: "center",
            }}
            onClick={() => setActionNotice(null)}
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div
        className="card"
        style={{
          marginBottom: "1.25rem",
          padding: "0.75rem 1rem",
          display: "flex",
          flexWrap: "wrap",
          gap: "1rem",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <span style={{ fontSize: "var(--font-size-small)", color: "var(--color-text-secondary)", fontWeight: 500 }}>
            Status:
          </span>
          {["all", "draft", "confirmed", "paid", "cancelled"].map((st) => (
            <button
              key={st}
              className={`chip ${statusFilter === st ? "chip-active" : ""}`}
              onClick={() => setStatusFilter(st)}
              style={{
                textTransform: "capitalize",
                padding: "4px 12px",
                borderRadius: "var(--radius-full)",
                border: "1px solid var(--color-border)",
                background: statusFilter === st ? "var(--color-midnight-indigo)" : "transparent",
                color: statusFilter === st ? "#FFFFFF" : "var(--color-text-primary)",
                fontSize: "var(--font-size-small)",
                cursor: "pointer",
              }}
            >
              {st}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <input
            type="text"
            placeholder="Search by invoice # or customer..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              padding: "6px 12px",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--color-border)",
              fontSize: "var(--font-size-body)",
              width: "260px",
            }}
          />
          {searchQuery && (
            <button
              className="btn-secondary"
              style={{ padding: "6px 10px", fontSize: "0.8rem" }}
              onClick={() => setSearchQuery("")}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Invoices Data Table */}
      <div className="card">
        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Invoice #</th>
                <th>Customer</th>
                <th>Period</th>
                <th>Due Date</th>
                <th>Status</th>
                <th style={{ textAlign: "right" }}>Total</th>
                <th style={{ textAlign: "right" }}>Paid</th>
                <th style={{ textAlign: "right" }}>Outstanding</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: "center", padding: "2rem" }}>
                    Loading invoices...
                  </td>
                </tr>
              ) : displayedInvoices.length === 0 ? (
                <tr>
                  <td
                    colSpan={9}
                    style={{ textAlign: "center", padding: "2.5rem 1rem", color: "var(--color-text-secondary)" }}
                  >
                    <div style={{ fontWeight: 600, fontSize: "1rem", marginBottom: "0.25rem", color: "var(--color-text-primary)" }}>
                      No invoices found
                    </div>
                    <div style={{ fontSize: "var(--font-size-small)" }}>
                      {isStaff
                        ? "No invoices generated yet. Click 'Generate invoices' to run a billing cycle."
                        : "No invoices available for your account yet."}
                    </div>
                  </td>
                </tr>
              ) : (
                displayedInvoices.map((inv) => (
                  <tr key={inv.id}>
                    <td>
                      <strong>{inv.number}</strong>
                    </td>
                    <td>{inv.customer || inv.customer_email || "N/A"}</td>
                    <td style={{ fontSize: "var(--font-size-small)" }}>
                      {inv.period_start} to {inv.period_end}
                    </td>
                    <td>
                      <span>{inv.due_date}</span>
                      {inv.is_overdue && inv.status !== "paid" && (
                        <span
                          style={{
                            marginLeft: "6px",
                            fontSize: "10px",
                            padding: "1px 6px",
                            borderRadius: "var(--radius-full)",
                            backgroundColor: "var(--color-status-overdue-bg)",
                            color: "var(--color-status-overdue-text)",
                            fontWeight: 600,
                          }}
                        >
                          OVERDUE
                        </span>
                      )}
                    </td>
                    <td>
                      <span className={`status-badge status-${inv.status}`}>
                        {inv.status}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }} className="tabular-num">
                      <strong>{formatMoney(inv.total)}</strong>
                    </td>
                    <td style={{ textAlign: "right" }} className="tabular-num">
                      {formatMoney(inv.amount_paid)}
                    </td>
                    <td style={{ textAlign: "right" }} className="tabular-num">
                      <strong
                        style={{
                          color: isNonZero(inv.outstanding)
                            ? "var(--color-status-overdue-text)"
                            : "inherit",
                        }}
                      >
                        {formatMoney(inv.outstanding)}
                      </strong>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <div style={{ display: "inline-flex", gap: "4px" }}>
                        <button
                          className="btn-secondary"
                          style={{ padding: "0.35rem 0.65rem", fontSize: "0.8rem" }}
                          onClick={() => handleViewInvoice(inv)}
                        >
                          View
                        </button>

                        {/* Staff actions on table row */}
                        {isStaff && inv.status === "draft" && (
                          <button
                            className="btn-primary"
                            style={{ padding: "0.35rem 0.65rem", fontSize: "0.8rem" }}
                            onClick={() => handleConfirmInvoice(inv.id)}
                          >
                            Confirm
                          </button>
                        )}

                        {isStaff && (inv.status === "draft" || inv.status === "confirmed") && (
                          <button
                            className="btn-secondary"
                            style={{
                              padding: "0.35rem 0.65rem",
                              fontSize: "0.8rem",
                              color: "var(--color-status-overdue-text)",
                            }}
                            disabled={isNonZero(inv.amount_paid)}
                            title={
                              isNonZero(inv.amount_paid)
                                ? "Cannot cancel invoice with recorded payments"
                                : "Cancel invoice"
                            }
                            onClick={() => handleCancelInvoice(inv)}
                          >
                            Cancel
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Invoice Details Modal */}
      {selectedInvoice && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "680px" }}>
            <div className="modal-header">
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <h3 style={{ margin: 0 }}>{selectedInvoice.number}</h3>
                  <span className={`status-badge status-${selectedInvoice.status}`}>
                    {selectedInvoice.status}
                  </span>
                  {selectedInvoice.is_overdue && selectedInvoice.status !== "paid" && (
                    <span
                      style={{
                        fontSize: "11px",
                        padding: "1px 6px",
                        borderRadius: "var(--radius-full)",
                        backgroundColor: "var(--color-status-overdue-bg)",
                        color: "var(--color-status-overdue-text)",
                        fontWeight: 600,
                      }}
                    >
                      OVERDUE
                    </span>
                  )}
                </div>
                <p className="card-subtitle" style={{ marginTop: "4px" }}>
                  Customer: <strong>{selectedInvoice.customer || selectedInvoice.customer_email || "N/A"}</strong> • Subscription:{" "}
                  <strong>{selectedInvoice.subscription_id || selectedInvoice.subscription || "N/A"}</strong>
                </p>
              </div>
              <button
                className="btn-secondary"
                style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", padding: "6px" }}
                onClick={() => setSelectedInvoice(null)}
              >
                <X size={16} />
              </button>
            </div>

            {/* In-Modal Notice Banner if amounts changed */}
            {amountsChangedNotice && (
              <div
                style={{
                  padding: "0.75rem 1rem",
                  backgroundColor: "var(--color-status-pending-bg)",
                  border: "1px solid var(--color-status-pending-text)",
                  borderRadius: "var(--radius-sm)",
                  color: "var(--color-status-pending-text)",
                  fontSize: "var(--font-size-small)",
                  fontWeight: 600,
                  marginBottom: "1rem",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                }}
              >
                <AlertTriangle size={18} style={{ flexShrink: 0 }} />
                <span>{amountsChangedNotice}</span>
              </div>
            )}

            {/* Invoice Meta Grid */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(3, 1fr)",
                gap: "0.75rem",
                padding: "0.75rem",
                backgroundColor: "var(--color-muted)",
                borderRadius: "var(--radius-md)",
                marginBottom: "1rem",
                fontSize: "var(--font-size-small)",
              }}
            >
              <div>
                <span style={{ color: "var(--color-text-secondary)" }}>Issue Date:</span>
                <div><strong>{selectedInvoice.issue_date || "—"}</strong></div>
              </div>
              <div>
                <span style={{ color: "var(--color-text-secondary)" }}>Due Date:</span>
                <div><strong>{selectedInvoice.due_date || "—"}</strong></div>
              </div>
              <div>
                <span style={{ color: "var(--color-text-secondary)" }}>Period:</span>
                <div>
                  <strong>
                    {selectedInvoice.period_start || "—"} to {selectedInvoice.period_end || "—"}
                  </strong>
                </div>
              </div>
            </div>

            {/* Discounts List (from Member 4's detail shape: discounts[]) */}
            {Array.isArray(selectedInvoice.discounts) && selectedInvoice.discounts.length > 0 && (
              <div style={{ marginBottom: "1rem" }}>
                <h4
                  style={{
                    fontSize: "var(--font-size-small)",
                    fontWeight: 600,
                    color: "var(--color-text-secondary)",
                    marginBottom: "0.5rem",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  <Tag size={14} /> Applied Discounts
                </h4>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                  {selectedInvoice.discounts.map((disc, idx) => (
                    <span
                      key={disc.id || idx}
                      className="chip"
                      style={{
                        backgroundColor: "var(--color-status-confirmed-bg)",
                        color: "var(--color-status-confirmed-text)",
                        border: "1px solid var(--color-border)",
                        padding: "4px 10px",
                        fontSize: "var(--font-size-small)",
                        borderRadius: "var(--radius-sm)",
                      }}
                    >
                      {disc.name || disc.code || "Discount"}
                      {disc.amount && ` (-${formatMoney(disc.amount)})`}
                      {disc.percent && ` (${disc.percent}%)`}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Line Items Table */}
            <div style={{ marginBottom: "1rem" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Product / Line Item</th>
                    <th style={{ textAlign: "center" }}>Qty</th>
                    <th style={{ textAlign: "right" }}>Unit Price</th>
                    <th style={{ textAlign: "right" }}>Discount</th>
                    <th style={{ textAlign: "right" }}>Tax</th>
                    <th style={{ textAlign: "right" }}>Line Total</th>
                  </tr>
                </thead>
                <tbody>
                  {(selectedInvoice.lines || []).map((l, i) => (
                    <tr key={l.id || i}>
                      <td>{l.product_name || l.desc || "Item"}</td>
                      <td style={{ textAlign: "center" }}>{l.quantity || l.qty}</td>
                      <td style={{ textAlign: "right" }} className="tabular-num">
                        {formatMoney(l.unit_price)}
                      </td>
                      <td style={{ textAlign: "right" }} className="tabular-num">
                        {formatMoney(l.discount_amount)}
                      </td>
                      <td style={{ textAlign: "right" }} className="tabular-num">
                        {formatMoney(l.tax_amount)}
                      </td>
                      <td style={{ textAlign: "right" }} className="tabular-num">
                        <strong>{formatMoney(l.line_total || l.total)}</strong>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Financial Summary */}
            <div
              style={{
                padding: "1rem",
                backgroundColor: "var(--color-muted)",
                borderRadius: "var(--radius-md)",
                display: "flex",
                flexDirection: "column",
                gap: "0.4rem",
                textAlign: "right",
                fontSize: "var(--font-size-body)",
              }}
            >
              <div>
                <span style={{ color: "var(--color-text-secondary)" }}>Subtotal: </span>
                <span className="tabular-num">{formatMoney(selectedInvoice.subtotal)}</span>
              </div>
              <div>
                <span style={{ color: "var(--color-text-secondary)" }}>Discount Total: </span>
                <span className="tabular-num">-{formatMoney(selectedInvoice.discount_total)}</span>
              </div>
              <div>
                <span style={{ color: "var(--color-text-secondary)" }}>Tax Total: </span>
                <span className="tabular-num">+{formatMoney(selectedInvoice.tax_total)}</span>
              </div>
              <div
                style={{
                  fontSize: "1.1rem",
                  fontWeight: 700,
                  color: "var(--color-midnight-indigo)",
                  paddingTop: "0.25rem",
                  borderTop: "1px solid var(--color-border)",
                }}
              >
                <span>Total Amount: </span>
                <span className="tabular-num">{formatMoney(selectedInvoice.total)}</span>
              </div>
              <div>
                <span style={{ color: "var(--color-text-secondary)" }}>Amount Paid: </span>
                <span className="tabular-num">{formatMoney(selectedInvoice.amount_paid)}</span>
              </div>
              <div
                style={{
                  fontWeight: 600,
                  color: isNonZero(selectedInvoice.outstanding)
                    ? "var(--color-status-overdue-text)"
                    : "var(--color-status-active-text)",
                }}
              >
                <span>Outstanding Balance: </span>
                <span className="tabular-num">{formatMoney(selectedInvoice.outstanding)}</span>
              </div>
            </div>

            {/* Modal Footer Actions */}
            <div className="modal-footer" style={{ marginTop: "1.25rem" }}>
              <button className="btn-secondary" onClick={() => setSelectedInvoice(null)}>
                Close
              </button>

              {/* Staff Actions inside modal */}
              {isStaff && selectedInvoice.status === "draft" && (
                <button
                  className="btn-primary"
                  onClick={() => handleConfirmInvoice(selectedInvoice.id)}
                >
                  Confirm invoice
                </button>
              )}

              {isStaff &&
                (selectedInvoice.status === "draft" || selectedInvoice.status === "confirmed") && (
                  <button
                    className="btn-secondary"
                    style={{ color: "var(--color-status-overdue-text)" }}
                    disabled={isNonZero(selectedInvoice.amount_paid)}
                    title={
                      isNonZero(selectedInvoice.amount_paid)
                        ? "Cannot cancel invoice with recorded payments"
                        : "Cancel invoice"
                    }
                    onClick={() => handleCancelInvoice(selectedInvoice)}
                  >
                    Cancel invoice
                  </button>
                )}

              {/* Customer Quick Pay */}
              {isCustomer &&
                selectedInvoice.status !== "paid" &&
                selectedInvoice.status !== "cancelled" && (
                  <button
                    className="btn-primary"
                    onClick={() => {
                      alert(
                        `Payment initiated for invoice ${selectedInvoice.number} (${formatMoney(selectedInvoice.outstanding)}). In live mode, this connects to Member 4's /api/payments/ endpoint.`
                      );
                      setSelectedInvoice(null);
                    }}
                  >
                    Pay invoice now ({formatMoney(selectedInvoice.outstanding)})
                  </button>
                )}
            </div>
          </div>
        </div>
      )}

      {/* Staff Generate Invoices Modal */}
      {showGenerateModal && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "460px" }}>
            <div className="modal-header">
              <div>
                <h3>Generate Billing Invoices</h3>
                <p className="card-subtitle">
                  Run billing automation for all active subscriptions due on or before target date.
                </p>
              </div>
              <button
                className="btn-secondary"
                style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", padding: "6px" }}
                onClick={() => setShowGenerateModal(false)}
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleGenerateInvoices}>
              <div style={{ marginBottom: "1.25rem" }}>
                <label
                  style={{
                    display: "block",
                    fontSize: "var(--font-size-small)",
                    fontWeight: 500,
                    marginBottom: "6px",
                  }}
                >
                  Target Billing Date:
                </label>
                <input
                  type="date"
                  required
                  value={generateTargetDate}
                  onChange={(e) => setGenerateTargetDate(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    borderRadius: "var(--radius-sm)",
                    border: "1px solid var(--color-border)",
                    fontSize: "var(--font-size-body)",
                  }}
                />
                <small style={{ color: "var(--color-text-secondary)", display: "block", marginTop: "4px" }}>
                  Calls Member 4's endpoint: <code>POST /api/billing/invoices/generate/</code>
                </small>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowGenerateModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={generating}
                >
                  {generating ? "Running billing..." : "Run generation"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
