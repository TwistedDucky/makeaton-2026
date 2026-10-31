import React, { useState, useEffect } from "react";
import { getProducts, getPlans } from "../api/catalog";
import { createSubscription } from "../api/subscriptions";
import { useAuth } from "../context/AuthContext";
import { Package, Calendar, Plus, X, Check, ShieldCheck } from "lucide-react";

export default function CatalogView({ onNavigate }) {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState("products");
  const [products, setProducts] = useState([]);
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);

  // Subscribe Modal State for Customers
  const [subscribingProduct, setSubscribingProduct] = useState(null);
  const [selectedVariantId, setSelectedVariantId] = useState("");
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [paymentTerms, setPaymentTerms] = useState("IMMEDIATE");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadCatalog() {
      setLoading(true);
      try {
        const [prodRes, planRes] = await Promise.all([
          getProducts({ page_size: 100 }).catch(() => ({ results: [] })),
          getPlans({ page_size: 100 }).catch(() => ({ results: [] })),
        ]);

        const prodList = prodRes.results || prodRes || [];
        const planList = planRes.results || planRes || [];

        if (prodList.length > 0) {
          setProducts(prodList);
        } else {
          // Fallback demo products if table is empty
          setProducts([
            {
              id: 1,
              name: "Standard SaaS Platform",
              type: "service",
              sales_price: "50.00",
              cost_price: "10.00",
              variants: [{ id: 1, attribute: "Brand", value: "Standard Cloud", extra_price: "0.00" }],
              is_active: true,
            },
            {
              id: 2,
              name: "Pro Analytics & Reporting",
              type: "addon",
              sales_price: "100.00",
              cost_price: "20.00",
              variants: [{ id: 2, attribute: "Sync", value: "Realtime", extra_price: "40.00" }],
              is_active: true,
            },
            {
              id: 3,
              name: "Enterprise Infrastructure",
              type: "service",
              sales_price: "500.00",
              cost_price: "150.00",
              variants: [{ id: 3, attribute: "Brand", value: "Odoo", extra_price: "560.00" }],
              is_active: true,
            },
          ]);
        }

        if (planList.length > 0) {
          setPlans(planList);
        } else {
          setPlans([
            { id: 1, name: "Monthly Starter", price: "50.00", billing_period: "monthly", renewable: true, closable: true, auto_close: false },
            { id: 2, name: "Pro Growth", price: "150.00", billing_period: "monthly", renewable: true, closable: true, auto_close: false },
            { id: 3, name: "Enterprise Annual", price: "5000.00", billing_period: "yearly", renewable: true, closable: true, auto_close: false },
          ]);
        }
      } catch (err) {
        console.error("Failed to load catalog", err);
      } finally {
        setLoading(false);
      }
    }

    loadCatalog();
  }, []);

  const role = user?.role || "CUSTOMER";
  const isCustomer = role === "CUSTOMER";

  function handleOpenSubscribe(prod, defaultPlanId = "") {
    setSubscribingProduct(prod);
    setSelectedVariantId(prod.variants && prod.variants.length > 0 ? String(prod.variants[0].id) : "");
    setSelectedPlanId(defaultPlanId || (plans.length > 0 ? String(plans[0].id) : "1"));
    setQuantity(1);
    setPaymentTerms("IMMEDIATE");
    setError("");
  }

  function handleSubscribePlan(pl) {
    const firstProd = products[0] || { id: 1, name: "Software License", sales_price: pl.price || "50.00" };
    handleOpenSubscribe(firstProd, String(pl.id));
  }

  // Price calculations
  const basePrice = Number(subscribingProduct?.sales_price || 0);
  const selectedVariant = (subscribingProduct?.variants || []).find(
    (v) => String(v.id) === String(selectedVariantId)
  );
  const variantPrice = selectedVariant ? Number(selectedVariant.extra_price || 0) : 0;
  const unitPrice = basePrice + variantPrice;
  const subtotal = unitPrice * (Number(quantity) || 1);
  const taxes = subtotal * 0.18;
  const totalAmount = subtotal + taxes;

  async function handleConfirmSubscribe(e) {
    e.preventDefault();
    if (!subscribingProduct) return;
    setSubmitting(true);
    setError("");

    try {
      const payload = {
        plan: Number(selectedPlanId),
        payment_terms: paymentTerms,
        status: "CONFIRMED",
        lines: [
          {
            product: subscribingProduct.id,
            variant: selectedVariantId ? Number(selectedVariantId) : null,
            quantity: Number(quantity) || 1,
            unit_price: unitPrice.toFixed(2),
            taxes: taxes.toFixed(2),
          },
        ],
      };

      await createSubscription(payload);
      setMessage(`Successfully subscribed to ${subscribingProduct.name}! Your contract is active.`);
      setSubscribingProduct(null);
    } catch (err) {
      console.error("Subscription failed", err);
      setError(err?.message || err?.error || "Failed to create subscription.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="view-container">
      <div className="view-header">
        <div>
          <h2>{isCustomer ? "Products & Subscription Plans" : "Catalog Management"}</h2>
          <p>
            {isCustomer
              ? "Select and subscribe to software products, services, and flexible recurring billing plans."
              : "Configure software offerings, recurring billing intervals, and product variant add-ons."}
          </p>
        </div>
        {!isCustomer && (
          <a
            href="http://localhost:8001/admin/catalog/"
            target="_blank"
            rel="noreferrer"
            className="btn-secondary"
          >
            Manage in Django Admin
          </a>
        )}
      </div>

      {message && (
        <div className="notice-banner" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>{message}</span>
          {onNavigate && (
            <button
              className="btn-primary"
              style={{ padding: "6px 12px", fontSize: "12px" }}
              onClick={() => onNavigate("subscriptions")}
            >
              View in My Subscriptions
            </button>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="status-chips">
        <button
          className={`chip ${activeTab === "products" ? "chip-active" : ""}`}
          onClick={() => setActiveTab("products")}
        >
          <Package size={14} style={{ marginRight: 6, verticalAlign: "middle" }} />
          <span>Products & Offerings ({products.length})</span>
        </button>
        <button
          className={`chip ${activeTab === "plans" ? "chip-active" : ""}`}
          onClick={() => setActiveTab("plans")}
        >
          <Calendar size={14} style={{ marginRight: 6, verticalAlign: "middle" }} />
          <span>Billing Plans ({plans.length})</span>
        </button>
      </div>

      {loading ? (
        <div className="loading-state">Loading catalog from live REST API...</div>
      ) : activeTab === "products" ? (
        <div className="card">
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Product Name</th>
                  <th>Product Type</th>
                  <th>Base Price</th>
                  {!isCustomer && <th>Cost Price</th>}
                  <th>Variants & Add-ons</th>
                  <th>Status</th>
                  {isCustomer && <th>Action</th>}
                </tr>
              </thead>
              <tbody>
                {products.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <strong>{p.name}</strong>
                    </td>
                    <td>
                      <span className="chip" style={{ padding: "2px 8px", fontSize: "11px" }}>
                        {p.type}
                      </span>
                    </td>
                    <td className="tabular-num">
                      <strong>₹{Number(p.sales_price).toFixed(2)}</strong>
                    </td>
                    {!isCustomer && (
                      <td className="tabular-num" style={{ color: "var(--color-text-secondary)" }}>
                        {p.cost_price ? `₹${Number(p.cost_price).toFixed(2)}` : "—"}
                      </td>
                    )}
                    <td>
                      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                        {p.variants && p.variants.length > 0 ? (
                          p.variants.map((v, i) => (
                            <span
                              key={i}
                              style={{
                                backgroundColor: "var(--color-muted)",
                                border: "1px solid var(--color-border)",
                                borderRadius: "4px",
                                padding: "2px 6px",
                                fontSize: "11px",
                                color: "var(--color-midnight-indigo)",
                              }}
                            >
                              {v.attribute}: {v.value} {Number(v.extra_price) > 0 ? `(+₹${Number(v.extra_price).toFixed(2)})` : ""}
                            </span>
                          ))
                        ) : (
                          <span style={{ color: "var(--color-text-secondary)", fontSize: "12px" }}>None</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className={`status-badge ${p.is_active ? "status-active" : "status-overdue"}`}>
                        {p.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    {isCustomer && (
                      <td>
                        <button
                          className="btn-primary"
                          style={{ padding: "6px 14px", fontSize: "12px" }}
                          onClick={() => handleOpenSubscribe(p)}
                        >
                          <Plus size={14} />
                          <span>Subscribe</span>
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="card">
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Plan Name</th>
                  <th>Price</th>
                  <th>Billing Frequency</th>
                  <th>Min Qty</th>
                  <th>Auto-Renewal</th>
                  <th>Auto-Close</th>
                  <th>Status</th>
                  {isCustomer && <th>Action</th>}
                </tr>
              </thead>
              <tbody>
                {plans.map((pl) => (
                  <tr key={pl.id}>
                    <td>
                      <strong>{pl.name}</strong>
                    </td>
                    <td className="tabular-num">
                      <strong>₹{Number(pl.price).toFixed(2)}</strong>
                    </td>
                    <td>
                      <span className="chip" style={{ padding: "2px 8px", fontSize: "11px" }}>
                        {pl.billing_period}
                      </span>
                    </td>
                    <td>{pl.min_quantity || 1}</td>
                    <td>{pl.renewable ? "Yes (Renewable)" : "Manual"}</td>
                    <td>{pl.auto_close ? "Yes (Auto-close)" : "No"}</td>
                    <td>
                      <span className="status-badge status-active">Active</span>
                    </td>
                    {isCustomer && (
                      <td>
                        <button
                          className="btn-primary"
                          style={{ padding: "6px 14px", fontSize: "12px" }}
                          onClick={() => handleSubscribePlan(pl)}
                        >
                          <Plus size={14} />
                          <span>Select Plan</span>
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Subscribe Confirmation Modal */}
      {subscribingProduct && (
        <div className="modal-backdrop">
          <div className="modal-content" style={{ maxWidth: 540 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <h4 style={{ margin: 0 }}>Subscribe to {subscribingProduct.name}</h4>
              <button
                className="btn-secondary"
                style={{ padding: 4, borderRadius: "50%", minWidth: 28, height: 28 }}
                onClick={() => setSubscribingProduct(null)}
              >
                <X size={16} />
              </button>
            </div>

            {error && <div className="error-banner" style={{ marginBottom: 12 }}>{error}</div>}

            <form onSubmit={handleConfirmSubscribe} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--color-text-secondary)", marginBottom: 4 }}>
                  Product
                </label>
                <input
                  type="text"
                  value={subscribingProduct.name}
                  disabled
                  style={{ width: "100%", boxSizing: "border-box", background: "var(--color-muted)" }}
                />
              </div>

              {subscribingProduct.variants && subscribingProduct.variants.length > 0 && (
                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--color-text-secondary)", marginBottom: 4 }}>
                    Select Variant / Tier
                  </label>
                  <select
                    value={selectedVariantId}
                    onChange={(e) => setSelectedVariantId(e.target.value)}
                    style={{ width: "100%", boxSizing: "border-box" }}
                  >
                    {subscribingProduct.variants.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.attribute}: {v.value} {Number(v.extra_price) > 0 ? `(+₹${Number(v.extra_price).toFixed(2)})` : ""}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--color-text-secondary)", marginBottom: 4 }}>
                    Billing Plan
                  </label>
                  <select
                    value={selectedPlanId}
                    onChange={(e) => setSelectedPlanId(e.target.value)}
                    style={{ width: "100%", boxSizing: "border-box" }}
                  >
                    {plans.map((pl) => (
                      <option key={pl.id} value={pl.id}>
                        {pl.name} ({pl.billing_period})
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--color-text-secondary)", marginBottom: 4 }}>
                    Quantity
                  </label>
                  <input
                    type="number"
                    min="1"
                    value={quantity}
                    onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
                    style={{ width: "100%", boxSizing: "border-box" }}
                  />
                </div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--color-text-secondary)", marginBottom: 4 }}>
                  Payment Terms
                </label>
                <select
                  value={paymentTerms}
                  onChange={(e) => setPaymentTerms(e.target.value)}
                  style={{ width: "100%", boxSizing: "border-box" }}
                >
                  <option value="IMMEDIATE">Immediate Payment</option>
                  <option value="NET_15">Net 15 Days</option>
                  <option value="NET_30">Net 30 Days</option>
                </select>
              </div>

              {/* Summary Box */}
              <div
                style={{
                  backgroundColor: "var(--color-muted)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-sm)",
                  padding: 12,
                  marginTop: 4,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 13 }}>
                  <span style={{ color: "var(--color-text-secondary)" }}>Base Price:</span>
                  <span>₹{unitPrice.toFixed(2)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 13 }}>
                  <span style={{ color: "var(--color-text-secondary)" }}>Taxes (18% GST):</span>
                  <span>₹{taxes.toFixed(2)}</span>
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    paddingTop: 6,
                    borderTop: "1px solid var(--color-border)",
                    fontWeight: 700,
                    fontSize: 15,
                    color: "var(--color-midnight-indigo)",
                  }}
                >
                  <span>Total Due:</span>
                  <span>₹{totalAmount.toFixed(2)}</span>
                </div>
              </div>

              <div className="modal-actions" style={{ marginTop: 8 }}>
                <button type="button" className="btn-secondary" onClick={() => setSubscribingProduct(null)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? "Subscribing..." : "Confirm & Subscribe"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
