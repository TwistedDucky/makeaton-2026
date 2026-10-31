import React, { useState } from "react";

export default function CatalogView() {
  const [activeTab, setActiveTab] = useState("products");

  const products = [
    {
      id: 1,
      name: "Standard SaaS Platform",
      type: "service",
      sales_price: "50.00",
      cost_price: "10.00",
      tax_rate: "18.00%",
      variants: ["Standard Cloud Multi-Tenant", "Dedicated Region ($50)"],
      is_active: true,
    },
    {
      id: 2,
      name: "Pro Analytics & Reporting",
      type: "addon",
      sales_price: "100.00",
      cost_price: "20.00",
      tax_rate: "18.00%",
      variants: ["Daily Sync", "Realtime Webhooks (+$40)"],
      is_active: true,
    },
    {
      id: 3,
      name: "Enterprise Infrastructure",
      type: "service",
      sales_price: "500.00",
      cost_price: "150.00",
      tax_rate: "18.00%",
      variants: ["Dedicated VPC (+$560)", "High-Availability Multi-AZ (+$250)"],
      is_active: true,
    },
  ];

  const plans = [
    {
      id: 1,
      name: "Monthly Starter",
      price: "50.00",
      billing_period: "Monthly",
      renewable: true,
      closable: true,
      auto_close: false,
    },
    {
      id: 2,
      name: "Pro Growth",
      price: "150.00",
      billing_period: "Monthly",
      renewable: true,
      closable: true,
      auto_close: false,
    },
    {
      id: 3,
      name: "Enterprise Annual",
      price: "5000.00",
      billing_period: "Yearly",
      renewable: true,
      closable: true,
      auto_close: false,
    },
  ];

  return (
    <div className="view-container">
      <div className="view-header">
        <div>
          <h2>Catalog & Subscription Plans</h2>
          <p>Configure software offerings, recurring billing intervals, and product variant add-ons.</p>
        </div>
        <a
          href="http://localhost:8001/admin/catalog/"
          target="_blank"
          rel="noreferrer"
          className="btn-secondary"
        >
          Manage in Django Admin ↗
        </a>
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

      {activeTab === "products" ? (
        <div className="card">
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Product Name</th>
                  <th>Product Type</th>
                  <th>Base Price</th>
                  <th>Tax</th>
                  <th>Available Variants</th>
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
                    <td className="tabular-num">${p.sales_price}</td>
                    <td>{p.tax_rate}</td>
                    <td>
                      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                        {p.variants.map((v, i) => (
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
                            {v}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td>
                      <span className="status-badge status-active">Active</span>
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
                  <th>Auto-Renewal</th>
                  <th>Closable</th>
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
                      <strong>${pl.price}</strong>
                    </td>
                    <td>
                      <span className="chip" style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }}>
                        {pl.billing_period}
                      </span>
                    </td>
                    <td>{pl.renewable ? "Yes (Automatic)" : "Manual"}</td>
                    <td>{pl.closable ? "Yes" : "No"}</td>
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
