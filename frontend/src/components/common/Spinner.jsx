export default function Spinner({ size = 32 }) {
  return (
    <div
      aria-label="Loading"
      style={{
        width: size,
        height: size,
        border: "3px solid var(--border)",
        borderTop: "3px solid var(--accent)",
        borderRadius: "50%",
        animation: "spin 0.7s linear infinite",
        margin: "auto",
      }}
    />
  );
}

