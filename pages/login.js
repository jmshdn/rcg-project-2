import { useRouter } from "next/router";
import { useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });

      const payload = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(payload.error || "Login failed.");
      }

      const nextPath = typeof router.query.next === "string" && router.query.next.startsWith("/")
        ? router.query.next
        : "/";

      router.replace(nextPath);
    } catch (submitError) {
      setError(submitError.message || "Login failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <style jsx global>{`
        body {
          margin: 0;
          font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
          background:
            radial-gradient(circle at top, rgba(34, 211, 238, 0.18), transparent 35%),
            linear-gradient(160deg, #07111f 0%, #0f172a 55%, #111827 100%);
          min-height: 100vh;
        }
      `}</style>

      <main
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "24px",
        }}
      >
        <section
          style={{
            width: "100%",
            maxWidth: "420px",
            background: "rgba(15, 23, 42, 0.88)",
            border: "1px solid rgba(148, 163, 184, 0.18)",
            borderRadius: "22px",
            boxShadow: "0 30px 80px rgba(2, 6, 23, 0.55)",
            padding: "32px",
            color: "#e2e8f0",
          }}
        >
          <div style={{ marginBottom: "24px" }}>
            <div
              style={{
                width: "52px",
                height: "52px",
                borderRadius: "14px",
                display: "grid",
                placeItems: "center",
                background: "linear-gradient(135deg, #22d3ee 0%, #10b981 100%)",
                color: "#082f49",
                fontSize: "24px",
                fontWeight: "700",
                marginBottom: "16px",
              }}
            >
              R
            </div>
            <h1 style={{ margin: 0, fontSize: "28px", lineHeight: 1.1 }}>Private Access</h1>
            <p style={{ margin: "12px 0 0", color: "#94a3b8", lineHeight: 1.6 }}>
              This deployment is password protected so your OpenAI-backed resume tools cannot be used by strangers.
            </p>
          </div>

          <form onSubmit={handleSubmit}>
            <label style={{ display: "block", fontSize: "14px", marginBottom: "8px", color: "#cbd5e1" }}>
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoFocus
              autoComplete="current-password"
              style={{
                width: "100%",
                borderRadius: "12px",
                border: "1px solid rgba(148, 163, 184, 0.28)",
                background: "rgba(15, 23, 42, 0.65)",
                color: "#f8fafc",
                fontSize: "16px",
                padding: "14px 16px",
                boxSizing: "border-box",
                outline: "none",
              }}
            />

            {error ? (
              <p style={{ color: "#fca5a5", margin: "12px 0 0", lineHeight: 1.5 }}>{error}</p>
            ) : null}

            <button
              type="submit"
              disabled={loading}
              style={{
                width: "100%",
                marginTop: "20px",
                border: "none",
                borderRadius: "12px",
                padding: "14px 16px",
                fontSize: "16px",
                fontWeight: "600",
                cursor: loading ? "not-allowed" : "pointer",
                color: "#082f49",
                background: loading
                  ? "linear-gradient(135deg, #94a3b8 0%, #64748b 100%)"
                  : "linear-gradient(135deg, #22d3ee 0%, #10b981 100%)",
              }}
            >
              {loading ? "Checking..." : "Enter Site"}
            </button>
          </form>
        </section>
      </main>
    </>
  );
}
