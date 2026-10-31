import { useNavigate } from "react-router-dom";
import { ShieldX } from "lucide-react";

export default function UnauthorizedPage() {
    const navigate = useNavigate();

    return (
        <div className="min-h-screen bg-[#EEEBDA] flex items-center justify-center px-4">
            <div className="text-center max-w-sm">
                <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-[#FEE2E2] mb-5">
                    <ShieldX size={28} className="text-[#991B1B]" />
                </div>
                <h1 className="text-2xl font-bold text-[#282B4A] mb-2">Access denied</h1>
                <p className="text-sm text-[#6B7280] mb-6">
                    You don't have permission to view this page.
                </p>
                <button
                    onClick={() => navigate(-1)}
                    className="h-10 px-5 bg-[#282B4A] hover:bg-[#1e2138] text-white text-sm font-medium rounded-lg transition-colors"
                >
                    Go back
                </button>
            </div>
        </div>
    );
}
