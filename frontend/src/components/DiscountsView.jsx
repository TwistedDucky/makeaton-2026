import React from "react";

export default function DiscountsView() {
  const discounts = [
    {
      code: "EARLYBIRD10",
      description: "Early Bird 10% discount on standard SaaS products",
      type: "Percentage",
      value: "10%",
      scope: "Product Scope",
      status: "Active",
      expires: "2026-12-31",
    },
    {
      code: "STARTUP50",
      description: "Fixed $50 discount on any initial subscription order",
      type: "Fixed Amount",
      value: "$50.00",
      scope: "Subscription Scope",
      status: "Active",
      expires: "2026-06-30",
    },
    {
      code: "ENTERPRISE2026",
      description: "Annual Enterprise infrastructure partner tier",
      type: "Percentage",
      value: "15%",
      scope: "Subscription Scope",
      status: "Active",
      expires: "2026-12-31",
    },
  ];

  return (
    <div className="view-container">
      <div className="view-header">
        <div>
          <h2>Discounts & Promotional Rules</h2>
          <p>Coupon codes and discount rules calculated by the Member 2 pricing engine.</p>
        </div>
      </div>

      <div className="card">
        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Coupon Code</th>
                <th>Description</th>
                <th>Discount Type</th>
                <th>Discount Value</th>
                <th>Scope</th>
                <th>Expiry</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {discounts.map((d, i) => (
                <tr key={i}>
                  <td>
                    <code>{d.code}</code>
                  </td>
                  <td>{d.description}</td>
                  <td>{d.type}</td>
                  <td className="tabular-num">
                    <strong>{d.value}</strong>
                  </td>
                  <td>
                    <span className="chip" style={{ fontSize: "0.75rem", padding: "0.2rem 0.5rem" }}>
                      {d.scope}
                    </span>
                  </td>
                  <td>{d.expires}</td>
                  <td>
                    <span className="status-badge status-active">{d.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
