import { apiRequest } from "./client";

export async function getInvoices(params = {}) {
  const query = new URLSearchParams(params).toString();
  return apiRequest(`/billing/invoices/${query ? "?" + query : ""}`);
}

export async function getInvoice(id) {
  return apiRequest(`/billing/invoices/${id}/`);
}

export async function createInvoice(data) {
  return apiRequest("/billing/invoices/", { method: "POST", body: JSON.stringify(data) });
}

export async function updateInvoice(id, data) {
  return apiRequest(`/billing/invoices/${id}/`, { method: "PATCH", body: JSON.stringify(data) });
}

export async function confirmInvoice(id) {
  return apiRequest(`/billing/invoices/${id}/confirm/`, { method: "POST" });
}

export async function cancelInvoice(id) {
  return apiRequest(`/billing/invoices/${id}/cancel/`, { method: "POST" });
}

export async function generateInvoices(data = {}) {
  return apiRequest("/billing/invoices/generate/", { method: "POST", body: JSON.stringify(data) });
}
