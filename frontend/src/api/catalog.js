import { apiRequest } from "./client";

export async function getProducts(params = {}) {
  const query = new URLSearchParams(params).toString();
  return apiRequest(`/catalog/products/${query ? "?" + query : ""}`);
}

export async function getProduct(id) {
  return apiRequest(`/catalog/products/${id}/`);
}

export async function createProduct(data) {
  return apiRequest("/catalog/products/", { method: "POST", body: JSON.stringify(data) });
}

export async function updateProduct(id, data) {
  return apiRequest(`/catalog/products/${id}/`, { method: "PATCH", body: JSON.stringify(data) });
}

export async function deleteProduct(id) {
  return apiRequest(`/catalog/products/${id}/`, { method: "DELETE" });
}

export async function getPlans(params = {}) {
  const query = new URLSearchParams(params).toString();
  return apiRequest(`/catalog/plans/${query ? "?" + query : ""}`);
}

export async function getTaxes(params = {}) {
  const query = new URLSearchParams(params).toString();
  return apiRequest(`/catalog/taxes/${query ? "?" + query : ""}`);
}

export async function getDiscounts(params = {}) {
  const query = new URLSearchParams(params).toString();
  return apiRequest(`/catalog/discounts/${query ? "?" + query : ""}`);
}
