import { apiRequest } from "./client";

export async function getQuotationTemplates() {
    return apiRequest("/sales/templates/");
}

export async function getQuotations(params = {}) {
    const query = new URLSearchParams(params).toString();
    return apiRequest(`/sales/quotations/${query ? `?${query}` : ""}`);
}

export async function createQuotationFromTemplate(data) {
    return apiRequest("/sales/quotations/from-template/", {
        method: "POST",
        body: JSON.stringify(data),
    });
}

export async function sendQuotation(id) {
    return apiRequest(`/sales/quotations/${id}/send/`, {
        method: "POST",
    });
}

export async function acceptQuotation(id) {
    return apiRequest(`/sales/quotations/${id}/accept/`, {
        method: "POST",
    });
}

export async function declineQuotation(id, reason = "") {
    return apiRequest(`/sales/quotations/${id}/decline/`, {
        method: "POST",
        body: JSON.stringify({ reason }),
    });
}

export async function convertQuotationToSubscription(id) {
    return apiRequest(`/sales/quotations/${id}/convert/`, {
        method: "POST",
    });
}
