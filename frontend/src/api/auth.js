import { apiRequest } from "./client";

export async function initializeCsrf() {
    return apiRequest("/auth/csrf/");
}

export async function login(email, password) {
    return apiRequest("/auth/login/", {
        method: "POST",
        body: JSON.stringify({ email, password }),
    });
}

export async function logout() {
    return apiRequest("/auth/logout/", {
        method: "POST",
    });
}

export async function getCurrentUser() {
    return apiRequest("/auth/me/");
}