import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Eye, EyeOff, LogIn, AlertCircle } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import "./auth.css";

export default function LoginPage() {
    const navigate  = useNavigate();
    const { login } = useAuth();

    const [form, setForm]       = useState({ email: "", password: "" });
    const [showPwd, setShowPwd] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError]     = useState(null);

    function handleChange(e) {
        setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
        setError(null);
    }

    async function handleSubmit(e) {
        e.preventDefault();
        setLoading(true);
        setError(null);

        try {
            const user = await login(form.email.trim().toLowerCase(), form.password);

            // Role-based redirect
            if (user.role === "ADMIN")    return navigate("/admin/dashboard", { replace: true });
            if (user.role === "STAFF")    return navigate("/dashboard",       { replace: true });
            if (user.role === "CUSTOMER") return navigate("/portal",          { replace: true });

            navigate("/dashboard", { replace: true });
        } catch (err) {
            setError(err?.message || "Invalid email or password.");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="auth-page">
            <div className="auth-container">

                {/* Logo / Brand */}
                <div className="auth-brand">
                    <div className="brand-logo-mark">B</div>
                    <h1>Welcome back</h1>
                    <p>Sign in to your Brightloop account</p>
                </div>

                {/* Card */}
                <div className="auth-card">

                    {/* Error banner */}
                    {error && (
                        <div className="error-banner" style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', marginBottom: 'var(--space-4)' }}>
                            <AlertCircle size={16} style={{ marginTop: '2px', flexShrink: 0 }} />
                            <span>{error}</span>
                        </div>
                    )}

                    <form onSubmit={handleSubmit} noValidate className="auth-form">

                        {/* Email */}
                        <div className="form-field">
                            <label htmlFor="email">Email address</label>
                            <input
                                id="email"
                                name="email"
                                type="email"
                                autoComplete="email"
                                required
                                value={form.email}
                                onChange={handleChange}
                                placeholder="you@example.com"
                            />
                        </div>

                        {/* Password */}
                        <div className="form-field">
                            <div className="field-label-row">
                                <label htmlFor="password">Password</label>
                                <Link to="/forgot-password" className="forgot-link">
                                    Forgot password?
                                </Link>
                            </div>
                            <div className="password-input-wrapper">
                                <input
                                    id="password"
                                    name="password"
                                    type={showPwd ? "text" : "password"}
                                    autoComplete="current-password"
                                    required
                                    value={form.password}
                                    onChange={handleChange}
                                    placeholder="Enter your password"
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPwd((v) => !v)}
                                    aria-label={showPwd ? "Hide password" : "Show password"}
                                    className="password-toggle"
                                >
                                    {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                                </button>
                            </div>
                        </div>

                        {/* Submit */}
                        <button
                            type="submit"
                            disabled={loading || !form.email || !form.password}
                            className="btn-primary btn-auth"
                        >
                            {loading ? (
                                <span className="spinner" />
                            ) : (
                                <>
                                    <LogIn size={15} />
                                    Sign in
                                </>
                            )}
                        </button>
                    </form>

                    {/* Divider */}
                    <div className="auth-divider">
                        <span>or</span>
                    </div>

                    {/* Register link */}
                    <p className="auth-footer-text">
                        Don't have an account?{" "}
                        <Link to="/register" className="auth-link">
                            Create account
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    );
}
