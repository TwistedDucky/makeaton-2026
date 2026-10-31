import { apiRequest } from "./client";

export async function getPayments(params = {}) {
  const query = new URLSearchParams(params).toString();
  return apiRequest(`/payments/${query ? "?" + query : ""}`);
}

export async function getPayment(id) {
  return apiRequest(`/payments/${id}/`);
}

export async function createPayment(data) {
  return apiRequest("/payments/", { method: "POST", body: JSON.stringify(data) });
}

export const recordPayment = createPayment;
