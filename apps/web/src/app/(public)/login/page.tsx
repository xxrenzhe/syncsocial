"use client";

import { useAuth } from "@/lib/auth";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function LoginPage() {
  const auth = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!auth.loading && auth.user) router.replace("/");
  }, [auth.loading, auth.user, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await auth.login(email, password);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    }
  }

  return (
    <div style={{ maxWidth: 420, margin: "72px auto", padding: 24 }}>
      <h1 style={{ marginBottom: 16 }}>SyncSocial 登录</h1>
      <p style={{ marginBottom: 24, opacity: 0.8 }}>无注册入口：请使用管理员分配的账号登录。</p>
      <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span>邮箱</span>
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            type="email"
            placeholder="you@company.com"
            required
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span>密码</span>
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            placeholder="••••••••••••"
            required
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}
          />
        </label>
        {error ? <div style={{ color: "#ff6b6b" }}>{error}</div> : null}
        <button
          type="submit"
          disabled={auth.loading}
          style={{
            marginTop: 8,
            padding: 12,
            borderRadius: 10,
            border: "none",
            background: "#2f6fed",
            color: "white",
            cursor: "pointer",
          }}
        >
          登录
        </button>
      </form>
    </div>
  );
}

