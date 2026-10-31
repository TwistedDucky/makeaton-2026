import { apiRequest } from "./client";

export async function getSubscriptions(params = {}) {
    const query = new URLSearchParams(params).toString();
    return apiRequest(`/subscriptions/${query ? `?${query}` : ""}`);
}

export async function getSubscription(id) {
    return apiRequest(`/subscriptions/${id}/`);
}

export async function createSubscription(data) {
    return apiRequest("/subscriptions/", {
        method: "POST",
        body: JSON.stringify(data),
    });
}

export async function transitionSubscription(id, targetStatus, reason = "") {
    return apiRequest(`/subscriptions/${id}/transition/`, {
        method: "POST",
        body: JSON.stringify({
            target_status: targetStatus,
            reason,
        }),
    });
}

export async function getDueSubscriptions(targetDate) {
    const query = targetDate ? `?target_date=${targetDate}` : "";
    return apiRequest(`/subscriptions/due-for-billing/${query}`);
}

export async function advanceBilling(id) {
    return apiRequest(`/subscriptions/${id}/advance-billing/`, {
        method: "POST",
    });
}
