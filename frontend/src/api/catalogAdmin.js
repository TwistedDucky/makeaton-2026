import { apiRequest } from "./client";

function buildQuery(params = {}) {
  const cleanParams = {};
  for (const [key, val] of Object.entries(params)) {
    if (val !== undefined && val !== null && val !== "") {
      cleanParams[key] = val;
    }
  }
  const qs = new URLSearchParams(cleanParams).toString();
  return qs ? `?${qs}` : "";
}

// ============================================================================
// Discounts
// ============================================================================

export async function getDiscounts(params = {}) {
  return apiRequest(`/catalog/discounts/${buildQuery(params)}`);
}

export async function getDiscount(id) {
  return apiRequest(`/catalog/discounts/${id}/`);
}

export async function createDiscount(data) {
  return apiRequest("/catalog/discounts/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateDiscount(id, data) {
  return apiRequest(`/catalog/discounts/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deactivateDiscount(id) {
  return apiRequest(`/catalog/discounts/${id}/`, {
    method: "DELETE",
  });
}

export async function getDiscountUsage(id, params = {}) {
  return apiRequest(`/catalog/discounts/${id}/usage/${buildQuery(params)}`);
}

// ============================================================================
// Plans
// ============================================================================

export async function getPlans(params = {}) {
  return apiRequest(`/catalog/plans/${buildQuery(params)}`);
}

export async function getPlan(id) {
  return apiRequest(`/catalog/plans/${id}/`);
}

export async function createPlan(data) {
  return apiRequest("/catalog/plans/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updatePlan(id, data) {
  return apiRequest(`/catalog/plans/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deactivatePlan(id) {
  return apiRequest(`/catalog/plans/${id}/`, {
    method: "DELETE",
  });
}

// ============================================================================
// Taxes
// ============================================================================

export async function getTaxes(params = {}) {
  return apiRequest(`/catalog/taxes/${buildQuery(params)}`);
}

export async function getTax(id) {
  return apiRequest(`/catalog/taxes/${id}/`);
}

export async function createTax(data) {
  return apiRequest("/catalog/taxes/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateTax(id, data) {
  return apiRequest(`/catalog/taxes/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deactivateTax(id) {
  return apiRequest(`/catalog/taxes/${id}/`, {
    method: "DELETE",
  });
}

// ============================================================================
// Products & Variants
// ============================================================================

export async function getProducts(params = {}) {
  return apiRequest(`/catalog/products/${buildQuery(params)}`);
}

export async function getProduct(id) {
  return apiRequest(`/catalog/products/${id}/`);
}

export async function createProduct(data) {
  return apiRequest("/catalog/products/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateProduct(id, data) {
  return apiRequest(`/catalog/products/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deactivateProduct(id) {
  return apiRequest(`/catalog/products/${id}/`, {
    method: "DELETE",
  });
}

export async function getProductVariants(productId, params = {}) {
  return apiRequest(`/catalog/products/${productId}/variants/${buildQuery(params)}`);
}

export async function createProductVariant(productId, data) {
  return apiRequest(`/catalog/products/${productId}/variants/`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getProductVariant(productId, variantId) {
  return apiRequest(`/catalog/products/${productId}/variants/${variantId}/`);
}

export async function updateProductVariant(productId, variantId, data) {
  return apiRequest(`/catalog/products/${productId}/variants/${variantId}/`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deactivateProductVariant(productId, variantId) {
  return apiRequest(`/catalog/products/${productId}/variants/${variantId}/`, {
    method: "DELETE",
  });
}

