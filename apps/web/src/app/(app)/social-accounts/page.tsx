"use client";

import { useAuth } from "@/lib/auth";
import type { LoginSessionPublic, SocialAccountPublic } from "@/lib/types";
import { useEffect, useMemo, useRef, useState } from "react";

type SessionState = { session: LoginSessionPublic; loading: boolean; error: string | null };

export default function SocialAccountsPage() {
  const auth = useAuth();
  const [accounts, setAccounts] = useState<SocialAccountPublic[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Record<string, SessionState>>({});
  const mountedRef = useRef(true);

  const platformOptions = useMemo(
    () => [
      { value: "x", label: "X（Twitter）" },
      { value: "reddit", label: "Reddit（预留）" },
      { value: "facebook", label: "Facebook（预留）" },
      { value: "instagram", label: "Instagram（预留）" },
    ],
    []
  );

  const [platformKey, setPlatformKey] = useState("x");
  const [handle, setHandle] = useState("");
  const [displayName, setDisplayName] = useState("");

  async function loadAccounts() {
    setLoading(true);
    setError(null);
    try {
      const res = await auth.apiFetch("/social-accounts");
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as SocialAccountPublic[];
      setAccounts(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    mountedRef.current = true;
    void loadAccounts();
    return () => {
      mountedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function createAccount(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await auth.apiFetch("/social-accounts", {
        method: "POST",
        body: JSON.stringify({
          platform_key: platformKey,
          handle: handle || null,
          display_name: displayName || null,
          labels: {},
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setHandle("");
      setDisplayName("");
      await loadAccounts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败");
    }
  }

  async function startLogin(account: SocialAccountPublic) {
    setSessions((prev) => ({
      ...prev,
      [account.id]: { session: prev[account.id]?.session as LoginSessionPublic, loading: true, error: null },
    }));
    try {
      const res = await auth.apiFetch(`/social-accounts/${account.id}/login-sessions`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      const session = (await res.json()) as LoginSessionPublic;
      setSessions((prev) => ({ ...prev, [account.id]: { session, loading: false, error: null } }));
      void pollLoginSession(account.id, session.id);
    } catch (err) {
      setSessions((prev) => ({
        ...prev,
        [account.id]: { session: prev[account.id]?.session as LoginSessionPublic, loading: false, error: String(err) },
      }));
    }
  }

  async function refreshSession(account: SocialAccountPublic) {
    const sessionId = sessions[account.id]?.session?.id;
    if (!sessionId) return;
    setSessions((prev) => ({ ...prev, [account.id]: { ...prev[account.id], loading: true, error: null } as SessionState }));
    try {
      const res = await auth.apiFetch(`/login-sessions/${sessionId}`);
      if (!res.ok) throw new Error(await res.text());
      const session = (await res.json()) as LoginSessionPublic;
      setSessions((prev) => ({ ...prev, [account.id]: { session, loading: false, error: null } }));
    } catch (err) {
      setSessions((prev) => ({
        ...prev,
        [account.id]: { ...prev[account.id], loading: false, error: String(err) } as SessionState,
      }));
    }
  }

  async function pollLoginSession(accountId: string, sessionId: string) {
    for (let i = 0; i < 120; i += 1) {
      await new Promise((r) => setTimeout(r, 3000));
      if (!mountedRef.current) return;

      try {
        const res = await auth.apiFetch(`/login-sessions/${sessionId}`);
        if (!res.ok) continue;
        const session = (await res.json()) as LoginSessionPublic;
        setSessions((prev) => ({ ...prev, [accountId]: { session, loading: false, error: null } }));

        if (["succeeded", "failed", "expired", "canceled"].includes(session.status)) {
          await loadAccounts();
          return;
        }
      } catch {
        // ignore
      }
    }
  }

  async function finalizeSession(account: SocialAccountPublic) {
    const sessionId = sessions[account.id]?.session?.id;
    if (!sessionId) return;
    setSessions((prev) => ({ ...prev, [account.id]: { ...prev[account.id], loading: true, error: null } as SessionState }));
    try {
      const res = await auth.apiFetch(`/login-sessions/${sessionId}/finalize`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      const session = (await res.json()) as LoginSessionPublic;
      setSessions((prev) => ({ ...prev, [account.id]: { session, loading: false, error: null } }));
      await loadAccounts();
    } catch (err) {
      setSessions((prev) => ({
        ...prev,
        [account.id]: { ...prev[account.id], loading: false, error: String(err) } as SessionState,
      }));
    }
  }

  async function cancelSession(account: SocialAccountPublic) {
    const sessionId = sessions[account.id]?.session?.id;
    if (!sessionId) return;
    setSessions((prev) => ({ ...prev, [account.id]: { ...prev[account.id], loading: true, error: null } as SessionState }));
    try {
      const res = await auth.apiFetch(`/login-sessions/${sessionId}/cancel`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      await refreshSession(account);
    } catch (err) {
      setSessions((prev) => ({
        ...prev,
        [account.id]: { ...prev[account.id], loading: false, error: String(err) } as SessionState,
      }));
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <h1 style={{ marginBottom: 16 }}>账号管理</h1>

      <form onSubmit={createAccount} style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
        <select
          value={platformKey}
          onChange={(e) => setPlatformKey(e.target.value)}
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}
        >
          {platformOptions.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
        <input
          value={handle}
          onChange={(e) => setHandle(e.target.value)}
          placeholder="@handle（可选）"
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333", minWidth: 220 }}
        />
        <input
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="display_name（可选）"
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333", minWidth: 220 }}
        />
        <button
          type="submit"
          style={{ padding: "10px 14px", borderRadius: 10, border: "none", background: "#2f6fed", color: "white" }}
        >
          添加账号
        </button>
      </form>

      {error ? <div style={{ color: "#ff6b6b", marginBottom: 12 }}>{error}</div> : null}
      {loading ? <div style={{ opacity: 0.8, marginBottom: 12 }}>加载中…</div> : null}

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {accounts.map((a) => {
          const s = sessions[a.id];
          return (
            <div key={a.id} style={{ border: "1px solid #222", borderRadius: 12, padding: 14 }}>
              <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                <div style={{ fontWeight: 700 }}>{a.platform_key}</div>
                <div style={{ opacity: 0.8 }}>{a.handle || a.display_name || "—"}</div>
                <div style={{ marginLeft: "auto", opacity: 0.7 }}>状态：{a.status}</div>
              </div>

              <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button
                  type="button"
                  onClick={() => startLogin(a)}
                  disabled={s?.loading}
                  style={{ padding: "8px 12px", borderRadius: 10, border: "1px solid #333", background: "transparent" }}
                >
                  开始登录（LoginSession）
                </button>
                <button
                  type="button"
                  onClick={() => finalizeSession(a)}
                  disabled={!s?.session?.id || s?.loading}
                  style={{ padding: "8px 12px", borderRadius: 10, border: "1px solid #333", background: "transparent" }}
                >
                  采集并保存凭证
                </button>
                <button
                  type="button"
                  onClick={() => refreshSession(a)}
                  disabled={!s?.session?.id || s?.loading}
                  style={{ padding: "8px 12px", borderRadius: 10, border: "1px solid #333", background: "transparent" }}
                >
                  刷新状态
                </button>
                <button
                  type="button"
                  onClick={() => cancelSession(a)}
                  disabled={!s?.session?.id || s?.loading}
                  style={{ padding: "8px 12px", borderRadius: 10, border: "1px solid #333", background: "transparent" }}
                >
                  取消会话
                </button>
                {s?.session?.remote_url ? (
                  <a
                    href={s.session.remote_url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ padding: "8px 12px", borderRadius: 10, border: "1px solid #2f6fed" }}
                  >
                    打开远程登录
                  </a>
                ) : null}
              </div>

              {s?.error ? <div style={{ marginTop: 10, color: "#ff6b6b" }}>{s.error}</div> : null}
              {s?.session ? (
                <div style={{ marginTop: 10, opacity: 0.85, fontSize: 13 }}>
                  <div>LoginSession：{s.session.status}</div>
                  <div>Expires：{new Date(s.session.expires_at).toLocaleString()}</div>
                  {!s.session.remote_url ? (
                    <div style={{ opacity: 0.7 }}>
                      remote_url 为空：当前 Browser Cluster 未配置远程可视化（可能是 local 模式或未设置 NOVNC_PUBLIC_URL）。
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
