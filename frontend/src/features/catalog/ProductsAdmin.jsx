import { useState, useEffect, useMemo } from "react";
import {
  getProducts,
  createProduct,
  updateProduct,
  deactivateProduct,
  getProductVariants,
  createProductVariant,
  updateProductVariant,
  deactivateProductVariant,
  getTaxes,
} from "../../api/catalogAdmin";
import { useAuth } from "../../context/AuthContext";
import { formatCurrency } from "../../utils/formatters";
import "./catalog.css";

const INITIAL_PRODUCT_FORM = {
  name: "",
  type: "service",
  sales_price: "",
  cost_price: "0.00",
  tax: "",
  notes: "",
  is_active: true,
};

const INITIAL_VARIANT_FORM = {
  attribute: "",
  value: "",
  extra_price: "0.00",
  is_active: true,
};

export default function ProductsAdmin() {
  const { user, isAdmin } = useAuth();
  const userRole = (user?.data || user)?.role;
  const hasAdminAccess = Boolean(isAdmin || userRole === "ADMIN");
  const isCustomer = userRole === "CUSTOMER";
  const canViewInternalDetails = hasAdminAccess || userRole === "STAFF" || !isCustomer;

  // Table & Data State
  const [products, setProducts] = useState([]);
  const [taxesList, setTaxesList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tableError, setTableError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  // Filters
  const [filterType, setFilterType] = useState("");
  const [filterActive, setFilterActive] = useState("");
  const [searchName, setSearchName] = useState("");

  // Pagination
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [totalCount, setTotalCount] = useState(0);

  // Product Form Modal State
  const [isProductModalOpen, setIsProductModalOpen] = useState(false);
  const [isEditingProduct, setIsEditingProduct] = useState(false);
  const [editingProductId, setEditingProductId] = useState(null);
  const [productForm, setProductForm] = useState(INITIAL_PRODUCT_FORM);
  const [savingProduct, setSavingProduct] = useState(false);
  const [productFieldErrors, setProductFieldErrors] = useState({});
  const [productGeneralError, setProductGeneralError] = useState("");

  // Variants Modal State
  const [isVariantsModalOpen, setIsVariantsModalOpen] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [variantsList, setVariantsList] = useState([]);
  const [loadingVariants, setLoadingVariants] = useState(false);
  const [variantsError, setVariantsError] = useState("");
  const [variantsSuccessMessage, setVariantsSuccessMessage] = useState("");

  // Variant Form (Inline in Variants Modal)
  const [isVariantFormOpen, setIsVariantFormOpen] = useState(false);
  const [isEditingVariant, setIsEditingVariant] = useState(false);
  const [editingVariantId, setEditingVariantId] = useState(null);
  const [variantForm, setVariantForm] = useState(INITIAL_VARIANT_FORM);
  const [savingVariant, setSavingVariant] = useState(false);
  const [variantFieldErrors, setVariantFieldErrors] = useState({});
  const [variantGeneralError, setVariantGeneralError] = useState("");

  // Tax lookup map
  const taxMap = useMemo(() => {
    const map = {};
    for (const t of taxesList) {
      map[t.id] = `${t.name} (${t.kind === "percent" ? `${t.rate}%` : `₹${t.rate}`})`;
    }
    return map;
  }, [taxesList]);

  // Load active taxes once for dropdown & table lookup
  useEffect(() => {
    let ignore = false;
    async function fetchTaxes() {
      try {
        const res = await getTaxes({ page_size: 100 });
        if (!ignore) {
          const list = res.results || (Array.isArray(res) ? res : []);
          setTaxesList(list);
        }
      } catch (err) {
        console.error("Failed to load taxes for products admin", err);
      }
    }
    fetchTaxes();
    return () => {
      ignore = true;
    };
  }, []);

  // Load Products with filters & pagination
  useEffect(() => {
    let ignore = false;
    async function fetchProducts() {
      try {
        const params = {
          page,
          page_size: pageSize,
        };

        if (filterType) params.type = filterType;
        if (filterActive !== "") params.is_active = filterActive;
        if (searchName.trim()) params.search = searchName.trim();

        const res = await getProducts(params);
        if (!ignore) {
          const items = res.results || (Array.isArray(res) ? res : []);
          setProducts(items);
          setTotalCount(typeof res.count === "number" ? res.count : items.length);
          setTableError("");
          setLoading(false);
        }
      } catch (err) {
        if (!ignore) {
          console.error("Failed to load products", err);
          setTableError(err?.message || "Failed to load products from catalog API.");
          setLoading(false);
        }
      }
    }

    fetchProducts();
    return () => {
      ignore = true;
    };
  }, [page, pageSize, filterType, filterActive, searchName, refreshTrigger]);

  function triggerRefresh() {
    setRefreshTrigger((prev) => prev + 1);
  }

  // Filter change handlers
  function handleFilterTypeChange(val) {
    setFilterType(val);
    setPage(1);
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
    setFilterType("");
    setFilterActive("");
    setSearchName("");
    setPage(1);
  }

  // --------------------------------------------------------------------------
  // Product Create / Edit Handlers
  // --------------------------------------------------------------------------

  function handleOpenCreateProduct() {
    setIsEditingProduct(false);
    setEditingProductId(null);
    setProductForm(INITIAL_PRODUCT_FORM);
    setProductFieldErrors({});
    setProductGeneralError("");
    setIsProductModalOpen(true);
  }

  function handleOpenEditProduct(p) {
    setIsEditingProduct(true);
    setEditingProductId(p.id);
    setProductForm({
      name: p.name || "",
      type: p.type || "service",
      sales_price: p.sales_price || "",
      cost_price: p.cost_price || "0.00",
      tax: p.tax || "",
      notes: p.notes || "",
      is_active: p.is_active ?? true,
    });
    setProductFieldErrors({});
    setProductGeneralError("");
    setIsProductModalOpen(true);
  }

  function updateProductFormField(field, value) {
    setProductForm((prev) => ({ ...prev, [field]: value }));
    if (productFieldErrors[field]) {
      setProductFieldErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  }

  async function handleSaveProduct(e) {
    e.preventDefault();
    setSavingProduct(true);
    setProductFieldErrors({});
    setProductGeneralError("");
    setSuccessMessage("");

    const payload = {
      name: productForm.name.trim(),
      type: productForm.type.trim(),
      sales_price: productForm.sales_price,
      cost_price: productForm.cost_price || "0.00",
      tax: productForm.tax ? parseInt(productForm.tax, 10) : null,
      notes: productForm.notes || "",
      is_active: Boolean(productForm.is_active),
    };

    try {
      if (isEditingProduct) {
        await updateProduct(editingProductId, payload);
        setSuccessMessage(`Product "${payload.name}" updated successfully.`);
      } else {
        await createProduct(payload);
        setSuccessMessage(`Product "${payload.name}" created successfully.`);
      }
      setIsProductModalOpen(false);
      triggerRefresh();
    } catch (err) {
      console.error("Save product failed", err);
      if (err && typeof err === "object") {
        if (err.errors) {
          setProductFieldErrors(err.errors);
          if (err.errors.non_field_errors) {
            setProductGeneralError(
              Array.isArray(err.errors.non_field_errors)
                ? err.errors.non_field_errors.join(" ")
                : String(err.errors.non_field_errors)
            );
          } else if (err.message && err.message !== "Request failed") {
            setProductGeneralError(err.message);
          }
        } else if (err.detail) {
          setProductGeneralError(err.detail);
        } else if (err.message) {
          setProductGeneralError(err.message);
        } else {
          setProductFieldErrors(err);
        }
      } else {
        setProductGeneralError("An unexpected error occurred while saving product.");
      }
    } finally {
      setSavingProduct(false);
    }
  }

  async function handleDeactivateProduct(p) {
    const ok = window.confirm(`Are you sure you want to deactivate product "${p.name}"?`);
    if (!ok) return;

    setTableError("");
    setSuccessMessage("");
    try {
      const res = await deactivateProduct(p.id);
      setSuccessMessage(res?.message || `Product "${p.name}" deactivated.`);
      triggerRefresh();
    } catch (err) {
      console.error("Deactivate product failed", err);
      setTableError(err?.message || err?.detail || `Failed to deactivate product "${p.name}".`);
    }
  }

  // --------------------------------------------------------------------------
  // Variants Panel / Modal Handlers
  // --------------------------------------------------------------------------

  async function loadProductVariants(productId) {
    setLoadingVariants(true);
    setVariantsError("");
    try {
      const res = await getProductVariants(productId);
      const items = res.results || (Array.isArray(res) ? res : []);
      setVariantsList(items);
    } catch (err) {
      console.error("Failed to load variants", err);
      setVariantsError(err?.message || "Failed to load variants for this product.");
    } finally {
      setLoadingVariants(false);
    }
  }

  function handleOpenVariants(p) {
    setSelectedProduct(p);
    setIsVariantsModalOpen(true);
    setIsVariantFormOpen(false);
    setVariantsSuccessMessage("");
    setVariantsError("");
    loadProductVariants(p.id);
  }

  function handleOpenAddVariant() {
    setIsEditingVariant(false);
    setEditingVariantId(null);
    setVariantForm(INITIAL_VARIANT_FORM);
    setVariantFieldErrors({});
    setVariantGeneralError("");
    setIsVariantFormOpen(true);
  }

  function handleOpenEditVariant(v) {
    setIsEditingVariant(true);
    setEditingVariantId(v.id);
    setVariantForm({
      attribute: v.attribute || "",
      value: v.value || "",
      extra_price: v.extra_price || "0.00",
      is_active: v.is_active ?? true,
    });
    setVariantFieldErrors({});
    setVariantGeneralError("");
    setIsVariantFormOpen(true);
  }

  function updateVariantFormField(field, value) {
    setVariantForm((prev) => ({ ...prev, [field]: value }));
    if (variantFieldErrors[field]) {
      setVariantFieldErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  }

  async function handleSaveVariant(e) {
    e.preventDefault();
    if (!selectedProduct) return;

    setSavingVariant(true);
    setVariantFieldErrors({});
    setVariantGeneralError("");
    setVariantsSuccessMessage("");

    const payload = {
      product: selectedProduct.id,
      attribute: variantForm.attribute.trim(),
      value: variantForm.value.trim(),
      extra_price: variantForm.extra_price || "0.00",
      is_active: Boolean(variantForm.is_active),
    };

    try {
      if (isEditingVariant) {
        await updateProductVariant(selectedProduct.id, editingVariantId, payload);
        setVariantsSuccessMessage(`Variant "${payload.attribute}: ${payload.value}" updated.`);
      } else {
        await createProductVariant(selectedProduct.id, payload);
        setVariantsSuccessMessage(`Variant "${payload.attribute}: ${payload.value}" added.`);
      }
      setIsVariantFormOpen(false);
      loadProductVariants(selectedProduct.id);
      triggerRefresh(); // Refresh parent products table to sync variant chips
    } catch (err) {
      console.error("Save variant failed", err);
      if (err && typeof err === "object") {
        if (err.errors) {
          setVariantFieldErrors(err.errors);
          if (err.errors.non_field_errors) {
            setVariantGeneralError(
              Array.isArray(err.errors.non_field_errors)
                ? err.errors.non_field_errors.join(" ")
                : String(err.errors.non_field_errors)
            );
          } else if (err.message && err.message !== "Request failed") {
            setVariantGeneralError(err.message);
          }
        } else if (err.detail) {
          setVariantGeneralError(err.detail);
        } else if (err.message) {
          setVariantGeneralError(err.message);
        } else {
          setVariantFieldErrors(err);
        }
      } else {
        setVariantGeneralError("An unexpected error occurred while saving variant.");
      }
    } finally {
      setSavingVariant(false);
    }
  }

  async function handleDeactivateVariant(v) {
    if (!selectedProduct) return;
    const ok = window.confirm(
      `Are you sure you want to deactivate variant "${v.attribute}: ${v.value}"?`
    );
    if (!ok) return;

    setVariantsError("");
    setVariantsSuccessMessage("");
    try {
      const res = await deactivateProductVariant(selectedProduct.id, v.id);
      setVariantsSuccessMessage(res?.message || `Variant "${v.attribute}: ${v.value}" deactivated.`);
      loadProductVariants(selectedProduct.id);
      triggerRefresh();
    } catch (err) {
      console.error("Deactivate variant failed", err);
      setVariantsError(err?.message || err?.detail || "Failed to deactivate variant.");
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
          <h2 className="cat-title">Products & Variants Catalog</h2>
          <p className="cat-subtitle">
            Manage software offerings, base pricing tiers, cost records, taxes, and product variant add-ons.
          </p>
        </div>

        <div className="cat-actions-group">
          {hasAdminAccess && (
            <button
              type="button"
              className="cat-btn cat-btn-primary"
              onClick={handleOpenCreateProduct}
            >
              <span>+ New Product</span>
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
            <label className="cat-filter-label" htmlFor="cat-filter-search-prod">
              Search Product
            </label>
            <input
              id="cat-filter-search-prod"
              type="text"
              className="cat-filter-input"
              placeholder="e.g. CRM, ERP, Support..."
              value={searchName}
              onChange={(e) => handleSearchChange(e.target.value)}
            />
          </div>

          <div className="cat-filter-group">
            <label className="cat-filter-label" htmlFor="cat-filter-prod-type">
              Product Type
            </label>
            <select
              id="cat-filter-prod-type"
              className="cat-filter-select"
              value={filterType}
              onChange={(e) => handleFilterTypeChange(e.target.value)}
            >
              <option value="">All Types</option>
              <option value="service">Service</option>
              <option value="addon">Add-on</option>
            </select>
          </div>

          <div className="cat-filter-group">
            <label className="cat-filter-label" htmlFor="cat-filter-active-prod">
              Status
            </label>
            <select
              id="cat-filter-active-prod"
              className="cat-filter-select"
              value={filterActive}
              onChange={(e) => handleFilterActiveChange(e.target.value)}
            >
              <option value="">All Statuses</option>
              <option value="true">Active Only</option>
              <option value="false">Inactive Only</option>
            </select>
          </div>

          {(filterType || filterActive !== "" || searchName) && (
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

      {/* Products Table */}
      <div className="cat-table-card">
        {loading ? (
          <div className="cat-loading-state">Loading products from catalog API...</div>
        ) : products.length === 0 ? (
          <div className="cat-empty-state">
            No products match the selected filter criteria.
          </div>
        ) : (
          <div className="cat-table-responsive">
            <table className="cat-table">
              <thead>
                <tr>
                  <th className="cat-th">Product Name</th>
                  <th className="cat-th">Type</th>
                  <th className="cat-th">Sales Price</th>
                  {canViewInternalDetails && <th className="cat-th">Cost Price</th>}
                  <th className="cat-th">Tax Rule</th>
                  {canViewInternalDetails && <th className="cat-th">Internal Notes</th>}
                  <th className="cat-th">Variants</th>
                  <th className="cat-th">Status</th>
                  <th className="cat-th" style={{ textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {products.map((p) => {
                  const variants = p.variants || [];

                  return (
                    <tr key={p.id}>
                      <td className="cat-td">
                        <strong>{p.name}</strong>
                      </td>
                      <td className="cat-td">
                        <span className="cat-chip" style={{ textTransform: "capitalize" }}>
                          {p.type}
                        </span>
                      </td>
                      <td className="cat-td cat-tabular-num">
                        <strong>{formatCurrency(p.sales_price)}</strong>
                      </td>
                      {canViewInternalDetails && (
                        <td className="cat-td cat-tabular-num" style={{ color: "var(--color-text-secondary)" }}>
                          {p.cost_price ? formatCurrency(p.cost_price) : "—"}
                        </td>
                      )}
                      <td className="cat-td">
                        {p.tax ? (
                          <span className="cat-chip">{taxMap[p.tax] || `Tax #${p.tax}`}</span>
                        ) : (
                          <span style={{ color: "var(--color-text-secondary)" }}>No Tax</span>
                        )}
                      </td>
                      {canViewInternalDetails && (
                        <td className="cat-td" style={{ fontSize: "12px", maxWidth: "180px", color: "var(--color-text-secondary)" }}>
                          {p.notes ? p.notes : "—"}
                        </td>
                      )}
                      <td className="cat-td">
                        <div style={{ display: "flex", gap: "4px", flexWrap: "wrap", alignItems: "center" }}>
                          {variants.length > 0 ? (
                            variants.slice(0, 2).map((v) => (
                              <span key={v.id} className="cat-chip" style={{ fontSize: "11px" }}>
                                {v.attribute}: {v.value} {Number(v.extra_price) > 0 ? `(+${formatCurrency(v.extra_price)})` : ""}
                              </span>
                            ))
                          ) : (
                            <span style={{ color: "var(--color-text-secondary)", fontSize: "12px" }}>None</span>
                          )}
                          {variants.length > 2 && (
                            <span style={{ fontSize: "11px", color: "var(--color-text-secondary)" }}>
                              +{variants.length - 2} more
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="cat-td">
                        <span
                          className={`cat-badge ${
                            p.is_active ? "cat-badge-active" : "cat-badge-inactive"
                          }`}
                        >
                          {p.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td className="cat-td" style={{ textAlign: "right" }}>
                        <div className="cat-actions-cell" style={{ justifyContent: "flex-end" }}>
                          <button
                            type="button"
                            className="cat-btn cat-btn-secondary cat-btn-sm"
                            title="Manage product variants"
                            onClick={() => handleOpenVariants(p)}
                          >
                            Variants ({variants.length})
                          </button>

                          {hasAdminAccess && (
                            <>
                              <button
                                type="button"
                                className="cat-btn cat-btn-secondary cat-btn-sm"
                                onClick={() => handleOpenEditProduct(p)}
                              >
                                Edit
                              </button>

                              {p.is_active && (
                                <button
                                  type="button"
                                  className="cat-btn cat-btn-danger cat-btn-sm"
                                  onClick={() => handleDeactivateProduct(p)}
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
            Showing {startIndex} to {endIndex} of {totalCount} products
          </div>

          <div className="cat-pagination-controls">
            <label htmlFor="cat-prod-page-size" style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>
              Per Page:
            </label>
            <select
              id="cat-prod-page-size"
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

      {/* Create / Edit Product Modal */}
      {isProductModalOpen && (
        <div className="cat-modal-overlay" onClick={() => setIsProductModalOpen(false)}>
          <div
            className="cat-modal-card"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className="cat-modal-header">
              <h3 className="cat-modal-title">
                {isEditingProduct ? `Edit Product: ${productForm.name}` : "Create New Product"}
              </h3>
              <button
                type="button"
                className="cat-modal-close"
                onClick={() => setIsProductModalOpen(false)}
                aria-label="Close"
              >
                ×
              </button>
            </div>

            <form onSubmit={handleSaveProduct}>
              <div className="cat-modal-body">
                {productGeneralError && (
                  <div className="cat-alert-error">
                    {productGeneralError}
                  </div>
                )}

                <div className="cat-form-grid">
                  {/* Name */}
                  <div className="cat-form-group cat-form-group-full">
                    <label className="cat-form-label" htmlFor="cat-prod-field-name">
                      Product Name *
                    </label>
                    <input
                      id="cat-prod-field-name"
                      type="text"
                      className={`cat-form-input ${productFieldErrors.name ? "cat-input-has-error" : ""}`}
                      placeholder="e.g. Brightloop CRM, Enterprise Suite..."
                      value={productForm.name}
                      onChange={(e) => updateProductFormField("name", e.target.value)}
                      required
                    />
                    {productFieldErrors.name && (
                      <div className="cat-field-error">
                        {Array.isArray(productFieldErrors.name)
                          ? productFieldErrors.name.join(" ")
                          : productFieldErrors.name}
                      </div>
                    )}
                  </div>

                  {/* Type */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-prod-field-type">
                      Product Type *
                    </label>
                    <input
                      id="cat-prod-field-type"
                      type="text"
                      className={`cat-form-input ${productFieldErrors.type ? "cat-input-has-error" : ""}`}
                      placeholder="e.g. service, addon..."
                      value={productForm.type}
                      onChange={(e) => updateProductFormField("type", e.target.value)}
                      required
                    />
                    {productFieldErrors.type && (
                      <div className="cat-field-error">
                        {Array.isArray(productFieldErrors.type)
                          ? productFieldErrors.type.join(" ")
                          : productFieldErrors.type}
                      </div>
                    )}
                  </div>

                  {/* Tax */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-prod-field-tax">
                      Applicable Tax Rule
                    </label>
                    <select
                      id="cat-prod-field-tax"
                      className={`cat-form-select ${productFieldErrors.tax ? "cat-input-has-error" : ""}`}
                      value={productForm.tax}
                      onChange={(e) => updateProductFormField("tax", e.target.value)}
                    >
                      <option value="">No Tax Assigned</option>
                      {taxesList.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name} ({t.kind === "percent" ? `${t.rate}%` : `₹${t.rate}`})
                        </option>
                      ))}
                    </select>
                    {productFieldErrors.tax && (
                      <div className="cat-field-error">
                        {Array.isArray(productFieldErrors.tax)
                          ? productFieldErrors.tax.join(" ")
                          : productFieldErrors.tax}
                      </div>
                    )}
                  </div>

                  {/* Sales Price */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-prod-field-sales-price">
                      Sales Price (₹) *
                    </label>
                    <input
                      id="cat-prod-field-sales-price"
                      type="number"
                      step="0.01"
                      min="0"
                      className={`cat-form-input ${productFieldErrors.sales_price ? "cat-input-has-error" : ""}`}
                      placeholder="e.g. 2000.00"
                      value={productForm.sales_price}
                      onChange={(e) => updateProductFormField("sales_price", e.target.value)}
                      required
                    />
                    {productFieldErrors.sales_price && (
                      <div className="cat-field-error">
                        {Array.isArray(productFieldErrors.sales_price)
                          ? productFieldErrors.sales_price.join(" ")
                          : productFieldErrors.sales_price}
                      </div>
                    )}
                  </div>

                  {/* Cost Price */}
                  <div className="cat-form-group">
                    <label className="cat-form-label" htmlFor="cat-prod-field-cost-price">
                      Internal Cost Price (₹) *
                    </label>
                    <input
                      id="cat-prod-field-cost-price"
                      type="number"
                      step="0.01"
                      min="0"
                      className={`cat-form-input ${productFieldErrors.cost_price ? "cat-input-has-error" : ""}`}
                      placeholder="e.g. 800.00"
                      value={productForm.cost_price}
                      onChange={(e) => updateProductFormField("cost_price", e.target.value)}
                      required
                    />
                    {productFieldErrors.cost_price && (
                      <div className="cat-field-error">
                        {Array.isArray(productFieldErrors.cost_price)
                          ? productFieldErrors.cost_price.join(" ")
                          : productFieldErrors.cost_price}
                      </div>
                    )}
                  </div>

                  {/* Notes */}
                  <div className="cat-form-group cat-form-group-full">
                    <label className="cat-form-label" htmlFor="cat-prod-field-notes">
                      Internal Notes
                    </label>
                    <textarea
                      id="cat-prod-field-notes"
                      className={`cat-form-textarea ${productFieldErrors.notes ? "cat-input-has-error" : ""}`}
                      placeholder="Optional notes for staff and admins..."
                      value={productForm.notes}
                      onChange={(e) => updateProductFormField("notes", e.target.value)}
                    />
                    {productFieldErrors.notes && (
                      <div className="cat-field-error">
                        {Array.isArray(productFieldErrors.notes)
                          ? productFieldErrors.notes.join(" ")
                          : productFieldErrors.notes}
                      </div>
                    )}
                  </div>

                  {/* Is Active */}
                  <div className="cat-form-group" style={{ justifyContent: "center" }}>
                    <label className="cat-form-checkbox-label">
                      <input
                        type="checkbox"
                        className="cat-form-checkbox"
                        checked={productForm.is_active}
                        onChange={(e) => updateProductFormField("is_active", e.target.checked)}
                      />
                      <span>Active</span>
                    </label>
                    {productFieldErrors.is_active && (
                      <div className="cat-field-error">
                        {Array.isArray(productFieldErrors.is_active)
                          ? productFieldErrors.is_active.join(" ")
                          : productFieldErrors.is_active}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="cat-modal-footer">
                <button
                  type="button"
                  className="cat-btn cat-btn-secondary"
                  onClick={() => setIsProductModalOpen(false)}
                  disabled={savingProduct}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="cat-btn cat-btn-primary"
                  disabled={savingProduct}
                >
                  {savingProduct ? "Saving..." : isEditingProduct ? "Update Product" : "Create Product"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Variants Modal */}
      {isVariantsModalOpen && selectedProduct && (
        <div className="cat-modal-overlay" onClick={() => setIsVariantsModalOpen(false)}>
          <div
            className="cat-modal-card"
            style={{ maxWidth: "780px" }}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className="cat-modal-header">
              <div>
                <h3 className="cat-modal-title">
                  Variants: {selectedProduct.name}
                </h3>
                <span style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>
                  Base Price: {formatCurrency(selectedProduct.sales_price)}
                </span>
              </div>
              <button
                type="button"
                className="cat-modal-close"
                onClick={() => setIsVariantsModalOpen(false)}
                aria-label="Close"
              >
                ×
              </button>
            </div>

            <div className="cat-modal-body">
              {variantsSuccessMessage && (
                <div className="cat-alert-success">
                  {variantsSuccessMessage}
                </div>
              )}

              {variantsError && (
                <div className="cat-alert-error">
                  {variantsError}
                </div>
              )}

              {/* Add / Edit Variant Subpanel */}
              {isVariantFormOpen ? (
                <div className="cat-subpanel">
                  <h4 style={{ margin: "0 0 12px 0", color: "var(--color-midnight-indigo)" }}>
                    {isEditingVariant ? "Edit Variant" : "Add Product Variant"}
                  </h4>

                  {variantGeneralError && (
                    <div className="cat-alert-error" style={{ marginBottom: "12px" }}>
                      {variantGeneralError}
                    </div>
                  )}

                  <form onSubmit={handleSaveVariant}>
                    <div className="cat-form-grid">
                      <div className="cat-form-group">
                        <label className="cat-form-label" htmlFor="cat-var-field-attr">
                          Attribute * (e.g. Brand, Edition, Tier)
                        </label>
                        <input
                          id="cat-var-field-attr"
                          type="text"
                          className={`cat-form-input ${variantFieldErrors.attribute ? "cat-input-has-error" : ""}`}
                          placeholder="e.g. Brand"
                          value={variantForm.attribute}
                          onChange={(e) => updateVariantFormField("attribute", e.target.value)}
                          required
                        />
                        {variantFieldErrors.attribute && (
                          <div className="cat-field-error">
                            {Array.isArray(variantFieldErrors.attribute)
                              ? variantFieldErrors.attribute.join(" ")
                              : variantFieldErrors.attribute}
                          </div>
                        )}
                      </div>

                      <div className="cat-form-group">
                        <label className="cat-form-label" htmlFor="cat-var-field-val">
                          Value * (e.g. Odoo, Zoho, Enterprise)
                        </label>
                        <input
                          id="cat-var-field-val"
                          type="text"
                          className={`cat-form-input ${variantFieldErrors.value ? "cat-input-has-error" : ""}`}
                          placeholder="e.g. Odoo"
                          value={variantForm.value}
                          onChange={(e) => updateVariantFormField("value", e.target.value)}
                          required
                        />
                        {variantFieldErrors.value && (
                          <div className="cat-field-error">
                            {Array.isArray(variantFieldErrors.value)
                              ? variantFieldErrors.value.join(" ")
                              : variantFieldErrors.value}
                          </div>
                        )}
                      </div>

                      <div className="cat-form-group">
                        <label className="cat-form-label" htmlFor="cat-var-field-extra">
                          Extra Price (₹)
                        </label>
                        <input
                          id="cat-var-field-extra"
                          type="number"
                          step="0.01"
                          min="0"
                          className={`cat-form-input ${variantFieldErrors.extra_price ? "cat-input-has-error" : ""}`}
                          placeholder="0.00"
                          value={variantForm.extra_price}
                          onChange={(e) => updateVariantFormField("extra_price", e.target.value)}
                        />
                        {variantFieldErrors.extra_price && (
                          <div className="cat-field-error">
                            {Array.isArray(variantFieldErrors.extra_price)
                              ? variantFieldErrors.extra_price.join(" ")
                              : variantFieldErrors.extra_price}
                          </div>
                        )}
                      </div>

                      <div className="cat-form-group" style={{ justifyContent: "center" }}>
                        <label className="cat-form-checkbox-label">
                          <input
                            type="checkbox"
                            className="cat-form-checkbox"
                            checked={variantForm.is_active}
                            onChange={(e) => updateVariantFormField("is_active", e.target.checked)}
                          />
                          <span>Active</span>
                        </label>
                        {variantFieldErrors.is_active && (
                          <div className="cat-field-error">
                            {Array.isArray(variantFieldErrors.is_active)
                              ? variantFieldErrors.is_active.join(" ")
                              : variantFieldErrors.is_active}
                          </div>
                        )}
                      </div>
                    </div>

                    <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end", marginTop: "12px" }}>
                      <button
                        type="button"
                        className="cat-btn cat-btn-secondary cat-btn-sm"
                        onClick={() => setIsVariantFormOpen(false)}
                        disabled={savingVariant}
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="cat-btn cat-btn-primary cat-btn-sm"
                        disabled={savingVariant}
                      >
                        {savingVariant ? "Saving..." : isEditingVariant ? "Update Variant" : "Save Variant"}
                      </button>
                    </div>
                  </form>
                </div>
              ) : (
                hasAdminAccess && (
                  <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "8px" }}>
                    <button
                      type="button"
                      className="cat-btn cat-btn-primary cat-btn-sm"
                      onClick={handleOpenAddVariant}
                    >
                      + Add Variant
                    </button>
                  </div>
                )
              )}

              {/* Variants Table */}
              {loadingVariants ? (
                <div className="cat-loading-state">Loading product variants...</div>
              ) : variantsList.length === 0 ? (
                <div className="cat-empty-state">
                  No variants defined for this product yet.
                </div>
              ) : (
                <div className="cat-table-responsive">
                  <table className="cat-table">
                    <thead>
                      <tr>
                        <th className="cat-th">Attribute</th>
                        <th className="cat-th">Value</th>
                        <th className="cat-th">Extra Price</th>
                        <th className="cat-th">Status</th>
                        {hasAdminAccess && <th className="cat-th" style={{ textAlign: "right" }}>Actions</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {variantsList.map((v) => (
                        <tr key={v.id}>
                          <td className="cat-td">
                            <strong>{v.attribute}</strong>
                          </td>
                          <td className="cat-td">
                            <span className="cat-chip">{v.value}</span>
                          </td>
                          <td className="cat-td cat-tabular-num">
                            {Number(v.extra_price) > 0 ? (
                              <strong>+{formatCurrency(v.extra_price)}</strong>
                            ) : (
                              <span style={{ color: "var(--color-text-secondary)" }}>₹0.00</span>
                            )}
                          </td>
                          <td className="cat-td">
                            <span
                              className={`cat-badge ${
                                v.is_active ? "cat-badge-active" : "cat-badge-inactive"
                              }`}
                            >
                              {v.is_active ? "Active" : "Inactive"}
                            </span>
                          </td>
                          {hasAdminAccess && (
                            <td className="cat-td" style={{ textAlign: "right" }}>
                              <div className="cat-actions-cell" style={{ justifyContent: "flex-end" }}>
                                <button
                                  type="button"
                                  className="cat-btn cat-btn-secondary cat-btn-sm"
                                  onClick={() => handleOpenEditVariant(v)}
                                >
                                  Edit
                                </button>
                                {v.is_active && (
                                  <button
                                    type="button"
                                    className="cat-btn cat-btn-danger cat-btn-sm"
                                    onClick={() => handleDeactivateVariant(v)}
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
            </div>

            <div className="cat-modal-footer">
              <button
                type="button"
                className="cat-btn cat-btn-secondary"
                onClick={() => setIsVariantsModalOpen(false)}
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

