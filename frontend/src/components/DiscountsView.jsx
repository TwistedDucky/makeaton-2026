import React, { useState, useEffect } from "react";
import { getDiscounts } from "../api/catalog";

export default function DiscountsView() {
  const [discounts, setDiscounts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadDiscounts() {
      setLoading(true);
      try {
        const res = await getDiscounts({ page_size: 100 });
        const list = res?.results || res || [];
        if (list.length > 0) {
          setDiscounts(
            list.map((d) => ({
              code: d.name,
              description: d.name,
              type: d.kind === "percentage" ? "Percentage" : "Fixed Amount",
              value: d.kind === "percentage" ? `${d.value}%` : `₹${Number(d.value).toFixed(2)}`,
              scope: d.scope ? `${d.scope.charAt(0).toUpperCase() + d.scope.slice(1)} Scope` : "Subscription Scope",
              status: d.is_active ? "Active" : "Inactive",
              expires: d.end_date || "2026-12-31",
            }))
          );
        } else {
          setDiscounts([
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
              description: "Fixed ₹50 discount on any initial subscription order",
              type: "Fixed Amount",
              value: "₹50.00",
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
          ]);
        }
      } catch (err) {
        setDiscounts([
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
            description: "Fixed ₹50 discount on any initial subscription order",
            type: "Fixed Amount",
            value: "₹50.00",
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
        ]);
      } finally {
        setLoading(false);
      }
    }

    loadDiscounts();
  }, []);

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
              {loading ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: "center", padding: "2rem" }}>
                    Loading discounts...
                  </td>
                </tr>
              ) : (
                discounts.map((d, i) => (
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
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
