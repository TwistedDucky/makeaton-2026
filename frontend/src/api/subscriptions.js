import { apiRequest } from "./client";

export async function getSubscriptions(params = {}) {
  const query = new URLSearchParams(params).toString();
  return apiRequest(`/subscriptions/${query ? "?" + query : ""}`);
}

export async function getSubscription(id) {
  return apiRequest(`/subscriptions/${id}/`);
}

export async function createSubscription(data) {
  return apiRequest("/subscriptions/", { method: "POST", body: JSON.stringify(data) });
}

export async function cancelSubscription(id) {
  return apiRequest(`/subscriptions/${id}/cancel/`, { method: "POST" });
}

