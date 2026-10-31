import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Eye, EyeOff, UserPlus, CheckCircle2, XCircle, AlertCircle } from "lucide-react";
import { register } from "../../api/auth";
import { useAuth } from "../../context/AuthContext";
import "./auth.css";

// Password rule definitions — checked live as user types
const PASSWORD_RULES = [
    { id: "length",  label: "More than 8 characters",      test: (v) => v.length > 8 },
    { id: "upper",   label: "One uppercase letter (A–Z)",   test: (v) => /[A-Z]/.test(v) },
    { id: "lower",   label: "One lowercase letter (a–z)",   test: (v) => /[a-z]/.test(v) },
    { id: "special", label: "One special character (!@#…)", test: (v) => /[^a-zA-Z0-9]/.test(v) },
];

function PasswordRule({ met, label }) {
    return (
        <li style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 'var(--font-size-small)' }}>
            {met
                ? <CheckCircle2 size={13} style={{ color: 'var(--color-status-active-text)', flexShrink: 0 }} />
                : <XCircle      size={13} style={{ color: 'var(--color-text-secondary)', flexShrink: 0 }} />
            }
            <span style={{ color: met ? 'var(--color-status-active-text)' : 'var(--color-text-secondary)' }}>
                {label}
            </span>
        </li>
    );
}

export default function RegisterPage() {
    const navigate      = useNavigate();
    const { setUser }   = useAuth();

    const [form, setForm] = useState({
        email:        "",
        first_name:   "",
        last_name:    "",
        phone_number: "",
        password:     "",
    });
    const [showPwd,    setShowPwd]    = useState(false);
    const [pwdFocused, setPwdFocused] = useState(false);
    const [loading,    setLoading]    = useState(false);
    const [error,      setError]      = useState(null);
    const [fieldErrors, setFieldErrors] = useState({});

    const passwordRules = PASSWORD_RULES.map((r) => ({
        ...r,
        met: r.test(form.password),
    }));
    const passwordValid = passwordRules.every((r) => r.met);

    function handleChange(e) {
        const { name, value } = e.target;
        setForm((prev) => ({ ...prev, [name]: value }));
        setError(null);
        setFieldErrors((prev) => ({ ...prev, [name]: null }));
    }

    async function handleSubmit(e) {
        e.preventDefault();

        if (!passwordValid) {
            setError("Please fix the password issues before continuing.");
            return;
        }

        setLoading(true);
        setError(null);
        setFieldErrors({});

        try {
            const res = await register({
                email:        form.email.trim().toLowerCase(),
                first_name:   form.first_name.trim(),
                last_name:    form.last_name.trim(),
                phone_number: form.phone_number.trim(),
                password:     form.password,
            });

            // register endpoint auto-logs in — set user and redirect
            setUser(res.data);
            navigate("/portal", { replace: true });
        } catch (err) {
            // err is the parsed JSON body from apiRequest
            if (err?.errors) {
                // Field-level errors from serializer
                setFieldErrors(err.errors);
                setError(err.message || "Registration failed. Please check the fields below.");
            } else {
                setError(err?.message || "Something went wrong. Please try again.");
            }
        } finally {
            setLoading(false);
        }
    }

    const canSubmit = form.email && form.password && passwordValid && !loading;

    return (
        <div className="auth-page">
            <div className="auth-container">

                {/* Brand */}
                <div className="auth-brand">
                    <div className="brand-logo-mark">B</div>
                    <h1>Create your account</h1>
                    <p>Join Brightloop — it's free to get started</p>
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

                        {/* Name row */}
                        <div className="form-row">
                            <div className="form-field">
                                <label htmlFor="first_name">First name</label>
                                <input
                                    id="first_name"
                                    name="first_name"
                                    type="text"
                                    autoComplete="given-name"
                                    value={form.first_name}
                                    onChange={handleChange}
                                    placeholder="Alice"
                                    className={fieldErrors.first_name ? "input-error" : ""}
                                />
                                {fieldErrors.first_name && (
                                    <p className="field-error">{fieldErrors.first_name[0]}</p>
                                )}
                            </div>
                            <div className="form-field">
                                <label htmlFor="last_name">Last name</label>
                                <input
                                    id="last_name"
                                    name="last_name"
                                    type="text"
                                    autoComplete="family-name"
                                    value={form.last_name}
                                    onChange={handleChange}
                                    placeholder="Smith"
                                    className={fieldErrors.last_name ? "input-error" : ""}
                                />
                                {fieldErrors.last_name && (
                                    <p className="field-error">{fieldErrors.last_name[0]}</p>
                                )}
                            </div>
                        </div>

                        {/* Email */}
                        <div className="form-field">
                            <label htmlFor="email">
                                Email address <span style={{ color: 'var(--color-status-overdue-text)' }}>*</span>
                            </label>
                            <input
                                id="email"
                                name="email"
                                type="email"
                                autoComplete="email"
                                required
                                value={form.email}
                                onChange={handleChange}
                                placeholder="you@example.com"
                                className={fieldErrors.email ? "input-error" : ""}
                            />
                            {fieldErrors.email && (
                                <p className="field-error">{fieldErrors.email[0]}</p>
                            )}
                        </div>

                        {/* Phone (optional) */}
                        <div className="form-field">
                            <label htmlFor="phone_number">
                                Phone number
                                <span style={{ color: 'var(--color-text-secondary)', fontWeight: 'normal', marginLeft: '4px' }}>
                                    (optional)
                                </span>
                            </label>
                            <input
                                id="phone_number"
                                name="phone_number"
                                type="tel"
                                autoComplete="tel"
                                value={form.phone_number}
                                onChange={handleChange}
                                placeholder="+1 555 000 0000"
                            />
                        </div>

                        {/* Password */}
                        <div className="form-field">
                            <label htmlFor="password">
                                Password <span style={{ color: 'var(--color-status-overdue-text)' }}>*</span>
                            </label>
                            <div className="password-input-wrapper">
                                <input
                                    id="password"
                                    name="password"
                                    type={showPwd ? "text" : "password"}
                                    autoComplete="new-password"
                                    required
                                    value={form.password}
                                    onChange={handleChange}
                                    onFocus={() => setPwdFocused(true)}
                                    placeholder="Create a strong password"
                                    className={fieldErrors.password ? "input-error" : ""}
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
                            {fieldErrors.password && (
                                <p className="field-error">{fieldErrors.password[0]}</p>
                            )}

                            {/* Live password rules — shown once field is focused */}
                            {(pwdFocused || form.password) && (
                                <ul className="password-rules">
                                    {passwordRules.map((r) => (
                                        <PasswordRule key={r.id} met={r.met} label={r.label} />
                                    ))}
                                </ul>
                            )}
                        </div>

                        {/* Submit */}
                        <button
                            type="submit"
                            disabled={!canSubmit}
                            className="btn-primary btn-auth"
                        >
                            {loading ? (
                                <span className="spinner" />
                            ) : (
                                <>
                                    <UserPlus size={15} />
                                    Create account
                                </>
                            )}
                        </button>
                    </form>

                    {/* Divider */}
                    <div className="auth-divider">
                        <span>or</span>
                    </div>

                    <p className="auth-footer-text">
                        Already have an account?{" "}
                        <Link to="/login" className="auth-link">
                            Sign in
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    );
}
