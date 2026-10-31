export default function Navbar() {
  return (
    <nav style={{ borderBottom: "1px solid var(--border)", padding: "12px 24px", display: "flex", gap: "16px" }}>
      <a href="/dashboard">Dashboard</a>
      <a href="/catalog">Catalog</a>
      <a href="/billing">Billing</a>
      <a href="/subscriptions">Subscriptions</a>
      <a href="/payments">Payments</a>
      <a href="/reports">Reports</a>
    </nav>
  );
}

