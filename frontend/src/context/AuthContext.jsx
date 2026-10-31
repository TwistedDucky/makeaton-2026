import { createContext, useContext, useEffect, useState, useCallback } from "react";
import {
    initializeCsrf,
    getCurrentUser,
    login as apiLogin,
    logout as apiLogout,
} from "../api/auth";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser]       = useState(null);
    const [loading, setLoading] = useState(true);

    // On mount — restore session if cookie is still alive
    // Uses res?.data || res to handle both response shapes
    useEffect(() => {
        initializeCsrf()
            .then(() => getCurrentUser())
            .then((res) => setUser(res?.data || res || null))
            .catch(() => setUser(null))
            .finally(() => setLoading(false));
    }, []);

    // login(email, password) → returns user data on success, throws on failure
    const login = useCallback(async (email, password) => {
        await initializeCsrf();
        const res = await apiLogin(email, password);
        const userData = res?.data || res;
        setUser(userData);
        return userData;
    }, []);

    // logout() → clears session and user state
    const logout = useCallback(async () => {
        try {
            await apiLogout();
        } finally {
            setUser(null);
        }
    }, []);

    const resolvedUser = user?.data || user;

    const value = {
        user,
        setUser,
        loading,
        login,
        logout,
        isAdmin:    resolvedUser?.role === "ADMIN",
        isStaff:    resolvedUser?.role === "STAFF",
        isCustomer: resolvedUser?.role === "CUSTOMER",
    };

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
    return ctx;
}
