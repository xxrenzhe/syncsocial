"use client";

import { useAuth } from "@/lib/auth";
import type { ProxyPoolPublic, ProxyPublic } from "@/lib/types";
import { useEffect, useMemo, useState } from "react";

export default function ProxiesPage() {
  const auth = useAuth();
  const [pools, setPools] = useState<ProxyPoolPublic[]>([]);
  const [proxies, setProxies] = useState<ProxyPublic[]>([]);
  const [selectedPoolId, setSelectedPoolId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const poolStrategies = useMemo(() => ["hash", "random"], []);
  const schemes = useMemo(() => ["http", "https", "socks5"], []);

  const [poolName, setPoolName] = useState("");
  const [poolStrategy, setPoolStrategy] = useState("hash");

  const [scheme, setScheme] = useState("http");
  const [host, setHost] = useState("");
  const [port, setPort] = useState(8080);
  const [country, setCountry] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [weight, setWeight] = useState(1);

  async function loadPools() {
    const res = await auth.apiFetch("/proxy-pools");
    if (!res.ok) throw new Error(await res.text());
    const data = (await res.json()) as ProxyPoolPublic[];
    setPools(data);
    if (!selectedPoolId && data[0]?.id) setSelectedPoolId(data[0].id);
  }

  async function loadProxies(poolId: string) {
    if (!poolId) {
      setProxies([]);
      return;
    }
    const res = await auth.apiFetch(`/proxy-pools/${poolId}/proxies`);
    if (!res.ok) throw new Error(await res.text());
    const data = (await res.json()) as ProxyPublic[];
    setProxies(data);
  }

  async function loadAll() {
    setLoading(true);
    setError(null);
    try {
      await loadPools();
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setError(null);
    if (!selectedPoolId) return;
    void loadProxies(selectedPoolId).catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPoolId]);

  async function createPool(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await auth.apiFetch("/proxy-pools", {
        method: "POST",
        body: JSON.stringify({ name: poolName, strategy: poolStrategy }),
      });
      if (!res.ok) throw new Error(await res.text());
      setPoolName("");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败");
    }
  }

  async function deletePool(poolId: string) {
    if (!window.confirm("确定删除该代理池？池内代理也会被删除")) return;
    setError(null);
    try {
      const res = await auth.apiFetch(`/proxy-pools/${poolId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      if (selectedPoolId === poolId) setSelectedPoolId("");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  }

  async function createProxy(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedPoolId) {
      setError("请先选择代理池");
      return;
    }
    setError(null);
    try {
      const res = await auth.apiFetch(`/proxy-pools/${selectedPoolId}/proxies`, {
        method: "POST",
        body: JSON.stringify({
          scheme,
          host,
          port,
          country: country || null,
          username: username || null,
          password: password || null,
          enabled,
          weight,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setHost("");
      setPort(8080);
      setCountry("");
      setUsername("");
      setPassword("");
      setEnabled(true);
      setWeight(1);
      await loadProxies(selectedPoolId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败");
    }
  }

  async function toggleProxy(p: ProxyPublic) {
    setError(null);
    try {
      const res = await auth.apiFetch(`/proxies/${p.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !p.enabled }) });
      if (!res.ok) throw new Error(await res.text());
      await loadProxies(p.pool_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新失败");
    }
  }

  async function deleteProxy(p: ProxyPublic) {
    if (!window.confirm("确定删除该代理？")) return;
    setError(null);
    try {
      const res = await auth.apiFetch(`/proxies/${p.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      await loadProxies(p.pool_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  }

  async function checkProxy(p: ProxyPublic) {
    setError(null);
    try {
      const res = await auth.apiFetch(`/proxies/${p.id}/check`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as { ok: boolean; status: string; error_code: string | null };
      window.alert(data.ok ? "代理可用" : `代理不可用：${data.error_code || data.status}`);
      await loadProxies(p.pool_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "检测失败");
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <h1 style={{ marginBottom: 16 }}>代理管理</h1>

      {error ? <div style={{ color: "#ff6b6b", marginBottom: 12 }}>{error}</div> : null}
      {loading ? <div style={{ opacity: 0.8, marginBottom: 12 }}>加载中…</div> : null}

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 18, alignItems: "center" }}>
        <button
          type="button"
          onClick={() => loadAll().catch(() => null)}
          style={{ padding: "10px 14px", borderRadius: 10, border: "1px solid #333", background: "transparent" }}
        >
          刷新
        </button>
        <select
          value={selectedPoolId}
          onChange={(e) => setSelectedPoolId(e.target.value)}
          style={{ padding: 10, borderRadius: 8, border: "1px solid #333", minWidth: 260 }}
        >
          <option value="">选择代理池…</option>
          {pools.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.strategy})
            </option>
          ))}
        </select>
        {selectedPoolId ? (
          <button
            type="button"
            onClick={() => deletePool(selectedPoolId).catch(() => null)}
            style={{ padding: "10px 14px", borderRadius: 10, border: "1px solid #7a1f1f", color: "#ff6b6b", background: "transparent" }}
          >
            删除当前代理池
          </button>
        ) : null}
      </div>

      <div style={{ border: "1px solid #222", borderRadius: 12, padding: 14, marginBottom: 16 }}>
        <div style={{ fontWeight: 700, marginBottom: 10 }}>创建代理池</div>
        <form onSubmit={createPool} style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <input
            value={poolName}
            onChange={(e) => setPoolName(e.target.value)}
            placeholder="代理池名称"
            required
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333", minWidth: 260 }}
          />
          <select
            value={poolStrategy}
            onChange={(e) => setPoolStrategy(e.target.value)}
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}
          >
            {poolStrategies.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <button
            type="submit"
            style={{ padding: "10px 14px", borderRadius: 10, border: "none", background: "#2f6fed", color: "white" }}
          >
            创建
          </button>
        </form>
        <div style={{ marginTop: 8, opacity: 0.7, fontSize: 12 }}>
          说明：保存代理需要后端配置 `CREDENTIAL_ENCRYPTION_KEY`（用于加密存储代理认证信息）。
        </div>
      </div>

      <div style={{ border: "1px solid #222", borderRadius: 12, padding: 14, marginBottom: 16 }}>
        <div style={{ fontWeight: 700, marginBottom: 10 }}>向当前代理池添加代理</div>
        <form onSubmit={createProxy} style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <select value={scheme} onChange={(e) => setScheme(e.target.value)} style={{ padding: 10, borderRadius: 8, border: "1px solid #333" }}>
            {schemes.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <input
            value={host}
            onChange={(e) => setHost(e.target.value)}
            placeholder="host"
            required
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333", minWidth: 240 }}
          />
          <input
            value={String(port)}
            onChange={(e) => setPort(Number(e.target.value))}
            type="number"
            min={1}
            max={65535}
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333", width: 120 }}
          />
          <input
            value={country}
            onChange={(e) => setCountry(e.target.value)}
            placeholder="country（可选：US）"
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333", width: 180 }}
          />
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="username（可选）"
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333", width: 200 }}
          />
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="password（可选）"
            type="password"
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333", width: 200 }}
          />
          <label style={{ display: "flex", gap: 8, alignItems: "center", opacity: 0.9 }}>
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            enabled
          </label>
          <input
            value={String(weight)}
            onChange={(e) => setWeight(Number(e.target.value))}
            type="number"
            min={1}
            max={100}
            style={{ padding: 10, borderRadius: 8, border: "1px solid #333", width: 120 }}
          />
          <button
            type="submit"
            disabled={!selectedPoolId}
            style={{
              padding: "10px 14px",
              borderRadius: 10,
              border: "none",
              background: selectedPoolId ? "#2f6fed" : "#444",
              color: "white",
            }}
          >
            添加代理
          </button>
        </form>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #333" }}>
              <th style={{ padding: 10 }}>Proxy</th>
              <th style={{ padding: 10 }}>Enabled</th>
              <th style={{ padding: 10 }}>Failures</th>
              <th style={{ padding: 10 }}>Last Error</th>
              <th style={{ padding: 10 }}>Last Checked</th>
              <th style={{ padding: 10 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {proxies.map((p) => (
              <tr key={p.id} style={{ borderBottom: "1px solid #222" }}>
                <td style={{ padding: 10, fontFamily: "monospace" }}>
                  {p.scheme}://{p.host}:{p.port}
                </td>
                <td style={{ padding: 10 }}>{p.enabled ? "yes" : "no"}</td>
                <td style={{ padding: 10 }}>{p.consecutive_failures}</td>
                <td style={{ padding: 10 }}>{p.last_error_code || "—"}</td>
                <td style={{ padding: 10 }}>{p.last_checked_at ? new Date(p.last_checked_at).toLocaleString() : "—"}</td>
                <td style={{ padding: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button
                    type="button"
                    onClick={() => checkProxy(p)}
                    style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid #333", background: "transparent" }}
                  >
                    检测
                  </button>
                  <button
                    type="button"
                    onClick={() => toggleProxy(p)}
                    style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid #333", background: "transparent" }}
                  >
                    {p.enabled ? "禁用" : "启用"}
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteProxy(p)}
                    style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid #7a1f1f", color: "#ff6b6b", background: "transparent" }}
                  >
                    删除
                  </button>
                </td>
              </tr>
            ))}
            {!selectedPoolId ? (
              <tr>
                <td colSpan={6} style={{ padding: 12, opacity: 0.7 }}>
                  请选择代理池
                </td>
              </tr>
            ) : proxies.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ padding: 12, opacity: 0.7 }}>
                  当前代理池暂无代理
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
