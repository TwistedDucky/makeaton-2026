import { useState, useEffect, useMemo } from "react";
import {
  getDiscounts,
  createDiscount,
  updateDiscount,
  deactivateDiscount,
  getDiscountUsage,
  getProducts,
} from "../../api/catalogAdmin";
import { useAuth } from "../../context/AuthContext";
import { formatCurrency, formatDate } from "../../utils/formatters";
import "./catalog.css";

function getTodayString() {
  return new Date().toISOString().split("T")[0];
}

function getDefaultEndDateString() {
  const d = new Date();
  d.setMonth(d.getMonth() + 6);
  return d.toISOString().split("T")[0];
}

const INITIAL_FORM = {
  name: "",
  kind: "percent",
  value: "",
  min_purchase: "0.00",
  min_quantity: 1,
  start_date: getTodayString(),
  end_date: getDefaultEndDateString(),
  usage_limit: 100,
  scope: "subscription",
  product: "",
  is_active: true,
  used_count: 0,
};

export default function DiscountsAdmin() {
  const { user, isAdmin } = useAuth();
  const userRole = (user?.data || user)?.role;
  const hasAdminAccess = Boolean(isAdmin || userRole === "ADMIN");

  // Table & Data State
  const [discounts, setDiscounts] = useState([]);
  const [productsList, setProductsList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tableError, setTableError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  // Filters
  const [filterScope, setFilterScope] = useState("");
  const [filterActive, setFilterActive] = useState("");
  const [filterValidOn, setFilterValidOn] = useState("");
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

  // Usage Modal State
  const [isUsageModalOpen, setIsUsageModalOpen] = useState(false);
  const [selectedDiscountForUsage, setSelectedDiscountForUsage] = useState(null);
  const [usageList, setUsageList] = useState([]);
  const [loadingUsage, setLoadingUsage] = useState(false);
  const [usageError, setUsageError] = useState("");

  // Product map for display in table
  const productMap = useMemo(() => {
    const map = {};
    for (const p of productsList) {
      map[p.id] = p.name;
    }
    return map;
  }, [productsList]);

  // Load active products once for dropdown & table lookup
  useEffect(() => {
    let ignore = false;
    async function fetchProducts() {
      try {
        const res = await getProducts({ page_size: 100 });
        if (!ignore) {
          const list = res.results || (Array.isArray(res) ? res : []);
          setProductsList(list);
        }
      } catch (err) {
        console.error("Failed to fetch products for catalog admin", err);
      }
    }
    fetchProducts();
    return () => {
      ignore = true;
    };
  }, []);

  // Load Discounts with filters & pagination
  useEffect(() => {
    let ignore = false;
    async function fetchDiscounts() {
      try {
        const params = {
          page,
          page_size: pageSize,
        };

        if (filterScope) params.scope = filterScope;
        if (filterActive !== "") params.is_active = filterActive;
        if (filterValidOn) params.valid_on = filterValidOn;
        if (searchName.trim()) params.search = searchName.trim();

        const res = await getDiscounts(params);
        if (!ignore) {
          const items = res.results || (Array.isArray(res) ? res : []);
          setDiscounts(items);
          setTotalCount(typeof res.count === "number" ? res.count : items.length);
          setTableError("");
          setLoading(false);
        }
      } catch (err) {
        if (!ignore) {
          console.error("Failed to load discounts", err);
          setTableError(err?.message || "Failed to load discounts from catalog API.");
          setLoading(false);
        }
      }
    }

    fetchDiscounts();
    return () => {
      ignore = true;
    };
  }, [page, pageSize, filterScope, filterActive, filterValidOn, searchName, refreshTrigger]);

  function triggerRefresh() {
    setRefreshTrigger((prev) => prev + 1);
  }

  // Reset pagination when filters change
  function handleFilterScopeChange(val) {
    setFilterScope(val);
    setPage(1);
  }

  function handleFilterActiveChange(val) {
    setFilterActive(val);
    setPage(1);
  }

  function handleFilterValidOnChange(val) {
    setFilterValidOn(val);
    setPage(1);
  }

  function handleSearchChange(val) {
    setSearchName(val);
    setPage(1);
  }

  function handleResetFilters() {
    setFilterScope("");
    setFilterActive("");
    setFilterValidOn("");
    setSearchName("");
    setPage(1);
  }

  // Open Create Modal
  function handleOpenCreate() {
    setIsEditing(false);
    setEditingId(null);
    setForm({
      ...INITIAL_FORM,
      start_date: getTodayString(),
      end_date: getDefaultEndDateString(),
    });
    setFieldErrors({});
    setFormGeneralError("");
    setIsModalOpen(true);
  }

  // Open Edit Modal
  function handleOpenEdit(d) {
    setIsEditing(true);
    setEditingId(d.id);
    setForm({
      name: d.name || "",
      kind: d.kind || "percent",
      value: d.value || "",
      min_purchase: d.min_purchase || "0.00",
      min_quantity: d.min_quantity ?? 1,
      start_date: d.start_date || getTodayString(),
      end_date: d.end_date || getDefaultEndDateString(),
      usage_limit: d.usage_limit ?? 100,
      scope: d.scope || "subscription",
      product: d.product || "",
      is_active: d.is_active ?? true,
      used_count: d.used_count ?? 0,
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

  // Form Submit Handler
  async function handleSaveDiscount(e) {
    e.preventDefault();
    setSaving(true);
    setFieldErrors({});
    setFormGeneralError("");
    setSuccessMessage("");

    const payload = {
      name: form.name.trim(),
      kind: form.kind,
      value: form.value,
      min_purchase: form.min_purchase || "0.00",
      min_quantity: parseInt(form.min_quantity, 10) || 1,
      start_date: form.start_date,
      end_date: form.end_date,
      usage_limit: form.usage_limit ? parseInt(form.usage_limit, 10) : null,
      scope: form.scope,
      product: form.scope === "product" && form.product ? parseInt(form.product, 10) : null,
      is_active: Boolean(form.is_active),
    };

    try {
      if (isEditing) {
        await updateDiscount(editingId, payload);
        setSuccessMessage(`Discount "${payload.name}" updated successfully.`);
      } else {
        await createDiscount(payload);
        setSuccessMessage(`Discount "${payload.name}" created successfully.`);
      }
      setIsModalOpen(false);
      triggerRefresh();
    } catch (err) {
      console.error("Save discount failed", err);
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

  // Deactivate Handler
  async function handleDeactivate(discount) {
    const ok = window.confirm(
      `Are you sure you want to deactivate discount "${discount.name}"?`
    );
    if (!ok) return;

    setTableError("");
    setSuccessMessage("");
    try {
      const res = await deactivateDiscount(discount.id);
      setSuccessMessage(res?.message || `Discount "${discount.name}" deactivated.`);
      triggerRefresh();
    } catch (err) {
      console.error("Deactivate discount failed", err);
      setTableError(
        err?.message || err?.detail || `Failed to deactivate discount "${discount.name}".`
      );
    }
  }

  // Usage Modal Handler
  async function handleOpenUsage(discount) {
    setSelectedDiscountForUsage(discount);
    setIsUsageModalOpen(true);
    setLoadingUsage(true);
    setUsageError("");
    setUsageList([]);

    try {
      const res = await getDiscountUsage(discount.id);
      const usages = res.results || (Array.isArray(res) ? res : []);
      setUsageList(usages);
    } catch (err) {
      console.error("Failed to load discount usage", err);
      setUsageError(err?.message || "Failed to load discount redemptions.");
    } finally {
      setLoadingUsage(false);
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
          <h2 className="cat-title">Discount Rules & Promotions</h2>
          <p className="cat-subtitle">
            Manage percentage and fixed discounts, scope restrictions, and view redemption history.
          </p>
        </div>

        <div className="cat-actions-group">
          {hasAdminAccess && (
            <button
              type="button"
              className="cat-btn cat-btn-primary"
              onClick={handleOpenCreate}
            >
              <span>+ New Discount</span>
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
            <label className="cat-filter-label" htmlFor="cat-filter-search">
              Search Name
            </label>
            <input
              id="cat-filter-search"
              type="text"
              className="cat-filter-input"
              placeholder="e.g. Welcome, Volume..."
              value={searchName}
              onChange={(e) => handleSearchChange(e.target.value)}
            />
          </div>

          <div className="cat-filter-group">
            <label className="cat-filter-label" htmlFor="cat-filter-scope">
              Scope
            </label>
            <select
              id="cat-filter-scope"
              className="cat-filter-select"
              value={filterScope}
              onChange={(e) => handleFilterScopeChange(e.target.value)}
            >
              <option value="">All Scopes</option>
              <option value="subscription">Subscription</option>
              <option value="product">Product</option>
            </select>
          </div>

          <div className="cat-filter-group">
            <label className="cat-filter-label" htmlFor="cat-filter-active">
              Status
            </label>
            <select
              id="cat-filter-active"
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
            <label className="cat-filter-label" htmlFor="cat-filter-valid-on">
              Valid On Date
            </label>
            <input
              id="cat-filter-valid-on"
              type="date"
              className="cat-filter-input"
              value={filterValidOn}
              onChange={(e) => handleFilterValidOnChange(e.target.value)}
            />
          </div>

          {(filterScope || filterActive !== "" || filterValidOn || searchName) && (
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

      {/* Discounts Table */}
      <div className="cat-table-card">
        {loading ? (
          <div className="cat-loading-state">Loading discounts from catalog API...</div>
        ) : discounts.length === 0 ? (
          <div className="cat-empty-state">
            No discounts match the selected filter criteria.
          </div>
        ) : (
          <div className="cat-table-responsive">
            <table className="cat-table">
              <thead>
                <tr>
                  <th className="cat-th">Discount Name</th>
                  <th className="cat-th">Kind</th>
                  <th className="cat-th">Value</th>
                  <th className="cat-th">Scope</th>
                  <th className="cat-th">Min Requirements</th>
                  <th className="cat-th">Validity Period</th>
                  <th className="cat-th">Usage / Limit</th>
                  <th className="cat-th">Status</th>
                  <th className="cat-th" style={{ textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {discounts.map((d) => {
                  const isPercent = d.kind === "percent";
                  const displayValue = isPercent
                    ? `${Number(d.value)}%`
                    : formatCurrency(d.value);
                  const minPurchaseNum = Number(d.min_purchase || 0);

                  return (
                    <tr key={d.id}>
                      <td className="cat-td">
                        <strong>{d.name}</strong>
                      </td>
                      <td className="cat-td">
                        <span className="cat-chip">
                          {isPercent ? "Percent" : "Fixed Amount"}
                        </span>
                      </td>
                      <td className="cat-td cat-tabular-num">
                        <strong>{displayValue}</strong>
                      </td>
                      <td className="cat-td">
                        <span className="cat-chip cat-chip-scope">
                          {d.scope === "product"
                            ? `Product: ${productMap[d.product] || `#${d.product}`}`
                            : "Subscription"}
                        </span>
                      </td>
                      <td className="cat-td" style={{ fontSize: "13px" }}>
                        {minPurchaseNum > 0 || (d.min_quantity && d.min_quantity > 1) ? (
                          <div>
                            {minPurchaseNum > 0 && (
                              <div>Min: {formatCurrency(d.min_purchase)}</div>
                            )}
                            {d.min_quantity && d.min_quantity > 1 && (
                              <div style={{ color: "var(--color-text-secondary)" }}>
                                Min Qty: {d.min_quantity}
                              </div>
                            )}
                          </div>
                        ) : (
                          <span style={{ color: "var(--color-text-secondary)" }}>None</span>
                        )}
                      </td>
                      <td className="cat-td" style={{ fontSize: "12px", whiteSpace: "nowrap" }}>
                        {d.start_date} → {d.end_date}
                      </td>
                      <td className="cat-td cat-tabular-num">
                        {d.used_count ?? 0} / {d.usage_limit ?? "∞"}
                      </td>
                      <td className="cat-td">
                        <span
                          className={`cat-badge ${
                            d.is_active ? "cat-badge-active" : "cat-badge-inactive"
                          }`}
                        >
                          {d.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td className="cat-td" style={{ textAlign: "right" }}>
                        <div className="cat-actions-cell" style={{ justifyContent: "flex-end" }}>
                          <button
                            type="button"
                            className="cat-btn cat-btn-secondary cat-btn-sm"
                            title="View redemptions"
                            onClick={() => handleOpenUsage(d)}
                          >
                            Usage
                          </button>

                          {hasAdminAccess && (
                            <>
                              <button
                                type="button"
                                className="cat-btn cat-btn-secondary cat-btn-sm"
                                onClick={() => handleOpenEdit(d)}
                              >
                                Edit
                              </button>

                              {d.is_active && (
                                <button
                                  type="button"
                                  className="cat-btn cat-btn-danger cat-btn-sm"
                                  onClick={() => handleDeactivate(d)}
                                >
                                  Deactivate
                                </button>
                              )}
                            </>
                          )}
                        </div>
                      </td>
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
            Showing {startIndex} to {endIndex} of {totalCount} discounts
          </div>

          <div className="cat-pagination-controls">
            <label htmlFor="cat-page-size" style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>
              Per Page:
            </label>
            <select
              id="cat-page-size"
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

      {/* Create / Edit Form Modal */}
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
                {isEditing ? `Edit Discount: ${form.name}` : "Create New Discount"}
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

            <form onSubmit={handleSaveDiscount}>
              <div className="cat-modal-body">
                {formGeneralError && (
                  <div className="cat-alert-error">
                    {formGeneralError}
                  </div>
                )}

                <div className="cat-form-grid">
                  {/* Name */}
                  <div className="cat-form-group cat-form-group-full">
                    <label className="cat-form-label" htmlFor="cat-field-name">
                      Discount Name *
                    </label>
                    <input
                      id="cat-field-name"
                      type="text"
                      className={`cat-form-input ${fieldErrors.name ? "cat-input-has-error" : ""}`}
                      placeholder="e.g. Welcome 10% or Volume 500"
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
                    <label className="cat-form-label" htmlFor="cat-field-kind">
                      Discount Kind *
                    </label>
                    <select
                      id="cat-field-kind"
                      className={`cat-form-select ${fieldErrors.kind ? "cat-input-has-error" : ""}`}
                      value={form.kind}
                      onChange={(e) => updateFormField("kind", e.target.value)}
                    >
                      <option value="percent">Percent (%)</option>
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

                  {/* Value */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-field-value">
                      Value * {form.kind === "percent" ? "(1 to 100)" : "(Amount in ₹)"}
                    </label>
                    <input
                      id="cat-field-value"
                      type="number"
                      step="0.01"
                      className={`cat-form-input ${fieldErrors.value ? "cat-input-has-error" : ""}`}
                      placeholder={form.kind === "percent" ? "10" : "500.00"}
                      value={form.value}
                      onChange={(e) => updateFormField("value", e.target.value)}
                      required
                    />
                    {fieldErrors.value && (
                      <div className="cat-field-error">
                        {Array.isArray(fieldErrors.value)
                          ? fieldErrors.value.join(" ")
                          : fieldErrors.value}
                      </div>
                    )}
                  </div>

                  {/* Scope */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-field-scope">
                      Scope *
                    </label>
                    <select
                      id="cat-field-scope"
                      className={`cat-form-select ${fieldErrors.scope ? "cat-input-has-error" : ""}`}
                      value={form.scope}
                      onChange={(e) => updateFormField("scope", e.target.value)}
                    >
                      <option value="subscription">Subscription Level</option>
                      <option value="product">Product Specific</option>
                    </select>
                    {fieldErrors.scope && (
                      <div className="cat-field-error">
                        {Array.isArray(fieldErrors.scope)
                          ? fieldErrors.scope.join(" ")
                          : fieldErrors.scope}
                      </div>
                    )}
                  </div>

                  {/* Usage Limit */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-field-usage-limit">
                      Usage Limit *
                    </label>
                    <input
                      id="cat-field-usage-limit"
                      type="number"
                      min="1"
                      className={`cat-form-input ${fieldErrors.usage_limit ? "cat-input-has-error" : ""}`}
                      placeholder="e.g. 100"
                      value={form.usage_limit}
                      onChange={(e) => updateFormField("usage_limit", e.target.value)}
                      required
                    />
                    {fieldErrors.usage_limit && (
                      <div className="cat-field-error">
                        {Array.isArray(fieldErrors.usage_limit)
                          ? fieldErrors.usage_limit.join(" ")
                          : fieldErrors.usage_limit}
                      </div>
                    )}
                  </div>

                  {/* Product (Only shown when scope === "product") */}
                  {form.scope === "product" && (
                    <div className="cat-form-group cat-form-group-full">
                      <label className="cat-form-label" htmlFor="cat-field-product">
                        Target Product *
                      </label>
                      <select
                        id="cat-field-product"
                        className={`cat-form-select ${fieldErrors.product ? "cat-input-has-error" : ""}`}
                        value={form.product}
                        onChange={(e) => updateFormField("product", e.target.value)}
                        required={form.scope === "product"}
                      >
                        <option value="">Select a product...</option>
                        {productsList.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name} ({formatCurrency(p.sales_price)})
                          </option>
                        ))}
                      </select>
                      {fieldErrors.product && (
                        <div className="cat-field-error">
                          {Array.isArray(fieldErrors.product)
                            ? fieldErrors.product.join(" ")
                            : fieldErrors.product}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Min Purchase */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-field-min-purchase">
                      Min Purchase Amount (₹)
                    </label>
                    <input
                      id="cat-field-min-purchase"
                      type="number"
                      step="0.01"
                      min="0"
                      className={`cat-form-input ${fieldErrors.min_purchase ? "cat-input-has-error" : ""}`}
                      value={form.min_purchase}
                      onChange={(e) => updateFormField("min_purchase", e.target.value)}
                    />
                    {fieldErrors.min_purchase && (
                      <div className="cat-field-error">
                        {Array.isArray(fieldErrors.min_purchase)
                          ? fieldErrors.min_purchase.join(" ")
                          : fieldErrors.min_purchase}
                      </div>
                    )}
                  </div>

                  {/* Min Quantity */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-field-min-quantity">
                      Min Quantity
                    </label>
                    <input
                      id="cat-field-min-quantity"
                      type="number"
                      min="1"
                      className={`cat-form-input ${fieldErrors.min_quantity ? "cat-input-has-error" : ""}`}
                      value={form.min_quantity}
                      onChange={(e) => updateFormField("min_quantity", e.target.value)}
                    />
                    {fieldErrors.min_quantity && (
                      <div className="cat-field-error">
                        {Array.isArray(fieldErrors.min_quantity)
                          ? fieldErrors.min_quantity.join(" ")
                          : fieldErrors.min_quantity}
                      </div>
                    )}
                  </div>

                  {/* Start Date */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-field-start-date">
                      Start Date *
                    </label>
                    <input
                      id="cat-field-start-date"
                      type="date"
                      className={`cat-form-input ${fieldErrors.start_date ? "cat-input-has-error" : ""}`}
                      value={form.start_date}
                      onChange={(e) => updateFormField("start_date", e.target.value)}
                      required
                    />
                    {fieldErrors.start_date && (
                      <div className="cat-field-error">
                        {Array.isArray(fieldErrors.start_date)
                          ? fieldErrors.start_date.join(" ")
                          : fieldErrors.start_date}
                      </div>
                    )}
                  </div>

                  {/* End Date */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-field-end-date">
                      End Date *
                    </label>
                    <input
                      id="cat-field-end-date"
                      type="date"
                      className={`cat-form-input ${fieldErrors.end_date ? "cat-input-has-error" : ""}`}
                      value={form.end_date}
                      onChange={(e) => updateFormField("end_date", e.target.value)}
                      required
                    />
                    {fieldErrors.end_date && (
                      <div className="cat-field-error">
                        {Array.isArray(fieldErrors.end_date)
                          ? fieldErrors.end_date.join(" ")
                          : fieldErrors.end_date}
                      </div>
                    )}
                  </div>

                  {/* Read-only used_count (on Edit) */}
                  {isEditing && (
                    <div className="cat-form-group">
                      <label className="cat-form-label">
                        Used Count (Read-only)
                      </label>
                      <div className="cat-form-readonly-box">
                        {form.used_count ?? 0} redemptions
                      </div>
                    </div>
                  )}

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
                  {saving ? "Saving..." : isEditing ? "Update Discount" : "Create Discount"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Usage History Modal */}
      {isUsageModalOpen && (
        <div className="cat-modal-overlay" onClick={() => setIsUsageModalOpen(false)}>
          <div
            className="cat-modal-card"
            style={{ maxWidth: "700px" }}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className="cat-modal-header">
              <h3 className="cat-modal-title">
                Redemption History: {selectedDiscountForUsage?.name}
              </h3>
              <button
                type="button"
                className="cat-modal-close"
                onClick={() => setIsUsageModalOpen(false)}
                aria-label="Close"
              >
                ×
              </button>
            </div>

            <div className="cat-modal-body">
              {usageError && (
                <div className="cat-alert-error">
                  {usageError}
                </div>
              )}

              {loadingUsage ? (
                <div className="cat-loading-state">Loading redemption log...</div>
              ) : usageList.length === 0 ? (
                <div className="cat-empty-state">
                  No redemptions have been recorded for this discount yet.
                </div>
              ) : (
                <div className="cat-table-responsive">
                  <table className="cat-table">
                    <thead>
                      <tr>
                        <th className="cat-th">Invoice ID</th>
                        <th className="cat-th">Subscription ID</th>
                        <th className="cat-th">Redeemed At</th>
                      </tr>
                    </thead>
                    <tbody>
                      {usageList.map((u) => (
                        <tr key={u.id}>
                          <td className="cat-td">
                            <strong>Invoice #{u.invoice_id}</strong>
                          </td>
                          <td className="cat-td">
                            Subscription #{u.subscription_id}
                          </td>
                          <td className="cat-td">
                            {formatDate(u.created_at)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="cat-modal-footer">
              <button
                type="button"
                className="cat-btn cat-btn-secondary"
                onClick={() => setIsUsageModalOpen(false)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
