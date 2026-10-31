import React, { useState, useEffect } from "react";
import { getSubscriptions } from "../api/subscriptions";
import { useAuth } from "../context/AuthContext";
import SubscriptionPipeline from "./SubscriptionPipeline";

export default function SubscriptionsView() {
  const { user } = useAuth();
  const [subscriptions, setSubscriptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSub, setSelectedSub] = useState(null);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [search, setSearch] = useState("");

  async function loadSubscriptions() {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter !== "ALL") params.status = statusFilter;
      if (search) params.search = search;
      const res = await getSubscriptions(params);
      setSubscriptions(res.results || res || []);
    } catch (err) {
      console.error("Failed to load subscriptions", err);
      setSubscriptions([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSubscriptions();
  }, [statusFilter, user]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    loadSubscriptions();
  };

  return (
    <div className="view-container">
      {selectedSub ? (
        <SubscriptionPipeline
          subscription={selectedSub}
          onUpdated={(updated) => {
            setSelectedSub(updated);
            loadSubscriptions();
          }}
          onClose={() => setSelectedSub(null)}
        />
      ) : (
        <>
          <div className="view-header">
            <div>
              <h2>Subscriptions & Lifecycle Pipeline</h2>
              <p>Manage customer contract states: Draft ➔ Quotation ➔ Confirmed ➔ Active ➔ Closed</p>
            </div>
            <button className="btn-secondary" onClick={loadSubscriptions}>🔄 Refresh</button>
          </div>

          {/* Filter Bar */}
          <div className="filter-bar">
            <div className="status-chips">
              {["ALL", "DRAFT", "QUOTATION", "CONFIRMED", "ACTIVE", "CLOSED"].map((st) => (
                <button
                  key={st}
                  className={`chip ${statusFilter === st ? "chip-active" : ""}`}
                  onClick={() => setStatusFilter(st)}
                >
                  {st}
                </button>
              ))}
            </div>

            <form onSubmit={handleSearchSubmit} className="search-form">
              <input
                type="text"
                placeholder="Search sub number or email..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <button type="submit" className="btn-secondary">Search</button>
            </form>
          </div>

          {/* Subscriptions Grid/List */}
          {loading ? (
            <div className="loading-state">Loading subscriptions...</div>
          ) : subscriptions.length === 0 ? (
            <div className="empty-state">
              {!user ? (
                <>
                  <p>🔒 You are currently viewing as guest.</p>
                  <small>Use the <strong>1-Click Test Login</strong> buttons in the header above (e.g. <strong>Sales Rep 👤</strong> or <strong>Customer 🏢</strong>) to view and manage live contracts!</small>
                </>
              ) : (
                <>
                  <p>No subscriptions found matching the selected filters for your role ({user.role || "User"}).</p>
                  <small>Create a quotation in the Quotations tab and convert it to start a new subscription pipeline!</small>
                </>
              )}
            </div>
          ) : (
            <div className="subscriptions-grid">
              {subscriptions.map((sub) => (
                <div
                  key={sub.id}
                  className={`subscription-card status-border-${sub.status.toLowerCase()}`}
                  onClick={() => setSelectedSub(sub)}
                >
                  <div className="card-top">
                    <span className="sub-num">{sub.subscription_number}</span>
                    <span className={`status-badge status-${sub.status.toLowerCase()}`}>
                      {sub.status}
                    </span>
                  </div>

                  <div className="card-customer">{sub.customer_email}</div>

                  <div className="card-meta">
                    <div>
                      <small>Plan</small>
                      <strong>{sub.plan_name}</strong>
                    </div>
                    <div>
                      <small>Total Value</small>
                      <strong>${Number(sub.total_amount).toFixed(2)}</strong>
                    </div>
                  </div>

                  <div className="card-footer">
                    <span>Next Billing: {sub.next_billing_date || "—"}</span>
                    <span className="card-action-hint">Manage Lifecycle ➔</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
