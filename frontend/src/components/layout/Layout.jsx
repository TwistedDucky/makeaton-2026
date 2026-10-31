import Navbar from "./Navbar";

export default function Layout({ children }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100svh" }}>
      <Navbar />
      <main style={{ flex: 1, padding: "24px" }}>{children}</main>
    </div>
  );
}

