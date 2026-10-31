import { useState, useEffect } from "react";
import {
  getPlans,
  createPlan,
  updatePlan,
  deactivatePlan,
} from "../../api/catalogAdmin";
import { useAuth } from "../../context/AuthContext";
import { formatCurrency, formatDate } from "../../utils/formatters";
import "./catalog.css";

function getTodayString() {
  return new Date().toISOString().split("T")[0];
}

const INITIAL_FORM = {
  name: "",
  billing_period: "monthly",
  price: "",
  min_quantity: 1,
  available_from: getTodayString(),
  available_to: "",
  auto_close: false,
  closable: true,
  pausable: false,
  renewable: true,
  is_active: true,
};

export default function PlansAdmin() {
  const { user, isAdmin } = useAuth();
  const userRole = (user?.data || user)?.role;
  const hasAdminAccess = Boolean(isAdmin || userRole === "ADMIN");

  // Table & Data State
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tableError, setTableError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  // Filters
  const [filterBillingPeriod, setFilterBillingPeriod] = useState("");
  const [filterActive, setFilterActive] = useState("");
  const [filterAvailable, setFilterAvailable] = useState("");
  const [filterAvailableDate, setFilterAvailableDate] = useState("");
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

  // Load Plans with filters & pagination
  useEffect(() => {
    let ignore = false;
    async function fetchPlans() {
      try {
        const params = {
          page,
          page_size: pageSize,
        };

        if (filterBillingPeriod) params.billing_period = filterBillingPeriod;
        if (filterActive !== "") params.is_active = filterActive;
        if (filterAvailable !== "") {
          params.available = filterAvailable;
        } else if (filterAvailableDate) {
          // If available date is selected and matches today, query available=true
          params.available = "true";
        }
        if (searchName.trim()) params.search = searchName.trim();

        const res = await getPlans(params);
        if (!ignore) {
          let items = res.results || (Array.isArray(res) ? res : []);

          // Client-side refinement if a specific available date was specified
          if (filterAvailableDate) {
            items = items.filter((pl) => {
              const fromOk = !pl.available_from || pl.available_from <= filterAvailableDate;
              const toOk = !pl.available_to || pl.available_to >= filterAvailableDate;
              return fromOk && toOk;
            });
          }

          setPlans(items);
          setTotalCount(typeof res.count === "number" ? res.count : items.length);
          setTableError("");
          setLoading(false);
        }
      } catch (err) {
        if (!ignore) {
          console.error("Failed to load plans", err);
          setTableError(err?.message || "Failed to load plans from catalog API.");
          setLoading(false);
        }
      }
    }

    fetchPlans();
    return () => {
      ignore = true;
    };
  }, [page, pageSize, filterBillingPeriod, filterActive, filterAvailable, filterAvailableDate, searchName, refreshTrigger]);

  function triggerRefresh() {
    setRefreshTrigger((prev) => prev + 1);
  }

  // Filter change handlers
  function handleFilterBillingPeriodChange(val) {
    setFilterBillingPeriod(val);
    setPage(1);
  }

  function handleFilterActiveChange(val) {
    setFilterActive(val);
    setPage(1);
  }

  function handleFilterAvailableChange(val) {
    setFilterAvailable(val);
    setPage(1);
  }

  function handleFilterAvailableDateChange(val) {
    setFilterAvailableDate(val);
    setPage(1);
  }

  function handleSearchChange(val) {
    setSearchName(val);
    setPage(1);
  }

  function handleResetFilters() {
    setFilterBillingPeriod("");
    setFilterActive("");
    setFilterAvailable("");
    setFilterAvailableDate("");
    setSearchName("");
    setPage(1);
  }

  // Open Create Modal
  function handleOpenCreate() {
    setIsEditing(false);
    setEditingId(null);
    setForm({
      ...INITIAL_FORM,
      available_from: getTodayString(),
    });
    setFieldErrors({});
    setFormGeneralError("");
    setIsModalOpen(true);
  }

  // Open Edit Modal
  function handleOpenEdit(pl) {
    setIsEditing(true);
    setEditingId(pl.id);
    setForm({
      name: pl.name || "",
      billing_period: pl.billing_period || "monthly",
      price: pl.price || "",
      min_quantity: pl.min_quantity ?? 1,
      available_from: pl.available_from || getTodayString(),
      available_to: pl.available_to || "",
      auto_close: Boolean(pl.auto_close),
      closable: Boolean(pl.closable),
      pausable: Boolean(pl.pausable),
      renewable: Boolean(pl.renewable),
      is_active: pl.is_active ?? true,
    });
    setFieldErrors({});
    setFormGeneralError("");
    setIsModalOpen(true);
  }

  // Update Form Field
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

  // Save Plan (Create or Update)
  async function handleSavePlan(e) {
    e.preventDefault();
    setSaving(true);
    setFieldErrors({});
    setFormGeneralError("");
    setSuccessMessage("");

    const payload = {
      name: form.name.trim(),
      billing_period: form.billing_period,
      price: form.price,
      min_quantity: parseInt(form.min_quantity, 10) || 1,
      available_from: form.available_from,
      available_to: form.available_to ? form.available_to : null,
      auto_close: Boolean(form.auto_close),
      closable: Boolean(form.closable),
      pausable: Boolean(form.pausable),
      renewable: Boolean(form.renewable),
      is_active: Boolean(form.is_active),
    };

    try {
      if (isEditing) {
        await updatePlan(editingId, payload);
        setSuccessMessage(`Plan "${payload.name}" updated successfully.`);
      } else {
        await createPlan(payload);
        setSuccessMessage(`Plan "${payload.name}" created successfully.`);
      }
      setIsModalOpen(false);
      triggerRefresh();
    } catch (err) {
      console.error("Save plan failed", err);
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
        setFormGeneralError("An unexpected error occurred while saving.");
      }
    } finally {
      setSaving(false);
    }
  }

  // Deactivate Plan
  async function handleDeactivate(plan) {
    const ok = window.confirm(
      `Are you sure you want to deactivate plan "${plan.name}"?`
    );
    if (!ok) return;

    setTableError("");
    setSuccessMessage("");
    try {
      const res = await deactivatePlan(plan.id);
      setSuccessMessage(res?.message || `Plan "${plan.name}" deactivated.`);
      triggerRefresh();
    } catch (err) {
      console.error("Deactivate plan failed", err);
      setTableError(
        err?.message || err?.detail || `Failed to deactivate plan "${plan.name}".`
      );
    }
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
          <h2 className="cat-title">Subscription Billing Plans</h2>
          <p className="cat-subtitle">
            Configure recurring billing intervals, pricing tiers, and renewal and cancellation flags.
          </p>
        </div>

        <div className="cat-actions-group">
          {hasAdminAccess && (
            <button
              type="button"
              className="cat-btn cat-btn-primary"
              onClick={handleOpenCreate}
            >
              <span>+ New Plan</span>
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
            <label className="cat-filter-label" htmlFor="cat-filter-search-plan">
              Search Plan
            </label>
            <input
              id="cat-filter-search-plan"
              type="text"
              className="cat-filter-input"
              placeholder="e.g. Monthly Starter, Pro..."
              value={searchName}
              onChange={(e) => handleSearchChange(e.target.value)}
            />
          </div>

          <div className="cat-filter-group">
            <label className="cat-filter-label" htmlFor="cat-filter-period">
              Billing Period
            </label>
            <select
              id="cat-filter-period"
              className="cat-filter-select"
              value={filterBillingPeriod}
              onChange={(e) => handleFilterBillingPeriodChange(e.target.value)}
            >
              <option value="">All Periods</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
              <option value="yearly">Yearly</option>
            </select>
          </div>

          <div className="cat-filter-group">
            <label className="cat-filter-label" htmlFor="cat-filter-active-plan">
              Status
            </label>
            <select
              id="cat-filter-active-plan"
              className="cat-filter-select"
              value={filterActive}
              onChange={(e) => handleFilterActiveChange(e.target.value)}
            >
              <option value="">All Statuses</option>
              <option value="true">Active Only</option>
              <option value="false">Inactive Only</option>
            </select>
          </div>

          <div className="cat-filter-group">
            <label className="cat-filter-label" htmlFor="cat-filter-available-status">
              Availability
            </label>
            <select
              id="cat-filter-available-status"
              className="cat-filter-select"
              value={filterAvailable}
              onChange={(e) => handleFilterAvailableChange(e.target.value)}
            >
              <option value="">All Availability</option>
              <option value="true">Available Now</option>
              <option value="false">Unavailable</option>
            </select>
          </div>

          <div className="cat-filter-group">
            <label className="cat-filter-label" htmlFor="cat-filter-available-date">
              Available Date
            </label>
            <input
              id="cat-filter-available-date"
              type="date"
              className="cat-filter-input"
              value={filterAvailableDate}
              onChange={(e) => handleFilterAvailableDateChange(e.target.value)}
            />
          </div>

          {(filterBillingPeriod || filterActive !== "" || filterAvailable !== "" || filterAvailableDate || searchName) && (
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

      {/* Plans Table */}
      <div className="cat-table-card">
        {loading ? (
          <div className="cat-loading-state">Loading plans from catalog API...</div>
        ) : plans.length === 0 ? (
          <div className="cat-empty-state">
            No billing plans match the selected filter criteria.
          </div>
        ) : (
          <div className="cat-table-responsive">
            <table className="cat-table">
              <thead>
                <tr>
                  <th className="cat-th">Plan Name</th>
                  <th className="cat-th">Price</th>
                  <th className="cat-th">Billing Frequency</th>
                  <th className="cat-th">Min Qty</th>
                  <th className="cat-th">Plan Flags</th>
                  <th className="cat-th">Availability Period</th>
                  <th className="cat-th">Status</th>
                  {hasAdminAccess && <th className="cat-th" style={{ textAlign: "right" }}>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {plans.map((pl) => (
                  <tr key={pl.id}>
                    <td className="cat-td">
                      <strong>{pl.name}</strong>
                    </td>
                    <td className="cat-td cat-tabular-num">
                      <strong>{formatCurrency(pl.price)}</strong>
                    </td>
                    <td className="cat-td">
                      <span className="cat-chip" style={{ textTransform: "capitalize" }}>
                        {pl.billing_period}
                      </span>
                    </td>
                    <td className="cat-td cat-tabular-num">
                      {pl.min_quantity || 1}
                    </td>
                    <td className="cat-td">
                      <div className="cat-flag-group">
                        <span
                          className={`cat-flag-badge ${pl.renewable ? "cat-flag-on" : "cat-flag-off"}`}
                          title={pl.renewable ? "Auto-renewable" : "Not renewable"}
                        >
                          {pl.renewable ? "✓ Renewable" : "× Renewable"}
                        </span>
                        <span
                          className={`cat-flag-badge ${pl.closable ? "cat-flag-on" : "cat-flag-off"}`}
                          title={pl.closable ? "Customer or staff can close" : "Not closable"}
                        >
                          {pl.closable ? "✓ Closable" : "× Closable"}
                        </span>
                        <span
                          className={`cat-flag-badge ${pl.pausable ? "cat-flag-on" : "cat-flag-off"}`}
                          title={pl.pausable ? "Can be paused" : "Not pausable"}
                        >
                          {pl.pausable ? "✓ Pausable" : "× Pausable"}
                        </span>
                        <span
                          className={`cat-flag-badge ${pl.auto_close ? "cat-flag-on" : "cat-flag-off"}`}
                          title={pl.auto_close ? "Automatically closes at period end" : "No auto-close"}
                        >
                          {pl.auto_close ? "✓ Auto-close" : "× Auto-close"}
                        </span>
                      </div>
                    </td>
                    <td className="cat-td" style={{ fontSize: "12px", whiteSpace: "nowrap" }}>
                      {formatDate(pl.available_from)} → {pl.available_to ? formatDate(pl.available_to) : "Ongoing"}
                    </td>
                    <td className="cat-td">
                      <span
                        className={`cat-badge ${
                          pl.is_active ? "cat-badge-active" : "cat-badge-inactive"
                        }`}
                      >
                        {pl.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    {hasAdminAccess && (
                      <td className="cat-td" style={{ textAlign: "right" }}>
                        <div className="cat-actions-cell" style={{ justifyContent: "flex-end" }}>
                          <button
                            type="button"
                            className="cat-btn cat-btn-secondary cat-btn-sm"
                            onClick={() => handleOpenEdit(pl)}
                          >
                            Edit
                          </button>
                          {pl.is_active && (
                            <button
                              type="button"
                              className="cat-btn cat-btn-danger cat-btn-sm"
                              onClick={() => handleDeactivate(pl)}
                            >
                              Deactivate
                            </button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Controls */}
        <div className="cat-pagination">
          <div className="cat-pagination-info">
            Showing {startIndex} to {endIndex} of {totalCount} plans
          </div>

          <div className="cat-pagination-controls">
            <label htmlFor="cat-plan-page-size" style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>
              Per Page:
            </label>
            <select
              id="cat-plan-page-size"
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

      {/* Create / Edit Plan Modal */}
      {isModalOpen && (
        <div className="cat-modal-overlay" onClick={() => setIsModalOpen(false)}>
          <div
            className="cat-modal-card"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className="cat-modal-header">
              <h3 className="cat-modal-title">
                {isEditing ? `Edit Plan: ${form.name}` : "Create New Billing Plan"}
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

            <form onSubmit={handleSavePlan}>
              <div className="cat-modal-body">
                {formGeneralError && (
                  <div className="cat-alert-error">
                    {formGeneralError}
                  </div>
                )}

                <div className="cat-form-grid">
                  {/* Name */}
                  <div className="cat-form-group cat-form-group-full">
                    <label className="cat-form-label" htmlFor="cat-plan-field-name">
                      Plan Name *
                    </label>
                    <input
                      id="cat-plan-field-name"
                      type="text"
                      className={`cat-form-input ${fieldErrors.name ? "cat-input-has-error" : ""}`}
                      placeholder="e.g. Monthly Starter, Enterprise Annual..."
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

                  {/* Billing Period */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-plan-field-period">
                      Billing Period *
                    </label>
                    <select
                      id="cat-plan-field-period"
                      className={`cat-form-select ${fieldErrors.billing_period ? "cat-input-has-error" : ""}`}
                      value={form.billing_period}
                      onChange={(e) => updateFormField("billing_period", e.target.value)}
                    >
                      <option value="daily">Daily</option>
                      <option value="weekly">Weekly</option>
                      <option value="monthly">Monthly</option>
                      <option value="yearly">Yearly</option>
                    </select>
                    {fieldErrors.billing_period && (
                      <div className="cat-field-error">
                        {Array.isArray(fieldErrors.billing_period)
                          ? fieldErrors.billing_period.join(" ")
                          : fieldErrors.billing_period}
                      </div>
                    )}
                  </div>

                  {/* Price */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-plan-field-price">
                      Recurring Price (₹) *
                    </label>
                    <input
                      id="cat-plan-field-price"
                      type="number"
                      step="0.01"
                      min="0"
                      className={`cat-form-input ${fieldErrors.price ? "cat-input-has-error" : ""}`}
                      placeholder="e.g. 50.00"
                      value={form.price}
                      onChange={(e) => updateFormField("price", e.target.value)}
                      required
                    />
                    {fieldErrors.price && (
                      <div className="cat-field-error">
                        {Array.isArray(fieldErrors.price)
                          ? fieldErrors.price.join(" ")
                          : fieldErrors.price}
                      </div>
                    )}
                  </div>

                  {/* Min Quantity */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-plan-field-min-qty">
                      Minimum Quantity *
                    </label>
                    <input
                      id="cat-plan-field-min-qty"
                      type="number"
                      min="1"
                      className={`cat-form-input ${fieldErrors.min_quantity ? "cat-input-has-error" : ""}`}
                      value={form.min_quantity}
                      onChange={(e) => updateFormField("min_quantity", e.target.value)}
                      required
                    />
                    {fieldErrors.min_quantity && (
                      <div className="cat-field-error">
                        {Array.isArray(fieldErrors.min_quantity)
                          ? fieldErrors.min_quantity.join(" ")
                          : fieldErrors.min_quantity}
                      </div>
                    )}
                  </div>

                  {/* Available From */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-plan-field-from">
                      Available From *
                    </label>
                    <input
                      id="cat-plan-field-from"
                      type="date"
                      className={`cat-form-input ${fieldErrors.available_from ? "cat-input-has-error" : ""}`}
                      value={form.available_from}
                      onChange={(e) => updateFormField("available_from", e.target.value)}
                      required
                    />
                    {fieldErrors.available_from && (
                      <div className="cat-field-error">
                        {Array.isArray(fieldErrors.available_from)
                          ? fieldErrors.available_from.join(" ")
                          : fieldErrors.available_from}
                      </div>
                    )}
                  </div>

                  {/* Available To */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-plan-field-to">
                      Available To (Optional)
                    </label>
                    <input
                      id="cat-plan-field-to"
                      type="date"
                      className={`cat-form-input ${fieldErrors.available_to ? "cat-input-has-error" : ""}`}
                      value={form.available_to}
                      onChange={(e) => updateFormField("available_to", e.target.value)}
                    />
                    {fieldErrors.available_to && (
                      <div className="cat-field-error">
                        {Array.isArray(fieldErrors.available_to)
                          ? fieldErrors.available_to.join(" ")
                          : fieldErrors.available_to}
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

                  {/* Four Lifecycle & Subscription Flags */}
                  <div className="cat-form-group cat-form-group-full">
                    <label className="cat-form-label">Plan Behavior & Policy Flags</label>
                    <div className="cat-checkbox-grid">
                      <label className="cat-form-checkbox-label">
                        <input
                          type="checkbox"
                          className="cat-form-checkbox"
                          checked={form.renewable}
                          onChange={(e) => updateFormField("renewable", e.target.checked)}
                        />
                        <span>Renewable</span>
                      </label>

                      <label className="cat-form-checkbox-label">
                        <input
                          type="checkbox"
                          className="cat-form-checkbox"
                          checked={form.closable}
                          onChange={(e) => updateFormField("closable", e.target.checked)}
                        />
                        <span>Closable</span>
                      </label>

                      <label className="cat-form-checkbox-label">
                        <input
                          type="checkbox"
                          className="cat-form-checkbox"
                          checked={form.pausable}
                          onChange={(e) => updateFormField("pausable", e.target.checked)}
                        />
                        <span>Pausable</span>
                      </label>

                      <label className="cat-form-checkbox-label">
                        <input
                          type="checkbox"
                          className="cat-form-checkbox"
                          checked={form.auto_close}
                          onChange={(e) => updateFormField("auto_close", e.target.checked)}
                        />
                        <span>Auto-Close</span>
                      </label>
                    </div>
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
                  {saving ? "Saving..." : isEditing ? "Update Plan" : "Create Plan"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

