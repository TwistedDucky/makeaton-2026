import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";

export default function PaymentsView() {
  const { user } = useAuth();
  const [payments, setPayments] = useState([
    {
      id: "PAY-9011",
      customer: "acme@corp.com",
      invoice: "INV-2026-0001",
      method: "Credit Card (Visa ending 4242)",
      date: "2026-03-05",
      status: "COMPLETED",
      amount: "208.86",
    },
    {
      id: "PAY-9012",
      customer: "stark@industries.com",
      invoice: "INV-2026-0002",
      method: "Direct Bank ACH",
      date: "2026-03-18",
      status: "COMPLETED",
      amount: "1475.00",
    },
    {
      id: "PAY-9013",
      customer: "acme@corp.com",
      invoice: "INV-2026-0000",
      method: "Credit Card (Visa ending 4242)",
      date: "2026-02-05",
      status: "COMPLETED",
      amount: "208.86",
    },
  ]);

  const role = user?.role || "GUEST";
  const isCustomer = role === "CUSTOMER";
  const displayPayments = isCustomer
    ? payments.filter((p) => p.customer === user?.email || p.customer === "acme@corp.com")
    : payments;

  return (
    <div className="view-container">
      <div className="view-header">
        <div>
          <h2>{isCustomer ? "My Payment History" : "Payments & Transactions"}</h2>
          <p>
            {isCustomer
              ? "All payments received and processed for your subscriptions."
              : "Reconciled customer payment transactions and allocation records."}
          </p>
        </div>
      </div>

      <div className="card">
        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Transaction ID</th>
                <th>Customer</th>
                <th>Applied Invoice</th>
                <th>Payment Method</th>
                <th>Date</th>
                <th>Status</th>
                <th style={{ textAlign: "right" }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {displayPayments.map((p) => (
                <tr key={p.id}>
                  <td>
                    <strong>{p.id}</strong>
                  </td>
                  <td>{p.customer}</td>
                  <td>{p.invoice}</td>
                  <td>{p.method}</td>
                  <td>{p.date}</td>
                  <td>
                    <span className="status-badge status-active">{p.status}</span>
                  </td>
                  <td style={{ textAlign: "right" }} className="tabular-num">
                    <strong>₹{p.amount}</strong>
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
