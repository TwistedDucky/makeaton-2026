import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Eye, EyeOff, LogIn, AlertCircle } from "lucide-react";
import { useAuth } from "../../context/AuthContext";

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
        <div className="min-h-screen bg-[#EEEBDA] flex items-center justify-center px-4">
            <div className="w-full max-w-md">

                {/* Logo / Brand */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-[#282B4A] mb-4">
                        <span className="text-white font-bold text-lg">B</span>
                    </div>
                    <h1 className="text-[28px] font-bold text-[#282B4A] leading-tight">
                        Welcome back
                    </h1>
                    <p className="text-sm text-[#6B7280] mt-1">
                        Sign in to your Brightloop account
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

                    <form onSubmit={handleSubmit} noValidate className="space-y-5">

                        {/* Email */}
                        <div>
                            <label
                                htmlFor="email"
                                className="block text-sm font-medium text-[#282B4A] mb-1.5"
                            >
                                Email address
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
                                className="w-full h-10 px-3 text-sm bg-white border border-[#DCD9C8] rounded-lg
                                           text-[#282B4A] placeholder-[#6B7280]
                                           focus:outline-none focus:ring-2 focus:ring-[#282B4A]/20 focus:border-[#282B4A]
                                           transition-colors"
                            />
                        </div>

                        {/* Password */}
                        <div>
                            <div className="flex items-center justify-between mb-1.5">
                                <label
                                    htmlFor="password"
                                    className="block text-sm font-medium text-[#282B4A]"
                                >
                                    Password
                                </label>
                                <Link
                                    to="/forgot-password"
                                    className="text-xs text-[#6B7280] hover:text-[#282B4A] transition-colors"
                                >
                                    Forgot password?
                                </Link>
                            </div>
                            <div className="relative">
                                <input
                                    id="password"
                                    name="password"
                                    type={showPwd ? "text" : "password"}
                                    autoComplete="current-password"
                                    required
                                    value={form.password}
                                    onChange={handleChange}
                                    placeholder="Enter your password"
                                    className="w-full h-10 px-3 pr-10 text-sm bg-white border border-[#DCD9C8] rounded-lg
                                               text-[#282B4A] placeholder-[#6B7280]
                                               focus:outline-none focus:ring-2 focus:ring-[#282B4A]/20 focus:border-[#282B4A]
                                               transition-colors"
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
                        </div>

                        {/* Submit */}
                        <button
                            type="submit"
                            disabled={loading || !form.email || !form.password}
                            className="w-full h-10 flex items-center justify-center gap-2
                                       bg-[#282B4A] hover:bg-[#1e2138] disabled:opacity-50 disabled:cursor-not-allowed
                                       text-white text-sm font-medium rounded-lg transition-colors"
                        >
                            {loading ? (
                                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            ) : (
                                <>
                                    <LogIn size={15} />
                                    Sign in
                                </>
                            )}
                        </button>
                    </form>

                    {/* Divider */}
                    <div className="flex items-center gap-3 my-6">
                        <div className="flex-1 h-px bg-[#DCD9C8]" />
                        <span className="text-xs text-[#6B7280]">or</span>
                        <div className="flex-1 h-px bg-[#DCD9C8]" />
                    </div>

                    {/* Register link */}
                    <p className="text-center text-sm text-[#6B7280]">
                        Don't have an account?{" "}
                        <Link
                            to="/register"
                            className="text-[#282B4A] font-medium hover:underline"
                        >
                            Create account
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    );
}
