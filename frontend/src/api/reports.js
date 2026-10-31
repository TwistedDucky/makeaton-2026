import { apiRequest } from "./client";

export async function getReports(params = {}) {
  const query = new URLSearchParams(params).toString();
  return apiRequest(`/reports/${query ? "?" + query : ""}`);
}

export async function getReport(id) {
  return apiRequest(`/reports/${id}/`);
}

export async function generateReport(data) {
  return apiRequest("/reports/generate/", { method: "POST", body: JSON.stringify(data) });
}

