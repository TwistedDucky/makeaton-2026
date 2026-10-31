import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Eye, EyeOff, UserPlus, CheckCircle2, XCircle, AlertCircle } from "lucide-react";
import { register } from "../../api/auth";
import { useAuth } from "../../context/AuthContext";

// Password rule definitions — checked live as user types
const PASSWORD_RULES = [
    { id: "length",  label: "More than 8 characters",      test: (v) => v.length > 8 },
    { id: "upper",   label: "One uppercase letter (A–Z)",   test: (v) => /[A-Z]/.test(v) },
    { id: "lower",   label: "One lowercase letter (a–z)",   test: (v) => /[a-z]/.test(v) },
    { id: "special", label: "One special character (!@#…)", test: (v) => /[^a-zA-Z0-9]/.test(v) },
];

function PasswordRule({ met, label }) {
    return (
        <li className="flex items-center gap-1.5 text-xs">
            {met
                ? <CheckCircle2 size={13} className="text-green-600 shrink-0" />
                : <XCircle      size={13} className="text-[#6B7280] shrink-0" />
            }
            <span className={met ? "text-green-700" : "text-[#6B7280]"}>{label}</span>
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
        <div className="min-h-screen bg-[#EEEBDA] flex items-center justify-center px-4 py-10">
            <div className="w-full max-w-md">

                {/* Brand */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-[#282B4A] mb-4">
                        <span className="text-white font-bold text-lg">B</span>
                    </div>
                    <h1 className="text-[28px] font-bold text-[#282B4A] leading-tight">
                        Create your account
                    </h1>
                    <p className="text-sm text-[#6B7280] mt-1">
                        Join Brightloop — it's free to get started
                    </p>
                </div>

                {/* Card */}
                <div className="bg-white rounded-xl border border-[#DCD9C8] p-8 shadow-sm">

                    {/* Error banner */}
                    {error && (
                        <div className="flex items-start gap-2 bg-[#FEE2E2] border border-[#FECACA] text-[#991B1B] rounded-lg px-4 py-3 mb-6 text-sm">
                            <AlertCircle size={16} className="mt-0.5 shrink-0" />
                            <span>{error}</span>
                        </div>
                    )}

                    <form onSubmit={handleSubmit} noValidate className="space-y-4">

                        {/* Name row */}
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <label htmlFor="first_name" className="block text-sm font-medium text-[#282B4A] mb-1.5">
                                    First name
                                </label>
                                <input
                                    id="first_name"
                                    name="first_name"
                                    type="text"
                                    autoComplete="given-name"
                                    value={form.first_name}
                                    onChange={handleChange}
                                    placeholder="Alice"
                                    className={`w-full h-10 px-3 text-sm bg-white rounded-lg text-[#282B4A] placeholder-[#6B7280]
                                        border transition-colors focus:outline-none focus:ring-2 focus:ring-[#282B4A]/20 focus:border-[#282B4A]
                                        ${fieldErrors.first_name ? "border-red-400" : "border-[#DCD9C8]"}`}
                                />
                                {fieldErrors.first_name && (
                                    <p className="text-xs text-red-600 mt-1">{fieldErrors.first_name[0]}</p>
                                )}
                            </div>
                            <div>
                                <label htmlFor="last_name" className="block text-sm font-medium text-[#282B4A] mb-1.5">
                                    Last name
                                </label>
                                <input
                                    id="last_name"
                                    name="last_name"
                                    type="text"
                                    autoComplete="family-name"
                                    value={form.last_name}
                                    onChange={handleChange}
                                    placeholder="Smith"
                                    className={`w-full h-10 px-3 text-sm bg-white rounded-lg text-[#282B4A] placeholder-[#6B7280]
                                        border transition-colors focus:outline-none focus:ring-2 focus:ring-[#282B4A]/20 focus:border-[#282B4A]
                                        ${fieldErrors.last_name ? "border-red-400" : "border-[#DCD9C8]"}`}
                                />
                                {fieldErrors.last_name && (
                                    <p className="text-xs text-red-600 mt-1">{fieldErrors.last_name[0]}</p>
                                )}
                            </div>
                        </div>

                        {/* Email */}
                        <div>
                            <label htmlFor="email" className="block text-sm font-medium text-[#282B4A] mb-1.5">
                                Email address <span className="text-red-500">*</span>
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
                                className={`w-full h-10 px-3 text-sm bg-white rounded-lg text-[#282B4A] placeholder-[#6B7280]
                                    border transition-colors focus:outline-none focus:ring-2 focus:ring-[#282B4A]/20 focus:border-[#282B4A]
                                    ${fieldErrors.email ? "border-red-400" : "border-[#DCD9C8]"}`}
                            />
                            {fieldErrors.email && (
                                <p className="text-xs text-red-600 mt-1">{fieldErrors.email[0]}</p>
                            )}
                        </div>

                        {/* Phone (optional) */}
                        <div>
                            <label htmlFor="phone_number" className="block text-sm font-medium text-[#282B4A] mb-1.5">
                                Phone number
                                <span className="text-[#6B7280] font-normal ml-1">(optional)</span>
                            </label>
                            <input
                                id="phone_number"
                                name="phone_number"
                                type="tel"
                                autoComplete="tel"
                                value={form.phone_number}
                                onChange={handleChange}
                                placeholder="+1 555 000 0000"
                                className="w-full h-10 px-3 text-sm bg-white border border-[#DCD9C8] rounded-lg
                                           text-[#282B4A] placeholder-[#6B7280]
                                           focus:outline-none focus:ring-2 focus:ring-[#282B4A]/20 focus:border-[#282B4A]
                                           transition-colors"
                            />
                        </div>

                        {/* Password */}
                        <div>
                            <label htmlFor="password" className="block text-sm font-medium text-[#282B4A] mb-1.5">
                                Password <span className="text-red-500">*</span>
                            </label>
                            <div className="relative">
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
                                    className={`w-full h-10 px-3 pr-10 text-sm bg-white rounded-lg text-[#282B4A] placeholder-[#6B7280]
                                        border transition-colors focus:outline-none focus:ring-2 focus:ring-[#282B4A]/20 focus:border-[#282B4A]
                                        ${fieldErrors.password ? "border-red-400" : "border-[#DCD9C8]"}`}
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPwd((v) => !v)}
                                    aria-label={showPwd ? "Hide password" : "Show password"}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#6B7280] hover:text-[#282B4A] transition-colors"
                                >
                                    {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                                </button>
                            </div>
                            {fieldErrors.password && (
                                <p className="text-xs text-red-600 mt-1">{fieldErrors.password[0]}</p>
                            )}

                            {/* Live password rules — shown once field is focused */}
                            {(pwdFocused || form.password) && (
                                <ul className="mt-2.5 space-y-1 bg-[#F6F5EE] border border-[#DCD9C8] rounded-lg px-3 py-2.5">
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
                            className="w-full h-10 flex items-center justify-center gap-2 mt-2
                                       bg-[#282B4A] hover:bg-[#1e2138] disabled:opacity-50 disabled:cursor-not-allowed
                                       text-white text-sm font-medium rounded-lg transition-colors"
                        >
                            {loading ? (
                                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            ) : (
                                <>
                                    <UserPlus size={15} />
                                    Create account
                                </>
                            )}
                        </button>
                    </form>

                    {/* Divider */}
                    <div className="flex items-center gap-3 my-5">
                        <div className="flex-1 h-px bg-[#DCD9C8]" />
                        <span className="text-xs text-[#6B7280]">or</span>
                        <div className="flex-1 h-px bg-[#DCD9C8]" />
                    </div>

                    <p className="text-center text-sm text-[#6B7280]">
                        Already have an account?{" "}
                        <Link to="/login" className="text-[#282B4A] font-medium hover:underline">
                            Sign in
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    );
}
