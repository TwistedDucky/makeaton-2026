import React, { useState, useEffect } from "react";
import { getProducts, getPlans } from "../api/catalog";
import { useAuth } from "../context/AuthContext";

export default function CatalogView() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState("products");
  const [products, setProducts] = useState([]);
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);

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

  const role = user?.role || "STAFF";
  const isCustomer = role === "CUSTOMER";

  return (
    <div className="view-container">
      <div className="view-header">
        <div>
          <h2>Catalog & Subscription Plans</h2>
          <p>Configure software offerings, recurring billing intervals, and product variant add-ons.</p>
        </div>
        {!isCustomer && (
          <a
            href="http://localhost:8001/admin/catalog/"
            target="_blank"
            rel="noreferrer"
            className="btn-secondary"
          >
            Manage in Django Admin ↗
          </a>
        )}
      </div>

      <div className="status-chips" style={{ marginBottom: "1.5rem" }}>
        <button
          className={`chip ${activeTab === "products" ? "chip-active" : ""}`}
          onClick={() => setActiveTab("products")}
        >
          📦 Products & Variants ({products.length})
        </button>
        <button
          className={`chip ${activeTab === "plans" ? "chip-active" : ""}`}
          onClick={() => setActiveTab("plans")}
        >
          📅 Billing Plans ({plans.length})
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
                </tr>
              </thead>
              <tbody>
                {products.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <strong>{p.name}</strong>
                    </td>
                    <td>
                      <span className="chip" style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }}>
                        {p.type}
                      </span>
                    </td>
                    <td className="tabular-num">${Number(p.sales_price).toFixed(2)}</td>
                    {!isCustomer && (
                      <td className="tabular-num" style={{ color: "var(--secondary-text)" }}>
                        {p.cost_price ? `$${Number(p.cost_price).toFixed(2)}` : "—"}
                      </td>
                    )}
                    <td>
                      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                        {p.variants && p.variants.length > 0 ? (
                          p.variants.map((v, i) => (
                            <span
                              key={i}
                              style={{
                                backgroundColor: "var(--soft-vanilla)",
                                border: "1px solid var(--border)",
                                borderRadius: "4px",
                                padding: "0.15rem 0.4rem",
                                fontSize: "0.75rem",
                                color: "var(--midnight-indigo)",
                              }}
                            >
                              {v.attribute}: {v.value} {Number(v.extra_price) > 0 ? `(+$${Number(v.extra_price).toFixed(2)})` : ""}
                            </span>
                          ))
                        ) : (
                          <span style={{ color: "var(--secondary-text)", fontSize: "0.8rem" }}>None</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className={`status-badge ${p.is_active ? "status-active" : "status-overdue"}`}>
                        {p.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
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
                </tr>
              </thead>
              <tbody>
                {plans.map((pl) => (
                  <tr key={pl.id}>
                    <td>
                      <strong>{pl.name}</strong>
                    </td>
                    <td className="tabular-num">
                      <strong>${Number(pl.price).toFixed(2)}</strong>
                    </td>
                    <td>
                      <span className="chip" style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }}>
                        {pl.billing_period}
                      </span>
                    </td>
                    <td>{pl.min_quantity || 1}</td>
                    <td>{pl.renewable ? "Yes (Renewable)" : "Manual"}</td>
                    <td>{pl.auto_close ? "Yes (Auto-close)" : "No"}</td>
                    <td>
                      <span className="status-badge status-active">Active</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
