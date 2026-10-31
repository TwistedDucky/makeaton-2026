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

export async function register(data) {
    // data: { email, first_name, last_name, phone_number, password }
    return apiRequest("/auth/register/", {
        method: "POST",
        body: JSON.stringify(data),
    });
}

export async function requestPasswordReset(email) {
    return apiRequest("/auth/password-reset/", {
        method: "POST",
        body: JSON.stringify({ email }),
    });
}

export async function confirmPasswordReset(uid, token, new_password) {
    return apiRequest("/auth/password-reset/confirm/", {
        method: "POST",
        body: JSON.stringify({ uid, token, new_password }),
    });
}
