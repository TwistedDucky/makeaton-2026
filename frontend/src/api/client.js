const API_BASE_URL = "/api";

function getCookie(name) {
    const cookies = document.cookie.split(";");

    for (const cookie of cookies) {
        const [key, ...value] = cookie.trim().split("=");

        if (key === name) {
            return decodeURIComponent(value.join("="));
        }
    }

    return null;
}

export async function apiRequest(endpoint, options = {}) {
    const method = (options.method || "GET").toUpperCase();

    const headers = {
        "Content-Type": "application/json",
        ...options.headers,
    };

    if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
        const csrfToken = getCookie("csrftoken");

        if (csrfToken) {
            headers["X-CSRFToken"] = csrfToken;
        }
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        ...options,
        method,
        headers,
        credentials: "include",
    });

    // Handle empty responses and safely parse JSON
    const text = await response.text();
    let result = {};
    if (text) {
        try {
            result = JSON.parse(text);
        } catch {
            // Non-JSON response (e.g. HTML error page or plain text)
            result = {
                success: false,
                message: !response.ok
                    ? `Server error (${response.status}: ${response.statusText || "non-JSON response"})`
                    : text,
                raw: text,
            };
        }
    }

    if (!response.ok) {
        throw result;
    }

    return result;
}