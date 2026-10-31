import { useState, useEffect } from "react";
import {
  getTaxes,
  createTax,
  updateTax,
  deactivateTax,
} from "../../api/catalogAdmin";
import { useAuth } from "../../context/AuthContext";
import { formatCurrency } from "../../utils/formatters";
import "./catalog.css";

const INITIAL_FORM = {
  name: "",
  kind: "percent",
  rate: "",
  is_active: true,
};

export default function TaxesAdmin() {
  const { user, isAdmin } = useAuth();
  const userRole = (user?.data || user)?.role;
  const hasAdminAccess = Boolean(isAdmin || userRole === "ADMIN");
  const isCustomer = userRole === "CUSTOMER";

  // Table & Data State
  const [taxes, setTaxes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tableError, setTableError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  // Filters
  const [filterActive, setFilterActive] = useState("");
  const [searchName, setSearchName] = useState("");

  // Pagination
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [totalCount, setTotalCount] = useState(0);

  // Form Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(INITIAL_FORM);
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});
  const [formGeneralError, setFormGeneralError] = useState("");

  // Load Taxes with filters & pagination
  useEffect(() => {
    let ignore = false;
    if (isCustomer) return;

    async function fetchTaxes() {
      try {
        const params = {
          page,
          page_size: pageSize,
        };

        if (filterActive !== "") params.is_active = filterActive;
        if (searchName.trim()) params.search = searchName.trim();

        const res = await getTaxes(params);
        if (!ignore) {
          const items = res.results || (Array.isArray(res) ? res : []);
          setTaxes(items);
          setTotalCount(typeof res.count === "number" ? res.count : items.length);
          setTableError("");
          setLoading(false);
        }
      } catch (err) {
        if (!ignore) {
          console.error("Failed to load taxes", err);
          setTableError(err?.message || "Failed to load taxes from catalog API.");
          setLoading(false);
        }
      }
    }

    fetchTaxes();

    return () => {
      ignore = true;
    };
  }, [page, pageSize, filterActive, searchName, refreshTrigger, isCustomer]);

  function triggerRefresh() {
    setRefreshTrigger((prev) => prev + 1);
  }

  function handleFilterActiveChange(val) {
    setFilterActive(val);
    setPage(1);
  }

  function handleSearchChange(val) {
    setSearchName(val);
    setPage(1);
  }

  function handleResetFilters() {
    setFilterActive("");
    setSearchName("");
    setPage(1);
  }

  // Open Create Modal
  function handleOpenCreate() {
    setIsEditing(false);
    setEditingId(null);
    setForm(INITIAL_FORM);
    setFieldErrors({});
    setFormGeneralError("");
    setIsModalOpen(true);
  }

  // Open Edit Modal
  function handleOpenEdit(tax) {
    setIsEditing(true);
    setEditingId(tax.id);
    setForm({
      name: tax.name || "",
      kind: tax.kind || "percent",
      rate: tax.rate || "",
      is_active: tax.is_active ?? true,
    });
    setFieldErrors({});
    setFormGeneralError("");
    setIsModalOpen(true);
  }

  function updateFormField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
    if (fieldErrors[field]) {
      setFieldErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  }

  // Form Submit Handler
  async function handleSaveTax(e) {
    e.preventDefault();
    setSaving(true);
    setFieldErrors({});
    setFormGeneralError("");
    setSuccessMessage("");

    const payload = {
      name: form.name.trim(),
      kind: form.kind,
      rate: form.rate,
      is_active: Boolean(form.is_active),
    };

    try {
      if (isEditing) {
        await updateTax(editingId, payload);
        setSuccessMessage(`Tax rule "${payload.name}" updated successfully.`);
      } else {
        await createTax(payload);
        setSuccessMessage(`Tax rule "${payload.name}" created successfully.`);
      }
      setIsModalOpen(false);
      triggerRefresh();
    } catch (err) {
      console.error("Save tax failed", err);
      if (err && typeof err === "object") {
        if (err.errors) {
          setFieldErrors(err.errors);
          if (err.errors.non_field_errors) {
            setFormGeneralError(
              Array.isArray(err.errors.non_field_errors)
                ? err.errors.non_field_errors.join(" ")
                : String(err.errors.non_field_errors)
            );
          } else if (err.message && err.message !== "Request failed") {
            setFormGeneralError(err.message);
          }
        } else if (err.detail) {
          setFormGeneralError(err.detail);
        } else if (err.message) {
          setFormGeneralError(err.message);
        } else {
          setFieldErrors(err);
        }
      } else {
        setFormGeneralError("An unexpected error occurred while saving tax rule.");
      }
    } finally {
      setSaving(false);
    }
  }

  // Deactivate Handler
  async function handleDeactivate(tax) {
    const ok = window.confirm(
      `Are you sure you want to deactivate tax "${tax.name}"?`
    );
    if (!ok) return;

    setTableError("");
    setSuccessMessage("");
    try {
      const res = await deactivateTax(tax.id);
      setSuccessMessage(res?.message || `Tax rule "${tax.name}" deactivated.`);
      triggerRefresh();
    } catch (err) {
      console.error("Deactivate tax failed", err);
      setTableError(
        err?.message || err?.detail || `Failed to deactivate tax "${tax.name}".`
      );
    }
  }

  // Customer Access Denied View
  if (isCustomer) {
    return (
      <div className="cat-container">
        <div className="cat-alert-error">
          Access denied. Tax rule configuration is restricted to staff and administrators.
        </div>
      </div>
    );
  }

  // Pagination Math
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const startIndex = totalCount === 0 ? 0 : (page - 1) * pageSize + 1;
  const endIndex = Math.min(totalCount, page * pageSize);

  return (
    <div className="cat-container">
      {/* Header */}
      <div className="cat-header">
        <div className="cat-title-group">
          <h2 className="cat-title">Tax Rates & Rules</h2>
          <p className="cat-subtitle">
            Configure percentage and fixed rate tax rules applied during invoice line pricing.
          </p>
        </div>

        <div className="cat-actions-group">
          {hasAdminAccess && (
            <button
              type="button"
              className="cat-btn cat-btn-primary"
              onClick={handleOpenCreate}
            >
              <span>+ New Tax</span>
            </button>
          )}
        </div>
      </div>

      {/* Alert Messages */}
      {successMessage && (
        <div className="cat-alert-success">
          {successMessage}
        </div>
      )}

      {tableError && (
        <div className="cat-alert-error">
          {tableError}
        </div>
      )}

      {/* Filter Toolbar */}
      <div className="cat-filter-card">
        <div className="cat-filter-row">
          <div className="cat-filter-group">
            <label className="cat-filter-label" htmlFor="cat-filter-search-tax">
              Search Tax Name
            </label>
            <input
              id="cat-filter-search-tax"
              type="text"
              className="cat-filter-input"
              placeholder="e.g. GST 18%, VAT..."
              value={searchName}
              onChange={(e) => handleSearchChange(e.target.value)}
            />
          </div>

          <div className="cat-filter-group">
            <label className="cat-filter-label" htmlFor="cat-filter-active-tax">
              Status
            </label>
            <select
              id="cat-filter-active-tax"
              className="cat-filter-select"
              value={filterActive}
              onChange={(e) => handleFilterActiveChange(e.target.value)}
            >
              <option value="">All Statuses</option>
              <option value="true">Active Only</option>
              <option value="false">Inactive Only</option>
            </select>
          </div>

          {(filterActive !== "" || searchName) && (
            <div className="cat-filter-group cat-filter-group-action">
              <button
                type="button"
                className="cat-btn cat-btn-secondary"
                onClick={handleResetFilters}
              >
                Clear Filters
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Taxes Table */}
      <div className="cat-table-card">
        {loading ? (
          <div className="cat-loading-state">Loading tax rules from catalog API...</div>
        ) : taxes.length === 0 ? (
          <div className="cat-empty-state">
            No tax rules match the selected filter criteria.
          </div>
        ) : (
          <div className="cat-table-responsive">
            <table className="cat-table">
              <thead>
                <tr>
                  <th className="cat-th">Tax Name</th>
                  <th className="cat-th">Kind</th>
                  <th className="cat-th">Rate / Amount</th>
                  <th className="cat-th">Status</th>
                  {hasAdminAccess && <th className="cat-th" style={{ textAlign: "right" }}>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {taxes.map((t) => {
                  const isPercent = t.kind === "percent";
                  const displayRate = isPercent
                    ? `${Number(t.rate)}%`
                    : formatCurrency(t.rate);

                  return (
                    <tr key={t.id}>
                      <td className="cat-td">
                        <strong>{t.name}</strong>
                      </td>
                      <td className="cat-td">
                        <span className="cat-chip">
                          {isPercent ? "Percentage (%)" : "Fixed Amount"}
                        </span>
                      </td>
                      <td className="cat-td cat-tabular-num">
                        <strong>{displayRate}</strong>
                      </td>
                      <td className="cat-td">
                        <span
                          className={`cat-badge ${
                            t.is_active ? "cat-badge-active" : "cat-badge-inactive"
                          }`}
                        >
                          {t.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      {hasAdminAccess && (
                        <td className="cat-td" style={{ textAlign: "right" }}>
                          <div className="cat-actions-cell" style={{ justifyContent: "flex-end" }}>
                            <button
                              type="button"
                              className="cat-btn cat-btn-secondary cat-btn-sm"
                              onClick={() => handleOpenEdit(t)}
                            >
                              Edit
                            </button>
                            {t.is_active && (
                              <button
                                type="button"
                                className="cat-btn cat-btn-danger cat-btn-sm"
                                onClick={() => handleDeactivate(t)}
                              >
                                Deactivate
                              </button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Controls */}
        <div className="cat-pagination">
          <div className="cat-pagination-info">
            Showing {startIndex} to {endIndex} of {totalCount} tax rules
          </div>

          <div className="cat-pagination-controls">
            <label htmlFor="cat-tax-page-size" style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>
              Per Page:
            </label>
            <select
              id="cat-tax-page-size"
              className="cat-filter-select"
              style={{ width: "auto", padding: "4px 8px", fontSize: "12px" }}
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
            >
              <option value="10">10</option>
              <option value="20">20</option>
              <option value="50">50</option>
            </select>

            <button
              type="button"
              className="cat-btn cat-btn-secondary cat-btn-sm"
              disabled={page <= 1}
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
            >
              ‹ Prev
            </button>
            <span style={{ fontSize: "13px", padding: "0 6px" }}>
              Page {page} of {totalPages}
            </span>
            <button
              type="button"
              className="cat-btn cat-btn-secondary cat-btn-sm"
              disabled={page >= totalPages}
              onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
            >
              Next ›
            </button>
          </div>
        </div>
      </div>

      {/* Create / Edit Tax Modal */}
      {isModalOpen && (
        <div className="cat-modal-overlay" onClick={() => setIsModalOpen(false)}>
          <div
            className="cat-modal-card"
            style={{ maxWidth: "520px" }}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className="cat-modal-header">
              <h3 className="cat-modal-title">
                {isEditing ? `Edit Tax Rule: ${form.name}` : "Create New Tax Rule"}
              </h3>
              <button
                type="button"
                className="cat-modal-close"
                onClick={() => setIsModalOpen(false)}
                aria-label="Close"
              >
                ×
              </button>
            </div>

            <form onSubmit={handleSaveTax}>
              <div className="cat-modal-body">
                {formGeneralError && (
                  <div className="cat-alert-error">
                    {formGeneralError}
                  </div>
                )}

                <div className="cat-form-grid" style={{ gridTemplateColumns: "1fr" }}>
                  {/* Name */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-tax-field-name">
                      Tax Name *
                    </label>
                    <input
                      id="cat-tax-field-name"
                      type="text"
                      className={`cat-form-input ${fieldErrors.name ? "cat-input-has-error" : ""}`}
                      placeholder="e.g. GST 18%, VAT 5%..."
                      value={form.name}
                      onChange={(e) => updateFormField("name", e.target.value)}
                      required
                    />
                    {fieldErrors.name && (
                      <div className="cat-field-error">
                        {Array.isArray(fieldErrors.name)
                          ? fieldErrors.name.join(" ")
                          : fieldErrors.name}
                      </div>
                    )}
                  </div>

                  {/* Kind */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-tax-field-kind">
                      Tax Kind *
                    </label>
                    <select
                      id="cat-tax-field-kind"
                      className={`cat-form-select ${fieldErrors.kind ? "cat-input-has-error" : ""}`}
                      value={form.kind}
                      onChange={(e) => updateFormField("kind", e.target.value)}
                    >
                      <option value="percent">Percentage (%)</option>
                      <option value="fixed">Fixed Amount (₹)</option>
                    </select>
                    {fieldErrors.kind && (
                      <div className="cat-field-error">
                        {Array.isArray(fieldErrors.kind)
                          ? fieldErrors.kind.join(" ")
                          : fieldErrors.kind}
                      </div>
                    )}
                  </div>

                  {/* Rate */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-tax-field-rate">
                      Tax Rate / Value * {form.kind === "percent" ? "(0 to 100%)" : "(Fixed amount in ₹)"}
                    </label>
                    <input
                      id="cat-tax-field-rate"
                      type="number"
                      step="0.01"
                      min="0"
                      className={`cat-form-input ${fieldErrors.rate ? "cat-input-has-error" : ""}`}
                      placeholder={form.kind === "percent" ? "18.00" : "50.00"}
                      value={form.rate}
                      onChange={(e) => updateFormField("rate", e.target.value)}
                      required
                    />
                    {fieldErrors.rate && (
                      <div className="cat-field-error">
                        {Array.isArray(fieldErrors.rate)
                          ? fieldErrors.rate.join(" ")
                          : fieldErrors.rate}
                      </div>
                    )}
                  </div>

                  {/* Is Active */}
                  <div className="cat-form-group" style={{ justifyContent: "center" }}>
                    <label className="cat-form-checkbox-label">
                      <input
                        type="checkbox"
                        className="cat-form-checkbox"
                        checked={form.is_active}
                        onChange={(e) => updateFormField("is_active", e.target.checked)}
                      />
                      <span>Active</span>
                    </label>
                    {fieldErrors.is_active && (
                      <div className="cat-field-error">
                        {Array.isArray(fieldErrors.is_active)
                          ? fieldErrors.is_active.join(" ")
                          : fieldErrors.is_active}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="cat-modal-footer">
                <button
                  type="button"
                  className="cat-btn cat-btn-secondary"
                  onClick={() => setIsModalOpen(false)}
                  disabled={saving}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="cat-btn cat-btn-primary"
                  disabled={saving}
                >
                  {saving ? "Saving..." : isEditing ? "Update Tax" : "Create Tax"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
