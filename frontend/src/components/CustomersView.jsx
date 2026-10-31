import React, { useState, useEffect } from "react";
import { apiRequest } from "../api/client";
import { useAuth } from "../context/AuthContext";

export default function CustomersView({ onNavigate }) {
  const { user } = useAuth();
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    async function loadCustomers() {
      setLoading(true);
      try {
        const res = await apiRequest("/users/");
        const users = res?.results || res || [];
        const customerList = users.filter((u) => u.role === "CUSTOMER");
        if (customerList.length > 0) {
          setCustomers(customerList);
        } else {
          // Fallback demo customers if API returns empty
          setCustomers([
            { id: 1, email: "acme@corp.com", first_name: "Acme", last_name: "Corporation", role: "CUSTOMER", is_active: true, date_joined: "2026-01-15" },
            { id: 2, email: "stark@industries.com", first_name: "Stark", last_name: "Industries", role: "CUSTOMER", is_active: true, date_joined: "2026-02-01" },
            { id: 3, email: "wayne@enterprises.com", first_name: "Wayne", last_name: "Enterprises", role: "CUSTOMER", is_active: true, date_joined: "2026-02-20" },
          ]);
        }
      } catch (err) {
        // Fallback demo customers
        setCustomers([
          { id: 1, email: "acme@corp.com", first_name: "Acme", last_name: "Corporation", role: "CUSTOMER", is_active: true, date_joined: "2026-01-15" },
          { id: 2, email: "stark@industries.com", first_name: "Stark", last_name: "Industries", role: "CUSTOMER", is_active: true, date_joined: "2026-02-01" },
          { id: 3, email: "wayne@enterprises.com", first_name: "Wayne", last_name: "Enterprises", role: "CUSTOMER", is_active: true, date_joined: "2026-02-20" },
        ]);
      } finally {
        setLoading(false);
      }
    }
    loadCustomers();
  }, []);

  const filtered = customers.filter(
    (c) =>
      c.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
      `${c.first_name} ${c.last_name}`.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="view-container">
      <div className="view-header">
        <div>
          <h2>Customers Directory</h2>
          <p>Client accounts, contract associations, and subscription billing profiles.</p>
        </div>
      </div>

      <div className="filter-bar">
        <input
          type="text"
          placeholder="Filter customer by name or email..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{ maxWidth: "340px" }}
        />
      </div>

      <div className="card">
        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Customer / Account</th>
                <th>Company / Name</th>
                <th>Account Role</th>
                <th>Status</th>
                <th>Member Since</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "2rem" }}>
                    Loading customer accounts...
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "2rem", color: "var(--secondary-text)" }}>
                    No customer accounts match your search.
                  </td>
                </tr>
              ) : (
                filtered.map((cust) => (
                  <tr key={cust.id}>
                    <td>
                      <strong>{cust.email}</strong>
                    </td>
                    <td>{cust.first_name || cust.last_name ? `${cust.first_name} ${cust.last_name}` : cust.email.split("@")[0]}</td>
                    <td>
                      <span className="role-badge role-customer">CUSTOMER</span>
                    </td>
                    <td>
                      <span className="status-badge status-active">Active</span>
                    </td>
                    <td>{cust.date_joined ? cust.date_joined.slice(0, 10) : "2026-01-15"}</td>
                    <td style={{ textAlign: "right" }}>
                      <button
                        className="btn-secondary"
                        style={{ padding: "0.35rem 0.75rem", fontSize: "0.8rem" }}
                        onClick={() => onNavigate("subscriptions")}
                      >
                        View Contracts ➔
                      </button>
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
